"""
Tool functions exposed to Gemini via function calling. Plain, type-hinted
Python functions with docstrings - google-genai auto-generates the JSON
schema from these, so the docstrings are part of the contract, not just
documentation.

These are built per-request as closures over the request's dependencies
(GraphQL client, catalog search) rather than module-level globals, so the
app stays trivially testable and doesn't leak shared mutable state across
concurrent requests.
"""
import json

from app.catalog.queries import PRODUCT_BY_ID_QUERY
from app.catalog.search import CatalogSearch
from app.config import Settings
from app.shopify.graphql_client import ShopifyGraphQLClient


def build_tools(
    settings: Settings,
    gql_client: ShopifyGraphQLClient,
    catalog_search: CatalogSearch,
):
    with open(settings.policies_path, encoding="utf-8") as f:
        policies = json.load(f)

    def search_products(query: str) -> str:
        """Search the naisoch.com.pk product catalog by meaning, not exact
        keywords. Use this whenever the customer describes something they
        want, asks what's available, or asks for recommendations. Returns
        up to 5 matching products with cached price/availability - call
        get_product_details before quoting an exact price or stock status,
        since this cache can be a few hours stale.

        Args:
            query: what the customer is looking for, in their own words.
        """
        results = catalog_search.search(query, top_k=5)
        if not results:
            return "No matching products found in the catalog."
        return json.dumps(
            [
                {
                    "product_id": r["product_id"],
                    "title": r["title"],
                    "price": r["price"],
                    "currency": r["currency"],
                    "in_stock": bool(r["available"]),
                    "handle": r["handle"],
                }
                for r in results
            ]
        )

    def get_product_details(product_id: str) -> str:
        """Fetch live, up-to-the-second price, stock, and variant info for
        one specific product. ALWAYS call this before telling a customer an
        exact price or whether something is in stock - never quote numbers
        from search_products directly, since that cache can be stale.

        Args:
            product_id: the Shopify product GID, as returned by search_products.
        """
        data = gql_client.execute(PRODUCT_BY_ID_QUERY, {"id": product_id})
        product = data.get("product")
        if not product:
            return "Product not found."
        return json.dumps(product)

    def get_store_policy(topic: str) -> str:
        """Look up naisoch.com.pk's store policy on a given topic. Use this
        for any question about shipping, returns, payment methods, sizing,
        or how to contact support - never guess at policy details.

        Args:
            topic: one of "shipping", "returns", "payment", "sizing", "contact".
        """
        return policies.get(
            topic.lower(),
            "No policy information found for that topic. Suggest the customer contact support directly.",
        )

    return [search_products, get_product_details, get_store_policy]
