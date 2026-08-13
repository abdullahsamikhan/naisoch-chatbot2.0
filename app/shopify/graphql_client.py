"""
Minimal Admin GraphQL client. Shopify recommends GraphQL over REST for
product/inventory queries as of 2026, so this is the only client in the app.
"""
from typing import Any

import httpx

from app.config import Settings
from app.shopify.token_manager import ShopifyTokenManager


class ShopifyGraphQLClient:
    def __init__(self, settings: Settings, token_manager: ShopifyTokenManager):
        self._settings = settings
        self._token_manager = token_manager
        self._endpoint = (
            f"https://{settings.shopify_shop_domain}"
            f"/admin/api/{settings.shopify_api_version}/graphql.json"
        )

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._token_manager.get_valid_token()
        response = self._post(token, query, variables)

        # Token could have been revoked/rotated out-of-band; force one refresh
        # and retry rather than surfacing a 401 to the end user.
        if response.status_code == 401:
            token = self._token_manager._refresh(self._settings.shopify_shop_domain)
            response = self._post(token, query, variables)

        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            raise RuntimeError(f"Shopify GraphQL error: {payload['errors']}")
        return payload["data"]

    def _post(self, token: str, query: str, variables: dict[str, Any] | None):
        return httpx.post(
            self._endpoint,
            headers={
                "X-Shopify-Access-Token": token,
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables or {}},
            timeout=20.0,
        )
