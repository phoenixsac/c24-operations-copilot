"""
MDL-2 — Sarvam AI adapter.

`SARVAM_BASE_URL` ends in `/v1`, so this speaks the OpenAI-compatible chat
completions shape. httpx directly rather than a vendor SDK: the surface used
here is one POST and three response fields, and a dependency that hides which
fields are being read makes the F7 swap harder rather than easier.

VERIFIED against the live endpoint, 2026-09-10 — see docs/IMPL.md §10:

  * `response_format: json_schema` with `strict: true` WORKS. Replies are
    well-formed and respect an enum. The planner can rely on the shape; it still
    validates the contents.
  * It is a REASONING model. `message.content` is null while it thinks and the
    thinking lands in `message.reasoning_content`. `max_tokens` is a budget over
    both, so a small budget returns `finish_reason: "length"` and an empty
    answer — a 256-token cap produced 256 reasoning tokens and no content.
    Hence a 4096 floor and the explicit empty-content check below.
  * `reasoning_effort` accepts 'low' | 'medium' | 'high'. There is no 'none',
    so reasoning cannot be switched off.
  * `temperature: 0` plus a fixed `seed` DOES NOT give identical replies. Two
    identical requests returned different shapes. C1/C2 cannot be met by asking
    the provider nicely — docs/IMPL.md §10.

Every failure path raises ModelError. This adapter never returns a degraded
answer, because deciding what a failure means belongs to the gateway.
"""

from __future__ import annotations

import time

import httpx

from app.model.base import (
    ModelError,
    ModelReply,
    ModelRequest,
    ModelTimeout,
    ModelUnavailable,
)
from app.model.config import ModelSettings


# Below this, the model spends the whole budget thinking and returns nothing.
# Measured floor for a one-line classification is ~1000 completion tokens.
MIN_MAX_TOKENS = 4096


class SarvamAdapter:
    name = "sarvam"

    def __init__(self, cfg: ModelSettings) -> None:
        self._cfg = cfg
        self._client = httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=httpx.Timeout(cfg.timeout_s),
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
        )

    def _payload(self, req: ModelRequest) -> dict:
        body: dict = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "max_tokens": max(
                req.max_tokens or self._cfg.max_tokens, MIN_MAX_TOKENS
            ),
            "temperature": (
                self._cfg.temperature if req.temperature is None else req.temperature
            ),
        }
        # Sent, and demonstrably not honoured. Kept because it costs nothing and
        # a future model version may respect it; determinism is enforced above
        # this layer, not requested from below it.
        if self._cfg.seed is not None:
            body["seed"] = self._cfg.seed
        if req.reasoning_effort:
            body["reasoning_effort"] = req.reasoning_effort
        if req.stop:
            body["stop"] = req.stop
        if req.json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ir",
                    "schema": req.json_schema,
                    "strict": True,
                },
            }
        return body

    async def complete(self, req: ModelRequest) -> ModelReply:
        started = time.monotonic()
        try:
            res = await self._client.post("/chat/completions", json=self._payload(req))
        except httpx.TimeoutException as exc:
            raise ModelTimeout(f"sarvam timed out after {self._cfg.timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"sarvam unreachable: {exc}") from exc

        # 429 and 5xx are worth another attempt; 4xx is a bug in our request and
        # retrying it just spends the budget twice.
        if res.status_code == 429 or res.status_code >= 500:
            raise ModelUnavailable(
                f"sarvam returned {res.status_code}: {res.text[:200]}"
            )
        if res.status_code >= 400:
            raise ModelError(
                f"sarvam rejected the request ({res.status_code}): {res.text[:200]}"
            )

        try:
            data = res.json()
            choice = data["choices"][0]
            message = choice["message"]
            text = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            finish = choice.get("finish_reason", "stop")
        except (KeyError, IndexError, ValueError) as exc:
            raise ModelError(f"sarvam returned an unreadable body: {exc}") from exc

        # A 200 with no content is the model's characteristic failure: it thought
        # until the budget ran out. Returning "" here would look like a model
        # that had nothing to say, and the caller would treat an empty string as
        # an answer. Raise instead, so it degrades like any other failure (F4).
        # Two shapes of the same failure, both arriving as HTTP 200.
        #
        # Empty content: it reasoned until the budget ran out and never spoke.
        # Truncated content: it started speaking and was cut off mid-token —
        # observed live as `{"shape": "lookup"` with the closing brace missing.
        #
        # The truncated case is the more dangerous one. Invalid JSON is caught
        # downstream, but a reply clipped at a plausible boundary could parse
        # into a valid-looking object that omits fields the model intended to
        # send. `finish_reason` is the only reliable signal that happened, so it
        # is checked here rather than inferred from the text.
        if finish == "length":
            raise ModelUnavailable(
                f"sarvam hit the token budget (content={len(text)} chars, "
                f"reasoning={len(reasoning)} chars). Reply is unusable whether "
                "or not it parses — raise max_tokens for this stage."
            )
        if not text.strip():
            raise ModelUnavailable(
                f"sarvam returned no content (finish_reason={finish}, "
                f"{len(reasoning)} chars of reasoning)."
            )

        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        latency_ms = int((time.monotonic() - started) * 1000)

        return ModelReply(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            model=data.get("model", self._cfg.model),
            latency_ms=latency_ms,
            stage=req.stage,
            # Claimed only when a schema was asked for AND the reply is non-empty
            # JSON-ish. The planner still validates; this only decides whether a
            # failure is worth retrying with a repair prompt.
            schema_enforced=bool(req.json_schema) and text.strip().startswith("{"),
            finish_reason=finish,
            # The API does not always populate completion_tokens_details, so fall
            # back to a chars/4 estimate rather than reporting a confident zero.
            reasoning_tokens=int(
                details.get("reasoning_tokens") or (len(reasoning) // 4)
            ),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        """Startup reachability check. Never called per request."""
        try:
            await self.complete(
                ModelRequest(
                    stage="ping",
                    system="Reply with the single word: ok",
                    user="ping",
                    reasoning_effort="low",
                )
            )
            return True
        except ModelError:
            return False
