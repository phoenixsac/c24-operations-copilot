"""
MDL-3 — the fake adapter. docs/INVARIANTS.md C6.

This is the default, not the fallback. A fresh clone with no API key boots,
serves the console, and runs the whole eval suite.

Three properties it must have, in order of how easy they are to lose:

  1. NO NETWORK. Not "a network call with a short timeout" — no client at all.
     The suite must be runnable on a plane and cost nothing.
  2. DETERMINISTIC. Same request, same reply, forever. C1 and C2 are asserted
     against this adapter; if the fake drifts, the assertion is meaningless.
  3. HONEST FAILURE. It can be told to fail, so the F4 degraded path is
     exercised by tests rather than only in production.

Replies come from `FIXTURES` when a request matches, and from a deterministic
synthetic reply otherwise. The synthetic reply is intentionally bland: a fake
that guesses well hides planner bugs, and a fake that guesses badly finds them.
"""

from __future__ import annotations

import hashlib
import json

from app.model.base import ModelReply, ModelRequest, ModelUnavailable

# Keyed by (stage, sha1(user)[:12]). Populated as eval cases land — EVAL-1.
# An empty registry is a valid state; the synthetic path covers everything.
FIXTURES: dict[tuple[str, str], str] = {}


# Stages where a wrong answer is worse than no answer. The synthesiser is not
# here: bland prose is harmless, and a test that never exercises the prose path
# never exercises `check()` either.
_MUST_DEGRADE = frozenset({"router", "planner"})


def fixture_key(stage: str, user: str) -> tuple[str, str]:
    return stage, hashlib.sha1(user.encode()).hexdigest()[:12]


def register(stage: str, user: str, reply: str) -> None:
    FIXTURES[fixture_key(stage, user)] = reply


def _stable_int(*parts: str) -> int:
    return int(hashlib.sha1("|".join(parts).encode()).hexdigest()[:8], 16)


class FakeAdapter:
    name = "fake"

    def __init__(self, *, fail: bool = False) -> None:
        # Flipped by tests to prove the gateway degrades rather than 500s.
        self.fail = fail
        self.calls: list[ModelRequest] = []

    async def complete(self, req: ModelRequest) -> ModelReply:
        self.calls.append(req)

        if self.fail:
            raise ModelUnavailable("fake adapter: forced failure")

        hit = FIXTURES.get(fixture_key(req.stage, req.user))
        if hit is None and req.stage in _MUST_DEGRADE:
            # No fixture means the fake has no opinion — and "no opinion" must
            # not be expressible as an answer. Returning "unsupported" here
            # would be the fake *asserting* a classification it did not make,
            # and the caller would act on it. Raising instead makes the caller
            # degrade to the deterministic path, which is both honest and
            # exactly what the eval suite needs to grade (ADR-014, ADR-015).
            raise ModelUnavailable(f"fake adapter: no fixture for stage {req.stage!r}")

        text = hit if hit is not None else self._synthetic(req)

        return ModelReply(
            text=text,
            # Rough but stable. Token *accounting* (MDL-6) needs a real counter;
            # this only needs to be non-zero and reproducible.
            prompt_tokens=max(1, len(req.system) + len(req.user)) // 4,
            completion_tokens=max(1, len(text)) // 4,
            model="fake",
            # Fixed, not measured. A latency that varies run to run turns a
            # determinism assertion into a flaky test.
            latency_ms=1,
            stage=req.stage,
            schema_enforced=req.json_schema is not None,
            finish_reason="stop",
        )

    def _synthetic(self, req: ModelRequest) -> str:
        """Deterministic, uninformative, well-formed."""
        if req.json_schema is not None:
            # Shape-valid, content-empty. Enough for the planner's parse path to
            # be exercised; not enough to accidentally pass a rule assertion.
            return json.dumps(
                {"shape": "unsupported", "confidence": 0.0, "_fake": True},
                sort_keys=True,
            )
        if req.stage == "router":
            return "unsupported"
        return f"[fake:{req.stage}:{_stable_int(req.stage, req.user) % 100000:05d}]"

    async def close(self) -> None:
        return None
