"""
Fault injection for dependency failures. docs/INVARIANTS.md B5, F3.

The invariant says an unavailable source must be *named*, never silently
treated as empty. That is untestable without a way to make a source unavailable,
and "unplug the RC service" is not a step an eval suite can take. Eval X-04
depends on this existing.

Deliberately crude: a process-global set of source names that should raise.
Nothing in the request path reads it in production — the set is empty and every
check is one `in` against an empty set. It exists so failure is reachable.

The important property is that the failure is *typed*. A source that raises
`SourceUnavailable` produces a partial answer naming what is missing. A source
that returns `None` is indistinguishable from a source with nothing in it, and
that is exactly the confusion B5 exists to prevent: "no RC case on this order"
and "the RC service did not answer" mean opposite things to an agent.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

# Source names match the snapshot keys they populate.
SOURCES = ("rc_case", "refurb", "delivery", "payments", "events", "refunds")

_failing: set[str] = set()


class SourceUnavailable(Exception):
    """Raised instead of returning empty. That distinction is the whole point."""

    def __init__(self, source: str) -> None:
        super().__init__(f"source {source!r} did not respond")
        self.source = source


def check(source: str) -> None:
    if source in _failing:
        raise SourceUnavailable(source)


@contextmanager
def failing(*sources: str) -> Iterator[None]:
    """Test seam. Not called by the application."""
    previous = set(_failing)
    _failing.update(sources)
    try:
        yield
    finally:
        _failing.clear()
        _failing.update(previous)
