import hmac

from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings


def verify_admin_secret(
    x_admin_secret: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> None:
    # constant-time comparison - a naive `==` here is timing-attackable
    if not hmac.compare_digest(x_admin_secret, settings.admin_sync_secret):
        raise HTTPException(status_code=401, detail="Invalid admin secret")
