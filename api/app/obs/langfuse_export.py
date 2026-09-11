"""
Langfuse exporter. Optional, self-hosted, off unless configured.

WHY LANGFUSE AND NOT AN OTEL EXPORTER. Three of its concepts already exist here
and the mapping is exact:

    langfuse session  ->  conversation_id   (the thread, ADR-033)
    langfuse user     ->  actor_id          (Priya / Tariq / Anil)
    langfuse score    ->  an eval case result

The third is the one that earns it. Pushing all 52 eval cases in as scores makes
"which cases pass on the fake adapter but fail live" a view rather than a diff
of two terminal scrollbacks — and that comparison is what has caught most of the
real bugs in this build.

SELF-HOSTED ONLY, and the code enforces nothing about that — you could point
`LANGFUSE_HOST` at their cloud. So it is stated here instead: a trace carries
the operator's question and resolved entity ids, and sending those to a third
party crosses the boundary `INVARIANTS.md` §H exists to describe. Run it in
compose next to Postgres.

WHAT IS SENT. Spans, timings, structured decisions, token counts. The prompt
text sent to a provider is already redacted (MDL-8) before it reaches the
gateway, and the operator's query is scrubbed on the way out here too — a
second store with a different retention policy is exactly where PII goes to be
forgotten about (H11).
"""

from __future__ import annotations

import logging
import os

from app.obs.trace import Trace

log = logging.getLogger("copilot.obs")

_client = None
_tried = False


def enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def client():
    """
    Built once, and never allowed to take the request down with it.

    An observability tool that can fail a user's request is worse than no
    observability tool. Every path here swallows and logs.
    """
    global _client, _tried
    if _tried:
        return _client
    _tried = True
    if not enabled():
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            base_url=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        )
        log.info("langfuse export enabled -> %s",
                 os.getenv("LANGFUSE_HOST", "http://localhost:3000"))
    except Exception as exc:  # import error, bad key, unreachable host
        log.warning("langfuse disabled: %s", exc)
        _client = None
    return _client


def export(trace: Trace, *, shape: str, refused: bool, model: str) -> None:
    """
    One Langfuse trace per answer, one observation per span.

    Model calls are sent as `generation` so token counts land in the right
    place; everything else is a `span`. The distinction matters for the cost
    view — on this provider reasoning tokens are most of the spend, and they
    only aggregate if the observation is typed correctly.
    """
    lf = client()
    if lf is None:
        return

    try:
        from langfuse import propagate_attributes

        from app.model.redact import scrub

        safe_query, _ = scrub(trace.query)

        # Trace-level attributes are a context manager in SDK v4, not a method
        # on the span. The published guide still shows `span.update_trace(...)`,
        # which does not exist on 4.15.2 — checked against the installed
        # package rather than the docs after the first attempt failed.
        with propagate_attributes(
            user_id=trace.actor,
            session_id=trace.conversation_id or trace.answer_id,
            tags=[shape, f"city:{trace.city}", model,
                  "refused" if refused else "answered"],
            metadata={"answer_id": trace.answer_id, "city": trace.city},
        ):
            with lf.start_as_current_observation(
                as_type="span", name=f"ask:{shape}", input=safe_query,
            ):
                for span in trace.spans:
                    with lf.start_as_current_observation(
                        as_type="span", name=span.name, metadata=span.detail,
                    ):
                        pass

                # Model calls are separate observations typed as `generation`,
                # so the prompt, the reply and the token split land where
                # Langfuse expects them. Emitted from the captured exchanges
                # rather than from spans because one stage can make several
                # calls — a planner repair retry is two, and both are worth
                # reading.
                for x in trace.exchanges:
                    tok = x.get("tokens") or {}
                    with lf.start_as_current_observation(
                        as_type="generation",
                        name=f"{x['stage']}#{x.get('attempt', 1)}",
                        model=x.get("model"),
                        # The prompt exactly as sent — post-redaction (MDL-8).
                        input=[
                            {"role": "system", "content": x.get("system", "")},
                            {"role": "user", "content": x.get("user", "")},
                        ],
                        output=(x.get("output") if x.get("output") is not None
                                else f"<no content: {x.get('error', 'unknown')}>"),
                        usage_details={
                            "input": tok.get("prompt", 0),
                            "output": tok.get("completion", 0),
                        },
                        metadata={
                            "finish_reason": x.get("finish_reason"),
                            "schema_enforced": x.get("schema_enforced"),
                            "latency_ms": x.get("latency_ms"),
                            # Most of the spend on this provider, and invisible
                            # unless broken out.
                            "reasoning_tokens": tok.get("reasoning", 0),
                            "error": x.get("error"),
                        },
                    ):
                        pass
        # Flushed per request rather than left to the batch timer.
        #
        # The SDK queues spans and ships them on a background schedule, which is
        # right for throughput and wrong for this: you ask a question, look at
        # the UI, and see nothing. Worse, a container restart between batches
        # drops them silently — which is exactly what happened on the first
        # attempt, and looked like a broken integration rather than a pending
        # one. A flush costs a local HTTP round trip on a request that already
        # took thirty seconds.
        lf.flush()
    except Exception as exc:
        # Never let the tracer break the answer it is tracing.
        log.warning("langfuse export failed: %s", exc)


def score(case_id: str, *, passed: bool, shape: str, live: bool,
          failures: list[str]) -> None:
    """
    One score per eval case. `live` distinguishes a provider run from a fake
    one, which is the comparison worth having.
    """
    lf = client()
    if lf is None:
        return
    try:
        lf.create_score(
            name="eval",
            value=1.0 if passed else 0.0,
            comment="; ".join(failures)[:500] or "pass",
        )
    except Exception as exc:
        log.warning("langfuse score failed: %s", exc)
