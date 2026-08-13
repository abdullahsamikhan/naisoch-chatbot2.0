PRODUCTS_PAGE_QUERY = """
query ProductsPage($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      title
      handle
      description
      productType
      tags
      totalInventory
      featuredImage {
        url
      }
      priceRangeV2 {
        minVariantPrice {
          amount
          currencyCode
        }
      }
    }
  }
}
"""

# Used by get_product_details for a live, single-product lookup so price /
# stock are never stale between syncs.
PRODUCT_BY_ID_QUERY = """
query ProductById($id: ID!) {
  product(id: $id) {
    id
    title
    handle
    description
    totalInventory
    featuredImage {
      url
    }
    priceRangeV2 {
      minVariantPrice {
        amount
        currencyCode
      }
    }
    variants(first: 10) {
      nodes {
        id
        title
        price
        availableForSale
        inventoryQuantity
      }
    }
  }
}
"""

# Fallback text search used by search_products when a product mentioned by
# the model can't be resolved from the embedding cache (e.g. cache is stale
# or empty right after a fresh deploy).
PRODUCTS_SEARCH_QUERY = """
query ProductsSearch($query: String!) {
  products(first: 5, query: $query) {
    nodes {
      id
      title
      handle
      totalInventory
      priceRangeV2 {
        minVariantPrice {
          amount
          currencyCode
        }
      }
    }
  }
}
"""
