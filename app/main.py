from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes_admin import router as admin_router
from app.api.routes_chat import limiter, router as chat_router
from app.api.routes_health import router as health_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="naisoch.com.pk storefront chatbot")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS locked to the storefront domain and its myshopify.com host - never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.allowed_origin,
        f"https://{settings.shopify_shop_domain}",
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(admin_router)
