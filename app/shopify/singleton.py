"""
Process-wide singleton for ShopifyTokenManager. A single Railway instance
runs one process, so a module-level singleton is enough to share the
in-memory token cache across the /chat and /admin/sync routes without
re-hitting sqlite (or Shopify) on every call. If this ever runs multi-
instance, the sqlite-backed persistence already means each instance just
refreshes independently - correct, just not maximally efficient.
"""
from app.config import Settings
from app.shopify.token_manager import ShopifyTokenManager

_instance: ShopifyTokenManager | None = None


def get_token_manager(settings: Settings) -> ShopifyTokenManager:
    global _instance
    if _instance is None:
        _instance = ShopifyTokenManager(
            client_id=settings.shopify_client_id,
            client_secret=settings.shopify_client_secret,
            default_shop_domain=settings.shopify_shop_domain,
            db_path=settings.token_db_path,
        )
    return _instance
