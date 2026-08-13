from fastapi import APIRouter, Depends

from app.catalog.sync import run_sync
from app.config import Settings, get_settings
from app.security import verify_admin_secret
from app.shopify.graphql_client import ShopifyGraphQLClient
from app.shopify.singleton import get_token_manager

router = APIRouter()


@router.post("/admin/sync", dependencies=[Depends(verify_admin_secret)])
def admin_sync(settings: Settings = Depends(get_settings)):
    token_manager = get_token_manager(settings)
    gql_client = ShopifyGraphQLClient(settings, token_manager)
    result = run_sync(settings, gql_client)
    return result
