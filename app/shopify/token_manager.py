"""
ShopifyTokenManager

Handles the post-Jan-2026 Shopify custom app auth flow: apps created in the
Dev Dashboard get a Client ID + Client Secret (never a static token). An
Admin API access token is obtained via the OAuth2 Client Credentials Grant
and expires roughly every 24h, so it must be refreshed proactively rather
than reactively on a 401.

Design note: this only works unmodified because we own naisoch.com.pk - the
Client Credentials Grant has no consent screen and can't be granted by a
third-party merchant. If this ever becomes a multi-tenant SaaS, per-merchant
auth needs the Authorization Code Grant / Token Exchange flow instead - a
different flow, not a tweak to this class. The `shop` parameter below exists
so that future seam doesn't require touching every call site, even though
today only one shop value is ever passed.
"""
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.db import connect, init_token_db

# Refresh this long before the ~24h expiry to leave headroom for clock drift
# and slow requests, so we never serve a token that expires mid-request.
REFRESH_MARGIN_SECONDS = 60 * 30  # 30 minutes


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # unix timestamp


class ShopifyTokenManager:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        default_shop_domain: str,
        db_path: Path,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._default_shop = default_shop_domain
        self._db_path = db_path
        self._memory_cache: dict[str, _CachedToken] = {}
        init_token_db(db_path)

    def get_valid_token(self, shop: str | None = None) -> str:
        """Returns a live Admin API access token for `shop`, refreshing if needed.

        `shop` defaults to the configured store domain. The parameter exists
        so this class isn't hardcoded to "the one store we own" - see module
        docstring.
        """
        shop = shop or self._default_shop

        cached = self._memory_cache.get(shop)
        if cached and cached.expires_at - time.time() > REFRESH_MARGIN_SECONDS:
            return cached.access_token

        row = self._load_from_db(shop)
        if row and row.expires_at - time.time() > REFRESH_MARGIN_SECONDS:
            self._memory_cache[shop] = row
            return row.access_token

        return self._refresh(shop)

    def _refresh(self, shop: str) -> str:
        url = f"https://{shop}/admin/oauth/access_token"
        resp = httpx.post(
            url,
            json={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 24 * 60 * 60)
        expires_at = time.time() + expires_in

        token = _CachedToken(access_token=access_token, expires_at=expires_at)
        self._memory_cache[shop] = token
        self._save_to_db(shop, token)
        return access_token

    def _load_from_db(self, shop: str) -> _CachedToken | None:
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT access_token, expires_at FROM shopify_tokens WHERE shop = ?",
                (shop,),
            ).fetchone()
        if not row:
            return None
        return _CachedToken(access_token=row["access_token"], expires_at=float(row["expires_at"]))

    def _save_to_db(self, shop: str, token: _CachedToken) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO shopify_tokens (shop, access_token, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(shop) DO UPDATE SET
                    access_token = excluded.access_token,
                    expires_at = excluded.expires_at
                """,
                (shop, token.access_token, str(token.expires_at)),
            )
