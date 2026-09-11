"""
MDL-1 — the adapter interface.

The point of this file is that nothing above it knows which provider is in use.
docs/INVARIANTS.md F7 says no provider is structurally required; Sarvam
replacing the original assumption is the test of that, and the test is only
passed if the swap touches this directory and nothing else.

Two shapes cross this boundary:

    ModelRequest  — a system prompt, a user prompt, and a budget.
    ModelReply    — text, token counts, and what was actually used to produce it.

Not in the request: raw database rows, PII, conversation objects, IR types. The
caller has already reduced everything to strings by the time it gets here, which
is what makes redaction (MDL-8) a single chokepoint rather than a habit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ModelError(RuntimeError):
    """Any provider failure. The caller's response is always the same: fall back."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ModelTimeout(ModelError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ModelUnavailable(ModelError):
    """Provider reachable but refusing — 429, 5xx, auth failure."""


@dataclass(frozen=True)
class ModelRequest:
    """
    One call. `stage` names the pipeline step ("router", "planner",
    "synthesiser") and is carried through to the trace, because the question the
    trace has to answer is not "did a model run" but "which step ran it".
    """

    stage: str
    system: str
    user: str
    max_tokens: int | None = None
    temperature: float | None = None
    # sarvam-105b is a reasoning model: it emits `reasoning_content` first and
    # `content` stays null until it stops thinking. Effort is 'low' | 'medium' |
    # 'high' — there is no 'none'. Measured: a bare shape classification burns
    # ~1000–1900 completion tokens before the first character of the answer.
    reasoning_effort: str | None = None
    # Set by the planner. Whether the provider honours it is unverified —
    # docs/IMPL.md §10 Q1. Adapters that cannot enforce it must say so via
    # `ModelReply.schema_enforced`, never silently drop it.
    json_schema: dict | None = None
    stop: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelReply:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    latency_ms: int
    stage: str
    # False when a schema was requested but the adapter could not constrain the
    # decoder. The planner then validates-and-retries instead of trusting it.
    schema_enforced: bool = False
    finish_reason: str = "stop"
    # Billed inside completion_tokens, but tracked separately: on this model it
    # is most of the spend, and a cost table that does not separate it is wrong.
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ModelAdapter(Protocol):
    """Implemented by SarvamAdapter and FakeAdapter. Nothing else."""

    name: str

    async def complete(self, req: ModelRequest) -> ModelReply: ...

    async def close(self) -> None: ...
