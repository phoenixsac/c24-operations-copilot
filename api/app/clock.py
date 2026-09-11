"""
The clock. One place, so "now" means the same thing everywhere.

Why this exists: the seed pins a fixed `t0` so re-seeding is byte-identical
(C7), but rule evaluation was reading real wall-clock time. Those two agree
only on the day you seed. A day later, a ticket seeded "20 minutes old" is 26
hours old, `ticket_first_response_breach` fires on rows that were clean, and
evals that passed yesterday fail today for no reason anyone changed.

That was a real bug and it was caught by exactly the mechanism meant to catch
it: two eval cases went red with no code change between runs.

`APP_CLOCK` pins the moment. Unset — which is how production runs — this is
`datetime.now(timezone.utc)` and nothing is different. Set to the seed's `t0`,
the whole system is reproducible: same data, same clock, same violations,
forever.

It is deliberately a single scalar rather than a frozen-time library. The thing
that needs to hold is "the demo dataset and the rules that read it share one
notion of now", and a scalar does that without a dependency.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

_PINNED: datetime | None = None
_LOADED = False


def _pinned() -> datetime | None:
    """Parsed once. A malformed value is a startup failure, not a silent fallback."""
    global _PINNED, _LOADED
    if _LOADED:
        return _PINNED

    raw = (os.getenv("APP_CLOCK") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise RuntimeError(
                f"APP_CLOCK is not an ISO timestamp: {raw!r}"
            ) from exc
        _PINNED = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    _LOADED = True
    return _PINNED


def now() -> datetime:
    return _pinned() or datetime.now(timezone.utc)


def is_pinned() -> bool:
    """Surfaced in /health. A console showing a frozen clock should say so."""
    return _pinned() is not None


def sql_now() -> datetime:
    """
    For queries that used to say `now()` in SQL.

    Postgres `now()` is transaction time and cannot be overridden per session,
    so a pinned clock has to be passed in as a parameter. Every such query takes
    it as an argument rather than embedding it, which also makes the dependency
    visible in the SQL instead of hidden in the server's timezone.
    """
    return now()


def reset() -> None:
    """Test seam. Not called by the application."""
    global _PINNED, _LOADED
    _PINNED, _LOADED = None, False
