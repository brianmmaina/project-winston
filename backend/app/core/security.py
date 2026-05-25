"""API-key bearer auth dependency.

Used to protect write endpoints (refresh / retrain). Behavior:

* If ``settings.api_key`` is **empty**, the dependency is a no-op — useful for
  local development.
* Otherwise the request must carry ``Authorization: Bearer <key>`` (or the
  shorter ``X-API-Key`` header). Mismatch returns 401.

Read endpoints stay unauthenticated for now; if you want to lock the whole API
behind auth, add ``Depends(require_api_key)`` to the router include in main.py.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def _extract_provided_key(
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        # Allow raw token (no scheme) for ergonomics
        return parts[0].strip()
    return None


async def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    expected = (get_settings().api_key or "").strip()
    if not expected:
        # Auth disabled: dev mode.
        return
    provided = _extract_provided_key(authorization, x_api_key)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
