"""Request checks for traffic arriving through the Vercel proxy.

Production topology: browser -> Vercel (same origin as the SPA) -> Render. Vercel adds a shared
secret header to every /api request it forwards, so a request without it bypassed Vercel.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.security import secrets_equal

ORIGIN_SECRET_HEADER = "x-origin-secret"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def has_valid_origin_secret(request: Request) -> bool:
    expected = settings.origin_secret
    if not expected:
        return False
    return secrets_equal(request.headers.get(ORIGIN_SECRET_HEADER, ""), expected)


def client_ip(request: Request) -> str:
    # Vercel overwrites X-Forwarded-For with the visitor's IP (it doesn't forward client-supplied
    # values), and the origin secret proves the request came through Vercel. Without that proof
    # the header is attacker-controlled, so fall back to the socket peer.
    if has_valid_origin_secret(request):
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _forbidden() -> JSONResponse:
    # Deliberately generic: don't tell a direct caller which check it failed.
    return JSONResponse({"detail": "Forbidden"}, status_code=403)


class EdgeGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        is_api = request.url.path.startswith("/api/")
        if is_api and settings.origin_secret and not has_valid_origin_secret(request):
            return _forbidden()

        allowed = settings.allowed_origin_list
        origin = request.headers.get("origin")
        # CSRF defence on top of SameSite=Lax: browsers send Origin on state-changing requests.
        if is_api and allowed and request.method in UNSAFE_METHODS and origin is not None:
            if origin.rstrip("/") not in allowed:
                return _forbidden()

        response = await call_next(request)
        if is_api:
            # Per-user data must never be cached by Vercel's CDN or the browser.
            response.headers["Cache-Control"] = "no-store"
        return response
