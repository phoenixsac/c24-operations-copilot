"""
OBS-1 — the trace collector. docs/INVARIANTS.md A3, G1.

What this replaces: a hardcoded `stages` array that reported
`{"rules": 1ms, "synthesise": 1ms}` regardless of what happened. Those numbers
came in with the generated console so the trace tab had something to render,
and they were the worst kind of instrumentation — they looked like measurement,
sat in the UI beside real token counts, and would have sent someone debugging
in the wrong direction.

What it records instead: one span per pipeline stage, with real timings and a
structured `detail` payload saying what that stage *decided*. The decision is
the part worth keeping. "Router took 8 seconds" is mildly interesting; "router
degraded to keywords because the provider hit its token budget, and the keyword
path returned cohort at 0.85" is the line that explains the answer.

Two rules the payloads follow:

  * **Structured, never prose.** Every value is a scalar, an id, or a closed
    enum. A trace is not a place to write sentences about what happened; it is
    a place to record which branch ran.
  * **Post-redaction only.** What is traced is what was actually sent (MDL-8).
    Tracing the raw prompt "for debugging" would quietly undo redaction and put
    PII in a second store with different retention — H11's problem, twice.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Span:
    name: str
    ms: int
    detail: dict[str, Any] = field(default_factory=dict)


class Trace:
    """
    Collected per request, always on, exported optionally.

    Always on because the cost is a few dicts and a monotonic clock, and a
    tracer you have to remember to enable is one that is off when you need it.
    """

    def __init__(self, answer_id: str, *, query: str, actor: str,
                 city: str, conversation_id: str | None = None) -> None:
        self.answer_id = answer_id
        self.query = query
        self.actor = actor
        self.city = city
        self.conversation_id = conversation_id
        self.spans: list[Span] = []
        # The prompt/response pairs, filled in at the end of the request from
        # the gateway. Kept beside the spans rather than inside them because a
        # stage can make several calls (a planner repair retry is two), and a
        # span is one interval.
        self.exchanges: list[dict] = []
        self._t0 = time.monotonic()

    @contextmanager
    def span(self, name: str, **detail: Any) -> Iterator[dict[str, Any]]:
        """
        Time a stage. The yielded dict is mutable, so a stage can record what it
        decided *after* doing the work:

            with trace.span("route") as s:
                shape = ...
                s["shape"] = shape.value
        """
        started = time.monotonic()
        payload: dict[str, Any] = dict(detail)
        try:
            yield payload
        finally:
            self.spans.append(Span(
                name=name,
                ms=int((time.monotonic() - started) * 1000),
                detail=payload,
            ))

    def event(self, name: str, **detail: Any) -> None:
        """A decision with no duration — a skip, a fallback, a gate refusal."""
        self.spans.append(Span(name=name, ms=0, detail=dict(detail)))

    @property
    def total_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {"name": s.name, "ms": s.ms, **({"detail": s.detail} if s.detail else {})}
            for s in self.spans
        ]

    def summary(self) -> dict[str, Any]:
        """The one-line version, for a log or a list."""
        by_name = {s.name: s.ms for s in self.spans}
        return {
            "answer_id": self.answer_id,
            "total_ms": self.total_ms,
            "slowest": max(self.spans, key=lambda s: s.ms).name if self.spans else None,
            "stages": by_name,
        }
