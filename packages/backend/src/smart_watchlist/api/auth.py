"""Authentication and the authorization boundary.

Every private endpoint resolves the caller here, from a server-side session referenced by
an HttpOnly cookie. The cookie carries a session identifier and nothing else — no user id,
no expiry the client could edit, nothing the frontend could forge.

Authorization is enforced by scoping every query to the resolved user, not by checking
afterwards. A caller who substitutes an id in a request body reaches a query that filters
on the session's user and finds nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, Response, status

if TYPE_CHECKING:
    from ..adapters.user_store import SqliteUserStore
    from ..core.userstate import User

__all__ = ["COOKIE_NAME", "clear_session_cookie", "current_user", "set_session_cookie"]

COOKIE_NAME = "swl_session"


def set_session_cookie(response: Response, session_id: str, max_age: int) -> None:
    """Set the session cookie.

    ``Secure`` is deliberately not set: local development is plain HTTP, and a Secure
    cookie would silently never be sent — which presents as broken authentication rather
    than as a configuration choice. A deployment behind TLS must set it.
    """
    response.set_cookie(
        COOKIE_NAME,
        session_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _store_from(request: Request) -> SqliteUserStore:
    return request.app.state.user_store


def current_user(request: Request) -> User:
    """Resolve the caller, or refuse.

    The failure is deliberately identical for a missing cookie, an unknown session and an
    expired one: distinguishing them tells an attacker which guess was closer.
    """
    session_id = request.cookies.get(COOKIE_NAME)
    user = None if not session_id else _store_from(request).user_for_session(session_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return user


CurrentUser = Depends(current_user)
