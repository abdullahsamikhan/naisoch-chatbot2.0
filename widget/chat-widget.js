/**
 * naisoch.com.pk storefront chat widget.
 * Dependency-free vanilla JS - drop this into theme.liquid via a <script> tag.
 *
 * Usage in theme.liquid, just before </body>:
 *   <script src="{{ 'chat-widget.js' | asset_url }}" defer
 *           data-api-url="https://your-backend.up.railway.app/chat"></script>
 *
 * (Upload chat-widget.js to the theme's /assets folder first.)
 */
(function () {
  "use strict";

  var scriptTag = document.currentScript;
  var API_URL = (scriptTag && scriptTag.getAttribute("data-api-url")) || "/chat";

  var history = []; // [{role: "user"|"model", content: "..."}]

  function el(tag, props, children) {
    var node = document.createElement(tag);
    Object.assign(node, props || {});
    (children || []).forEach(function (c) {
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function injectStyles() {
    var style = document.createElement("style");
    style.textContent =
      "#nsc-launcher{position:fixed;bottom:20px;right:20px;width:56px;height:56px;" +
      "border-radius:50%;background:#111;color:#fff;font-size:24px;border:none;" +
      "cursor:pointer;z-index:99998;box-shadow:0 2px 10px rgba(0,0,0,.25)}" +
      "#nsc-panel{position:fixed;bottom:88px;right:20px;width:340px;max-width:92vw;" +
      "height:460px;max-height:70vh;background:#fff;border-radius:12px;" +
      "box-shadow:0 8px 30px rgba(0,0,0,.2);display:none;flex-direction:column;" +
      "overflow:hidden;z-index:99999;font-family:system-ui,sans-serif}" +
      "#nsc-panel.open{display:flex}" +
      "#nsc-header{background:#111;color:#fff;padding:12px 16px;font-weight:600}" +
      "#nsc-messages{flex:1;overflow-y:auto;padding:12px;font-size:14px}" +
      ".nsc-msg{margin-bottom:10px;line-height:1.4;white-space:pre-wrap}" +
      ".nsc-msg.user{text-align:right;color:#111}" +
      ".nsc-msg.model{text-align:left;color:#333}" +
      "#nsc-form{display:flex;border-top:1px solid #eee}" +
      "#nsc-input{flex:1;border:none;padding:10px;font-size:14px;outline:none}" +
      "#nsc-send{border:none;background:#111;color:#fff;padding:0 16px;cursor:pointer}";
    document.head.appendChild(style);
  }

  function appendMessage(role, content) {
    var messages = document.getElementById("nsc-messages");
    var bubble = el("div", { className: "nsc-msg " + role }, [content]);
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }

  async function sendMessage(text) {
    appendMessage("user", text);
    history.push({ role: "user", content: text });

    var thinking = el("div", { className: "nsc-msg model" }, ["..."]);
    document.getElementById("nsc-messages").appendChild(thinking);

    try {
      var res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: history.slice(0, -1), // don't double-send the message we just added
        }),
      });
      if (!res.ok) throw new Error("Request failed: " + res.status);
      var data = await res.json();
      thinking.remove();
      appendMessage("model", data.reply);
      history.push({ role: "model", content: data.reply });
    } catch (err) {
      thinking.remove();
      appendMessage("model", "Sorry, something went wrong. Please try again.");
      console.error("naisoch chat widget error:", err);
    }
  }

  function buildWidget() {
    injectStyles();

    var launcher = el("button", { id: "nsc-launcher", innerHTML: "&#128172;" });
    var panel = el("div", { id: "nsc-panel" }, [
      el("div", { id: "nsc-header" }, ["Chat with us"]),
      el("div", { id: "nsc-messages" }),
      el("form", { id: "nsc-form" }, [
        el("input", { id: "nsc-input", type: "text", placeholder: "Ask about a product...", autocomplete: "off" }),
        el("button", { id: "nsc-send", type: "submit" }, ["Send"]),
      ]),
    ]);

    launcher.addEventListener("click", function () {
      panel.classList.toggle("open");
    });

    panel.querySelector("#nsc-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var input = document.getElementById("nsc-input");
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      sendMessage(text);
    });

    document.body.appendChild(launcher);
    document.body.appendChild(panel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildWidget);
  } else {
    buildWidget();
  }
})();
