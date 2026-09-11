"""
The model boundary. docs/IMPL.md §5.

Everything provider-specific lives in this package and nowhere else. That is the
whole design: docs/INVARIANTS.md F7 says no provider is structurally required,
and the only way to keep that true is for the swap to be one directory.

    base.py     MDL-1  the interface — ModelRequest, ModelReply, ModelAdapter
    sarvam.py   MDL-2  Sarvam AI, OpenAI-compatible chat completions
    fake.py     MDL-3  fixtures, no network — the default, and what evals run on
    gateway.py  MDL-4  the only origin of a model call: retries, budgets, trace
    config.py          environment, resolved once at startup
"""

from app.model.base import (
    ModelAdapter,
    ModelError,
    ModelReply,
    ModelRequest,
    ModelTimeout,
    ModelUnavailable,
)
# Note: the `gateway` accessor is deliberately NOT re-exported here. Binding the
# name at package level would shadow the `app.model.gateway` submodule, and
# `from app.model import gateway` would silently hand back the function.
from app.model.gateway import Gateway, RedactionRequired

__all__ = [
    "Gateway",
    "ModelAdapter",
    "ModelError",
    "ModelReply",
    "ModelRequest",
    "ModelTimeout",
    "ModelUnavailable",
    "RedactionRequired",
]
