"""
Chat service. The app is stateless server-side - no conversation DB, per the
cost constraint. The widget keeps the message history client-side and sends
it with every request; we just replay it into Gemini as `contents`.

Tool calling is handled MANUALLY here rather than via the SDK's
automatic_function_calling. That's not the original design - automatic
calling was tried first and worked most of the time, but its internal
conversation-state tracking proved unreliable across multi-step tool chains
(intermittent empty responses, and once even a reply claiming it had no
memory of the question it was just asked). Rather than paper over an
SDK-internal bug with retries, we build and manage the conversation state
ourselves: send a turn, check for function_call parts, execute them, append
the results as a new turn, and loop until the model returns plain text. Same
tools, same behavior from the customer's side, but no reliance on the buggy
internal path.

reply() returns (text, products, whatsapp):
- products: a compact list of dicts for any specific items the model looked
  up via get_product_details this turn - used by the API layer to render
  product cards alongside the text reply.
- whatsapp: None, or a dict like {"reason": "..."} if the model called
  offer_whatsapp_handoff this turn - used by the API layer to attach a
  "Chat on WhatsApp" button/link to the response.
Both are pure additions (see tools.py's side-channel collectors) - they do
not change the tool-calling loop, retry behavior, or temperature handling
above; those stay exactly as they were.
"""
import json

from google import genai
from google.genai import types as genai_types

from app.catalog.search import CatalogSearch
from app.chat.tools import build_tools
from app.config import Settings
from app.shopify.graphql_client import ShopifyGraphQLClient
from app.shopify.singleton import get_token_manager

SYSTEM_PROMPT = """You are the shopping assistant for this store's live chat widget.

Rules:
- Answer only questions about this store's products, availability, and policies.
- NEVER state a price or stock status from memory or by guessing. Always call
  search_products to find candidates, then get_product_details before quoting an
  exact price or availability to the customer.
- NEVER invent a store policy. Always call get_store_policy for shipping, returns,
  payment, sizing, or contact questions.
- When you recommend or confirm a specific product, keep your written reply short.
  A product card (image, price, stock status) is shown to the customer automatically
  right after your reply, so don't repeat all of those details in text - a brief
  sentence introducing or contextualizing the product is enough.
- Call offer_whatsapp_handoff when: the customer explicitly asks to talk to a
  human/agent; they describe an order-specific problem (wrong item, damaged
  item, missing order, a refund that needs manual review) that needs a real
  person's judgment rather than generic policy text; or you've genuinely
  exhausted what your tools can answer and they still need help. A "Chat on
  WhatsApp" button is shown to the customer automatically when you call this -
  don't also paste a phone number or link into your text reply, just briefly
  let them know they can continue there.
- If you don't have enough information after calling the available tools, say so
  plainly - do not make something up.
- Keep a friendly, concise tone. Keep answers short - this is a chat widget, not an essay.
- Don't refer to the store by its domain name or website address - the customer
  already knows what site they're on. Just say "we", "our store", or "here" naturally.
- Vary your phrasing naturally. Don't reuse the exact same sentence you used
  earlier in this conversation, even if the customer asks something very
  similar again - rephrase it like a person would, not a script repeating
  itself. A little natural variation (word choice, sentence order, a small
  aside) is good; robotic repetition is not.
- If asked something entirely unrelated to shopping here, politely redirect the
  conversation back to how you can help.
"""

MAX_TOOL_ITERATIONS = 6


class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role  # "user" | "model"
        self.content = content


def _to_genai_contents(history: list[ChatMessage]) -> list[genai_types.Content]:
    return [
        genai_types.Content(role=m.role, parts=[genai_types.Part(text=m.content)])
        for m in history
    ]


class ChatService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._genai_client = genai.Client(api_key=settings.gemini_api_key)
        self._gql_client = ShopifyGraphQLClient(settings, get_token_manager(settings))
        self._catalog_search = CatalogSearch(settings)

    def reply(self, history: list[ChatMessage]) -> tuple[str, list[dict], dict | None]:
        if not history:
            return "Hi! What can I help you find today?", [], None

        result = self._run(history)
        if result is not None:
            return result

        # First attempt came back genuinely empty (finish_reason=STOP,
        # parts=None - confirmed via debug logging, not a safety block).
        # Retrying with byte-identical input against a low-temperature model
        # tends to reproduce the exact same empty result, so this retry adds
        # a small system-side nudge as an extra turn - different input, real
        # chance of a different outcome - rather than resending the same
        # conversation verbatim.
        nudge = ChatMessage(
            role="user",
            content=(
                f"{history[-1].content}\n\n"
                "(Please use the available tools to answer this.)"
            ),
        )
        result = self._run(history[:-1] + [nudge])
        if result is not None:
            return result

        return "Sorry, I couldn't come up with an answer to that - could you rephrase?", [], None

    def _run(
        self, history: list[ChatMessage]
    ) -> tuple[str, list[dict], dict | None] | None:
        """Runs the manual tool-calling loop once. Returns (text, products,
        whatsapp), or None if the model produced neither a function call nor
        any text on a turn (occasional empty/blocked candidate - genuine
        model variance, not a code bug) - callers decide whether to retry
        that."""
        collected_products: list[dict] = []
        whatsapp_handoff: dict = {}
        tools = build_tools(
            self._settings,
            self._gql_client,
            self._catalog_search,
            collected_products,
            whatsapp_handoff,
        )
        tool_functions = {fn.__name__: fn for fn in tools}

        contents = _to_genai_contents(history)

        config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
            # A moderate amount of sampling temperature avoids two things:
            # (1) a specific Gemini quirk hit in testing, where low/zero
            # temperature made some prompts deterministically produce an
            # empty candidate (finish_reason=STOP, parts=None); (2) robotic,
            # word-for-word-identical replies to similar questions, which
            # read as scripted rather than conversational. 0.6 keeps replies
            # natural without loosening how strictly the model sticks to
            # tool-verified facts - that's enforced by the system prompt's
            # rules, not by temperature.
            temperature=0.6,
            # We're driving the tool-call loop ourselves below - see module
            # docstring for why automatic calling was dropped.
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._genai_client.models.generate_content(
                model=self._settings.gemini_chat_model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            model_content = candidate.content
            contents.append(model_content)

            function_calls = [
                part.function_call
                for part in (model_content.parts or [])
                if part.function_call
            ]

            if not function_calls:
                if response.text:
                    whatsapp = whatsapp_handoff if whatsapp_handoff.get("offered") else None
                    return response.text, collected_products[:4], whatsapp
                return None

            response_parts = []
            for call in function_calls:
                fn = tool_functions.get(call.name)
                if fn is None:
                    result = f"Unknown tool: {call.name}"
                else:
                    try:
                        result = fn(**(call.args or {}))
                    except Exception as exc:  # tool errors go back to the model, not the customer
                        result = json.dumps({"error": str(exc)})
                response_parts.append(
                    genai_types.Part.from_function_response(
                        name=call.name, response={"result": result}
                    )
                )

            contents.append(genai_types.Content(role="user", parts=response_parts))

        # Exceeded MAX_TOOL_ITERATIONS without a final text answer - genuinely
        # stuck in a tool-call loop rather than a one-off empty candidate, so
        # don't bother retrying this one.
        whatsapp = whatsapp_handoff if whatsapp_handoff.get("offered") else None
        return (
            "Sorry, I'm having trouble answering that right now - could you try again or contact support?",
            collected_products[:4],
            whatsapp,
        )