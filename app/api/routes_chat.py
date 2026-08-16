from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.chat.service import ChatMessage, ChatService
from app.config import Settings, get_settings

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
_rate_limit = get_settings().chat_rate_limit


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|model)$")
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)


class ProductCard(BaseModel):
    title: str | None = None
    price: str | None = None
    currency: str | None = None
    in_stock: bool = False
    image_url: str | None = None
    handle: str | None = None


class ChatResponse(BaseModel):
    reply: str
    products: list[ProductCard] = Field(default_factory=list)


_chat_service: ChatService | None = None


def get_chat_service(settings: Settings = Depends(get_settings)) -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(settings)
    return _chat_service


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(_rate_limit)
def chat(
    request: Request,
    body: ChatRequest,
    service: ChatService = Depends(get_chat_service),
):
    history = [ChatMessage(role=t.role, content=t.content) for t in body.history]
    history.append(ChatMessage(role="user", content=body.message))
    reply_text, products = service.reply(history)
    cards = [
        ProductCard(
            title=p.get("title"),
            price=p.get("price"),
            currency=p.get("currency"),
            in_stock=bool(p.get("in_stock")),
            image_url=p.get("image_url"),
            handle=p.get("handle"),
        )
        for p in products
    ]
    return ChatResponse(reply=reply_text, products=cards)
