"""Authentication and the authorization boundary.

Every private endpoint resolves the caller here, from a server-side session referenced by
an HttpOnly cookie. The cookie carries a session identifier and nothing else — no user id,
no expiry the client could edit, nothing the frontend could forge.

Authorization is enforced by scoping every query to the resolved user, not by checking
afterwards. A caller who substitutes an id in a request body reaches a query that filters
on the session's user and finds nothing.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, Response, status

if TYPE_CHECKING:
    from ..adapters.user_store import SqliteUserStore
    from ..core.userstate import User

__all__ = [
    "BEARER_SCHEME",
    "COOKIE_NAME",
    "clear_session_cookie",
    "current_user",
    "demo_mode_enabled",
    "optional_user",
    "session_id_of",
    "set_session_cookie",
]

COOKIE_NAME = "swl_session"

BEARER_SCHEME = "Bearer"
"""The second transport for the same session (D30).

One session table, one expiry, one revocation path, two ways to present the identifier: a
browser sends an HttpOnly cookie it cannot read, a mobile client sends
``Authorization: Bearer <session id>`` because it has no cookie jar worth trusting and no
same-origin story to rely on. A second *authentication system* would be a second place for
authorization to be wrong; a second transport is just an envelope.

The cookie is checked first. A browser that also sent a stale header must not be able to
downgrade itself, and a native client sends no cookie at all, so the order never matters
except in the one case where it should.
"""


def session_id_of(request: Request) -> str | None:
    """The session identifier this request presented, by either transport."""
    from_cookie = request.cookies.get(COOKIE_NAME)
    if from_cookie:
        return from_cookie

    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != BEARER_SCHEME.lower():
        return None
    return value.strip() or None


def demo_mode_enabled() -> bool:
    """Whether unauthenticated callers resolve to the shared demo account.

    On by default, because the point of this build is to be shown. Authentication is not
    removed or weakened — it is bypassed for callers who present no session, and every
    query is still scoped to whichever user was resolved. Turn it off with ``DEMO_MODE=off``
    and the sign-in wall returns exactly as it was.

    This is a local-demonstration switch. A deployment reachable by anyone else must set
    ``DEMO_MODE=off``, because in demo mode every anonymous visitor shares one account's
    watchlist and checkpoint.
    """
    return os.environ.get("DEMO_MODE", "on").strip().lower() not in ("off", "0", "false")


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

    In demo mode a caller with no session resolves to the shared demo account instead of
    being refused. Authorization is unchanged: whichever user is resolved, every query is
    scoped to them.
    """
    store = _store_from(request)
    session_id = session_id_of(request)
    user = None if not session_id else store.user_for_session(session_id)

    # A real session always wins, so signing in still works while demo mode is on and the
    # authenticated path stays exercised rather than dead.
    if user is None and demo_mode_enabled():
        return store.demo_user()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return user


CurrentUser = Depends(current_user)


def optional_user(request: Request) -> User | None:
    """Resolve the caller if we can, and refuse nothing.

    For endpoints that serve shared intelligence to everyone and additionally *annotate*
    it for whoever is asking. The verdicts returned are identical either way; knowing the
    caller only adds the note about their stated interests (D27). Reaching for
    :func:`current_user` here would put an authentication wall in front of a public
    resource in order to add a footnote.
    """
    store = _store_from(request)
    session_id = session_id_of(request)
    user = None if not session_id else store.user_for_session(session_id)
    if user is None and demo_mode_enabled():
        return store.demo_user()
    return user
