"""
MDL-4 — the model gateway.

The single place a model call can originate. Router, planner and synthesiser all
come through here, which is what makes budgets (D5), token accounting (G3),
trace records (A3) and the redaction chokepoint (MDL-8) enforceable in one place
instead of three.

What it decides, that the adapters do not:

  * whether a failure is retried, and how many times;
  * whether a failure ends the request or degrades it (F4 — degrade, always);
  * whether the call is allowed to leave the process at all.

That last one is the redaction gate. It is not implemented yet — MDL-8 — so
rather than let prompts flow out un-redacted while a TODO sits in a file, the
gate defaults closed: a networked adapter refuses any call the caller has not
explicitly marked as having passed redaction. Nothing calls the gateway on the
request path today (ask.py is still fully deterministic), so this blocks no
existing behaviour. It blocks the future mistake.
"""

from __future__ import annotations

import logging

from app.model.base import (
    ModelAdapter,
    ModelError,
    ModelReply,
    ModelRequest,
)
from app.model.config import ModelSettings, settings

log = logging.getLogger("copilot.model")


class RedactionRequired(RuntimeError):
    """H5 — fail closed. Drop the call, never send it."""


class Gateway:
    def __init__(self, adapter: ModelAdapter, cfg: ModelSettings) -> None:
        self._adapter = adapter
        self._cfg = cfg
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0
        # Per-request, because a Gateway is per-process. Cleared by `begin()` at
        # the start of each /ask, or one request would show another's prompts.
        self.exchanges: list[dict] = []

    @property
    def adapter_name(self) -> str:
        return self._adapter.name

    @property
    def model_name(self) -> str:
        return "fake" if self._adapter.name == "fake" else self._cfg.model

    async def complete(self, req: ModelRequest, *, redacted: bool = False) -> ModelReply:
        """
        Raises ModelError after exhausting retries. Callers catch it and take the
        deterministic path — they never propagate it to the operator.
        """
        if self._cfg.uses_network and not redacted:
            raise RedactionRequired(
                f"stage {req.stage!r} tried to reach {self._adapter.name} without "
                "passing redaction (MDL-8). Refusing to send."
            )

        attempts = self._cfg.max_retries + 1
        last: ModelError | None = None

        for attempt in range(attempts):
            try:
                reply = await self._adapter.complete(req)
            except ModelError as exc:
                last = exc
                # Failures are the interesting ones. A timeout with 11k chars of
                # reasoning and no content is exactly what you want to read.
                self.exchanges.append({
                    "stage": req.stage, "model": self.model_name,
                    "system": req.system, "user": req.user,
                    "output": None, "error": str(exc), "attempt": attempt + 1,
                })
                # A 4xx is our bug; sending it again just spends the budget twice.
                if not exc.retryable or attempt == attempts - 1:
                    break
                log.warning(
                    "model call failed (stage=%s attempt=%d/%d): %s",
                    req.stage, attempt + 1, attempts, exc,
                )
                continue

            self.calls += 1
            self.prompt_tokens += reply.prompt_tokens
            self.completion_tokens += reply.completion_tokens
            self.reasoning_tokens += reply.reasoning_tokens

            # The exchange itself, kept for inspection.
            #
            # This is what you need in order to iterate on a prompt, and it is
            # the one thing no amount of timing data substitutes for. Note what
            # is kept: `req.system` and `req.user` are the strings that actually
            # went out — already through redaction (MDL-8). Capturing the
            # pre-redaction text "for debugging" would quietly undo it and put
            # PII in a second store with no retention policy.
            self.exchanges.append({
                "stage": req.stage,
                "model": reply.model,
                "system": req.system,
                "user": req.user,
                "output": reply.text,
                "tokens": {"prompt": reply.prompt_tokens,
                           "completion": reply.completion_tokens,
                           "reasoning": reply.reasoning_tokens},
                "latency_ms": reply.latency_ms,
                "finish_reason": reply.finish_reason,
                "schema_enforced": reply.schema_enforced,
                "attempt": attempt + 1,
            })
            return reply

        assert last is not None
        log.warning("model call exhausted (stage=%s): %s", req.stage, last)
        raise last

    def begin(self) -> None:
        """
        Clear per-request state — counters included.

        These were cumulative, and the docstring here used to claim that was
        deliberate. It was not: `usage()` feeds the per-request trace, so every
        request reported every token since the process started and the number
        only ever grew. A cost figure that rises whether or not you spend
        anything is not a cost figure.

        Process totals, if ever wanted, belong in a metrics counter that is
        explicitly cumulative — not in the object that answers "what did this
        request cost".
        """
        self.exchanges = []
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0

    def usage(self) -> dict:
        """Folded into the trace. A3 / G3."""
        return {
            "adapter": self.adapter_name,
            "model": self.model_name,
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            # Broken out because on sarvam-105b it is the majority of the spend.
            "reasoning_tokens": self.reasoning_tokens,
        }

    async def close(self) -> None:
        await self._adapter.close()


_gateway: Gateway | None = None


def build(cfg: ModelSettings | None = None) -> Gateway:
    cfg = cfg or settings()
    if cfg.adapter == "sarvam":
        from app.model.sarvam import SarvamAdapter

        adapter: ModelAdapter = SarvamAdapter(cfg)
    else:
        from app.model.fake import FakeAdapter

        adapter = FakeAdapter()
    return Gateway(adapter, cfg)


async def connect() -> Gateway:
    global _gateway
    _gateway = build()
    log.info(
        "model gateway: adapter=%s model=%s",
        _gateway.adapter_name, _gateway.model_name,
    )
    return _gateway


async def disconnect() -> None:
    global _gateway
    if _gateway is not None:
        await _gateway.close()
        _gateway = None


def gateway() -> Gateway:
    if _gateway is None:
        raise RuntimeError("gateway not initialised")
    return _gateway


def status() -> dict:
    """
    For /health. Says what is configured, never whether a key is valid — a
    health endpoint that proves credentials on every poll bills for it.
    """
    cfg = settings()
    return {
        "adapter": cfg.adapter,
        "model": "fake" if cfg.adapter == "fake" else cfg.model,
        "base_url": cfg.base_url if cfg.uses_network else None,
        "api_key_present": bool(cfg.api_key),
        "temperature": cfg.temperature,
        "seed": cfg.seed,
        # MDL-8 has landed; every prompt is projected, scrubbed and fenced
        # before it reaches an adapter, and the gateway still refuses anything
        # not explicitly marked. Reported so the console can show which path is
        # live rather than asserting it in a doc nobody opens.
        "redaction": "enforced",
    }
