import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import get_settings

router = APIRouter(prefix="/internal", include_in_schema=False)


def _allowed_tls_name(name: str) -> bool:
    name = name.strip().lower().rstrip(".")
    if name == "localhost":
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    site = urlparse(get_settings().site_address).hostname
    return bool(site) and name == site


@router.get("/tls-ask")
async def tls_ask(domain: str = Query(max_length=253)) -> Response:
    """Caddy on-demand TLS permission check: issue internal certs only for IPs, localhost
    and the configured site. Blocked from the internet by the Caddyfile."""
    if not _allowed_tls_name(domain):
        raise HTTPException(status_code=404)
    return Response(status_code=200)
