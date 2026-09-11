"""
Model configuration, resolved once at startup.

Read from the environment here and nowhere else. A module that reads
`os.getenv` at call time can be given a different key mid-process and nothing
will notice; resolving once means a misconfiguration is a boot failure rather
than an intermittent one.

docs/IMPL.md §10 records the provider decision and what still needs verifying
against the real Sarvam API surface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised at startup. Never at request time."""


@dataclass(frozen=True)
class ModelSettings:
    adapter: str
    api_key: str
    base_url: str
    model: str
    timeout_s: float
    max_tokens: int
    max_retries: int
    temperature: float
    seed: int | None

    @property
    def uses_network(self) -> bool:
        return self.adapter != "fake"


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


ADAPTERS = ("fake", "sarvam")


def load() -> ModelSettings:
    adapter = os.getenv("MODEL_ADAPTER", "fake").strip().lower()
    if adapter not in ADAPTERS:
        raise ConfigError(
            f"MODEL_ADAPTER must be one of {ADAPTERS}, got {adapter!r}"
        )

    key = os.getenv("SARVAM_API_KEY", "").strip()

    # Fail at boot, not on the first operator question. An API-key typo that
    # surfaces as a degraded answer three hours later is worse than one that
    # stops the container.
    if adapter == "sarvam" and not key:
        raise ConfigError(
            "MODEL_ADAPTER=sarvam but SARVAM_API_KEY is empty. "
            "Set it in .env, or set MODEL_ADAPTER=fake to run without a provider."
        )

    seed_raw = os.getenv("MODEL_SEED", "").strip()

    return ModelSettings(
        adapter=adapter,
        api_key=key,
        base_url=os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1").rstrip("/"),
        model=os.getenv("SARVAM_MODEL", "sarvam-105b"),
        timeout_s=_float("MODEL_TIMEOUT_S", 60.0),
        max_tokens=_int("MODEL_MAX_TOKENS", 4096),
        max_retries=_int("MODEL_MAX_RETRIES", 1),
        temperature=_float("MODEL_TEMPERATURE", 0.0),
        seed=int(seed_raw) if seed_raw else None,
    )


_settings: ModelSettings | None = None


def settings() -> ModelSettings:
    global _settings
    if _settings is None:
        _settings = load()
    return _settings


def reset() -> None:
    """Test seam. Not called by the application."""
    global _settings
    _settings = None
