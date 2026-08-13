"""
Catalog sync: pulls the full product list from Shopify, embeds each product
with Gemini, and writes the result to a local .npy matrix + SQLite metadata
sidecar on the persistent volume. This is the low-cost alternative to a
vector DB - fine at naisoch's current catalog size (see module note below).

Run via POST /admin/sync, triggered by an external cron (Railway cron or a
scheduled GitHub Action) - see the README for why not an in-process
scheduler.
"""
import datetime as dt

import numpy as np
from google import genai
from google.genai import types as genai_types

from app.catalog.queries import PRODUCTS_PAGE_QUERY
from app.config import Settings
from app.db import connect, init_catalog_db
from app.shopify.graphql_client import ShopifyGraphQLClient

# If naisoch's catalog grows past a few thousand SKUs, or this gets
# productized into the multi-tenant SaaS, swap this file-based cache for
# pgvector/Qdrant. Not needed at current scale - don't build it early.
EMBEDDING_BATCH_SIZE = 20


def _product_text(node: dict) -> str:
    """Text blob fed to the embedding model - title carries the most
    weight for retrieval quality, so it's repeated rather than truncated
    away if description/tags run long."""
    tags = ", ".join(node.get("tags", []))
    return (
        f"{node['title']}. {node['title']}. "
        f"Type: {node.get('productType', '')}. "
        f"Tags: {tags}. "
        f"{node.get('description', '')[:500]}"
    )


def run_sync(settings: Settings, gql_client: ShopifyGraphQLClient) -> dict:
    init_catalog_db(settings.catalog_db_path)
    genai_client = genai.Client(api_key=settings.gemini_api_key)

    nodes: list[dict] = []
    cursor = None
    while True:
        data = gql_client.execute(PRODUCTS_PAGE_QUERY, {"cursor": cursor})
        page = data["products"]
        nodes.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    if not nodes:
        return {"products_synced": 0}

    texts = [_product_text(n) for n in nodes]
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        result = genai_client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=batch,
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        embeddings.extend(e.values for e in result.embeddings)

    matrix = np.array(embeddings, dtype=np.float32)
    np.save(settings.embeddings_path, matrix)

    now = dt.datetime.utcnow().isoformat()
    with connect(settings.catalog_db_path) as conn:
        conn.execute("DELETE FROM products")
        for idx, node in enumerate(nodes):
            price_info = node.get("priceRangeV2", {}).get("minVariantPrice", {})
            conn.execute(
                """
                INSERT INTO products
                    (row_index, product_id, title, handle, price, currency,
                     available, image_url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idx,
                    node["id"],
                    node["title"],
                    node.get("handle"),
                    price_info.get("amount"),
                    price_info.get("currencyCode"),
                    1 if (node.get("totalInventory") or 0) > 0 else 0,
                    (node.get("featuredImage") or {}).get("url"),
                    now,
                ),
            )
        conn.execute(
            "INSERT INTO sync_meta (key, value) VALUES ('last_synced_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (now,),
        )

    return {"products_synced": len(nodes), "synced_at": now}
