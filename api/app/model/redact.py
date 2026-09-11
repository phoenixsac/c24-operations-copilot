"""
MDL-8 — redaction. docs/INVARIANTS.md H2–H6, and ADR-017.

Five layers, weakest last. That ordering is the design: pattern matching is the
layer people think of first and it is the one carrying the least weight here.

  1. PROJECTION      PII columns are never selected into a prompt at all.
  2. PSEUDONYMISATION entities become stable handles — `customer:c_8821`.
  3. SCRUB           free text passes a curated regex sweep.
  4. FAIL CLOSED     anything still matching is dropped, never sent.
  5. GOLDEN TEST     no assembled prompt matches a PII pattern (eval, not runtime).

Layer 1 is why layer 3 can be a regex rather than a NER model: names never reach
a prompt, because the column is not in the SELECT. Presidio's advantage is name
detection, which we do not need — ADR-017.

The output of `redact()` is the ONLY thing allowed past the gateway. Callers
mark the request `redacted=True`; the gateway refuses otherwise (ADR-016).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Layer 1 — projection.
#
# The allowlist is per table, and it is an allowlist rather than a denylist on
# purpose: a column added to the schema next month is excluded by default
# instead of leaking until someone remembers to deny it. H2.
# ---------------------------------------------------------------------------

PROMPT_SAFE_COLUMNS: dict[str, frozenset[str]] = {
    "orders": frozenset({"id", "state", "amount", "created_at", "updated_at"}),
    "ticket": frozenset({"id", "order_id", "state", "priority", "reopen_count",
                         "created_at", "first_response_at", "resolved_at",
                         "resolution_code", "resolved_by"}),
    "payment": frozenset({"id", "kind", "status", "captured_at"}),
    "refund": frozenset({"id", "payment_id", "status"}),
    "rc_case": frozenset({"id", "status", "opened_at"}),
    "refurb_job": frozenset({"id", "status", "promised_at", "completed_at"}),
    "delivery": frozenset({"id", "status", "attempt_count", "slot_at"}),
    "order_event": frozenset({"id", "from_state", "to_state", "at"}),
    "vehicle": frozenset({"id", "make", "model", "year", "km", "listing_status"}),
    "customer": frozenset({"id", "city_code", "created_at"}),
    "ticket_message": frozenset({"id", "direction", "channel", "at",
                                 "injection_flagged"}),
}

# Columns that must never appear in a prompt regardless of table. Redundant with
# the allowlist by construction — kept because a redundant check that fires is
# how you learn the allowlist was edited wrongly. H2.
NEVER_IN_PROMPT = frozenset({
    "name", "phone", "email", "address", "reg_no", "vin", "account_no",
    "ifsc", "upi_id", "pan", "aadhaar", "blocked_reason", "body",
    "resolution_evidence", "subject",
})


class RedactionError(RuntimeError):
    """Layer 4. Raised instead of sending. H5."""


def project(table: str, row: dict) -> dict:
    """
    Layer 1. Returns only the columns that may be seen by a model.

    An unknown table yields `{}` rather than the row: a table nobody has
    classified is not a table whose columns we can vouch for.
    """
    allowed = PROMPT_SAFE_COLUMNS.get(table)
    if not allowed:
        return {}
    return {k: v for k, v in row.items() if k in allowed and k not in NEVER_IN_PROMPT}


# ---------------------------------------------------------------------------
# Layer 3 — free-text scrub.
#
# Ordered most-specific first: Aadhaar before the generic long-digit rule, or
# the generic one eats it and the label in the transcript is wrong.
#
# Known weakness, recorded rather than hidden: these are English- and
# format-anchored. Devanagari-script PII will pass straight through. ADR-012.
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AADHAAR", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("REG_NO", re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4}\b")),
    ("PHONE", re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("UPI", re.compile(r"\b[\w.-]{3,}@(?:okhdfcbank|okaxis|oksbi|ybl|paytm|upi)\b")),
    ("ACCOUNT", re.compile(r"\b\d{11,18}\b")),
]


def scrub(text: str) -> tuple[str, list[str]]:
    """Layer 3. Returns the scrubbed text and the labels that fired."""
    hits: list[str] = []
    for label, pat in _PATTERNS:
        text, n = pat.subn(f"[{label}_REDACTED]", text)
        if n:
            hits.append(label)
    return text, hits


def assert_clean(text: str) -> None:
    """
    Layer 4/5. Raises rather than sending.

    Called on the fully assembled prompt, after every other layer. If this ever
    fires in production it means a layer above it has a hole, so the correct
    behaviour is to fail the request rather than to scrub again and continue —
    a silent second scrub would hide the hole permanently.
    """
    for label, pat in _PATTERNS:
        if pat.search(text):
            raise RedactionError(
                f"assembled prompt still matches {label} after redaction — "
                "refusing to send (H5)"
            )


# ---------------------------------------------------------------------------
# Layer 2 — pseudonymisation, and the untrusted-content wrapper.
# ---------------------------------------------------------------------------

# Text from customers, third-party feeds and stored evidence is DATA, never
# INSTRUCTIONS. The delimiter is repeated in the system prompt so the boundary
# is stated twice — once structurally, once in the instruction. J4.
UNTRUSTED_OPEN = "<<<UNTRUSTED_CONTENT>>>"
UNTRUSTED_CLOSE = "<<<END_UNTRUSTED_CONTENT>>>"

# Cheap, high-recall, deliberately not clever. J10 says flag and count, not
# block: a false negative must be survivable, which it is — the model cannot
# name an action outside the ActionId enum no matter what it is told (J1).
_INJECTION_CUES = re.compile(
    r"(ignore (?:all |any )?previous|disregard (?:the )?above|system\s*:|"
    r"you are now|new instructions?|reveal|disclose all|approve this|"
    r"auto-?resolve immediately|prompt|jailbreak)",
    re.I,
)


def wrap_untrusted(text: str) -> tuple[str, bool]:
    """
    Layer 2/3 applied to free text, then fenced.

    Returns the safe-to-embed string and whether injection cues were seen. The
    caller surfaces the flag; nothing is silently stripped, because a stripped
    injection is one nobody learns about. J10.
    """
    flagged = bool(_INJECTION_CUES.search(text))
    cleaned, _ = scrub(text)
    # A crafted string containing our own delimiter would otherwise close the
    # fence early and escape into instruction context.
    cleaned = cleaned.replace(UNTRUSTED_OPEN, "").replace(UNTRUSTED_CLOSE, "")
    return f"{UNTRUSTED_OPEN}\n{cleaned}\n{UNTRUSTED_CLOSE}", flagged


@dataclass
class RedactedPrompt:
    """What the gateway is allowed to receive."""

    system: str
    user: str
    injection_flagged: bool = False
    scrub_hits: list[str] = field(default_factory=list)


def scrub_operator_turn(query: str) -> tuple[str, list[str]]:
    """
    The operator's own words are not exempt.

    An agent searching by registration number types the plate, and it is still
    a vehicle identifier leaving for a third-party API. Eval D-06 hit this: the
    query contained `MH12AB1234`, layer 4 fired, and the request was refused —
    correctly, because nothing had scrubbed it.

    Scrubbing it costs nothing downstream. The router is classifying a shape and
    the planner is choosing record types; neither needs the literal plate,
    because entity resolution reads it from the raw query by regex before any
    prompt is built (ADR-024). The model never needed it.
    """
    return scrub(query)


def finalise(system: str, user: str, *, injection_flagged: bool = False,
             scrub_hits: list[str] | None = None) -> RedactedPrompt:
    """Last gate before the gateway. Runs layer 4 on both halves."""
    assert_clean(system)
    assert_clean(user)
    return RedactedPrompt(
        system=system,
        user=user,
        injection_flagged=injection_flagged,
        scrub_hits=scrub_hits or [],
    )
