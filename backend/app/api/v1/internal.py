import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import get_settings
from app.core.redis import get_redis

TLS_NAMES_KEY = "tls:names"
MAX_TLS_NAMES = 20

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
    name = domain.strip().lower().rstrip(".")
    if not _allowed_tls_name(name):
        raise HTTPException(status_code=404)
    # Every new name costs a certificate: cap the number of distinct names (SNI flooding with
    # random IPs would otherwise burn CPU and disk). Caddy caches issued certs, so legitimate
    # names are asked about once.
    redis = get_redis()
    if not await redis.sismember(TLS_NAMES_KEY, name):
        if await redis.scard(TLS_NAMES_KEY) >= MAX_TLS_NAMES:
            raise HTTPException(status_code=404)
        await redis.sadd(TLS_NAMES_KEY, name)
    return Response(status_code=200)
