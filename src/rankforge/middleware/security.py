# src/rankforge/middleware/security.py

"""Security headers middleware."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every response.

    The API serves JSON only, so a restrictive baseline is safe:
    - X-Content-Type-Options: prevent MIME sniffing
    - X-Frame-Options: the API never needs to be framed
    - Referrer-Policy: don't leak URLs to third parties
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response
