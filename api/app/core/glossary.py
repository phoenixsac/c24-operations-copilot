"""
The domain glossary. Curated, static, and quoted rather than composed.

WHY THIS EXISTS. Asked "what's the difference between token paid and full
paid?", the system did one of two things and both were wrong: refused outright
(no shape covers a question about the schema), or — when the phrasing dragged it
into `diagnosis` — improvised. It produced "full paid is the payment kind that
was captured to move it forward", which is plausible, unverified, and
indistinguishable from a real definition to the person reading it.

The fix follows the same rule as everywhere else in this system: the model gets
established text, not raw material it has to reason over. The synthesiser
receives violations instead of records so it cannot invent a cause; it receives
definitions instead of column names so it cannot invent a meaning.

WHAT THIS IS NOT. Not knowledge in a system prompt. A definition recalled from
training is unattributable and cannot be corrected; a definition retrieved from
here has a source, a version, and an owner. The prompt instruction is "quote
these", and the fact block carries them as data alongside the records.

SOURCE. Definitions are derived from `docs/DOMAIN_v2.md` — §1 entities, §2 the
order state machine, §3 the ticket lifecycle, §4 invariants → rules. When the
schema changes, this file changes with it, and `test_glossary_covers_enums`
fails until it does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Term:
    """
    One entry. `definition` is written to be read aloud to a colleague, and to
    survive being quoted verbatim into an answer.
    """

    term: str
    definition: str
    # "state" | "entity" | "concept" | "rule" | "role"
    kind: str
    # Other terms worth reading next. Kept short; a glossary that fans out into
    # everything is one nobody finishes.
    see_also: tuple[str, ...] = field(default_factory=tuple)


# Populated in glossary_terms.py to keep the lookup logic readable and the
# content reviewable on its own.
from app.core.glossary_terms import ALIASES, TERMS  # noqa: E402


# A question that wants a definition rather than a record. "What is TOKEN_PAID"
# is answerable from this file alone; "what is the status of 4521" is not, and
# the difference is the presence of a lookupable identifier, not the wording.
DEFINITIONAL = re.compile(
    r"\b(what (?:is|are|does|do)|what'?s|whats|difference between|"
    r"mean(?:s|ing)?|explain|define|stand for|how does .* work)\b",
    re.I,
)


# A concrete identifier turns a definitional-sounding question into a records
# question. "What is TOKEN_PAID" wants this file; "what is the status of order
# 4521" wants the database, and both open with "what is".
#
# Kept as a local pattern rather than importing the planner's extractor: `core`
# does not depend on `agent`, and a glossary that needs the agent layer to
# decide whether it applies is not a core module any more.
_IDENTIFIER = re.compile(
    r"(?:\bTKT-\d{3,6}\b"
    r"|#\d{3,6}\b"
    r"|\border\s+\d{3,6}\b"
    r"|\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4}\b)",
    re.I,
)


def names_a_record(query: str) -> bool:
    return _IDENTIFIER.search(query) is not None


# Words allowed to trail a term in a genuinely definitional question. Anything
# else after the term means the sentence is asking about that thing rather than
# asking what the word means.
_DEFINITIONAL_TAIL = re.compile(
    r"^[\s\W]*(?:"
    r"mean(?:s|ing)?|exactly|precisely|here|in this (?:system|context)|"
    r"again|really|actually|and|or|vs|versus"
    r"|[\s\W]"
    r")*$",
    re.I,
)


def _asks_about_the_word(query: str) -> bool:
    """
    Does the sentence stop at the term, or keep going?

    "What is TOKEN_PAID?" stops — the term is the whole object of the question.
    "What is the customer asking for?" keeps going, and `asking for` is the real
    question: it is about a record's contents, not about what the word
    `customer` means.

    Both open with "what is" and both mention a glossary term, so the phrasing
    test alone cannot separate them. This looks at what follows the last term
    matched, allowing only the filler a definitional question actually ends on.

    Found live: "What is the customer asking for?", asked with a ticket open,
    returned the glossary definition of `customer` — a correct answer to a
    question nobody asked.
    """
    hits = find(query)
    if not hits:
        return False

    haystack = query.replace("_", " ")
    end = 0
    for term in hits:
        m = re.search(
            r"\b" + re.escape(term.term.replace("_", " ")) + r"\b", haystack, re.I
        )
        if m:
            end = max(end, m.end())
    return _DEFINITIONAL_TAIL.match(haystack[end:]) is not None


def wants_definition(query: str) -> bool:
    """
    Definitional phrasing, no identifier, and nothing trailing the term.

    The first version tested only the phrasing, which meant "what is the status
    of order 4521?" pulled in the definition of "order" — the word is a glossary
    key and the sentence contains it. Correct behaviour there is to say nothing:
    the operator is asking about a row, not about vocabulary.

    The third clause closes the same hole for sentences carrying no identifier at
    all, where the subject is the open ticket rather than a quoted id.
    """
    return (
        DEFINITIONAL.search(query) is not None
        and not names_a_record(query)
        and _asks_about_the_word(query)
    )


def canonical(word: str) -> str | None:
    """Map a surface form to a term key. `TOKEN_PAID`, "token paid", "token" → same entry."""
    key = re.sub(r"[\s_-]+", "_", word.strip().lower())
    if key in TERMS:
        return key
    return ALIASES.get(key)


def find(text: str) -> list[Term]:
    """
    Every glossary term mentioned in a piece of text, in the order they appear.

    Matches the longest form first so "token paid" wins over "payment" when both
    would match — otherwise a two-word term is shadowed by one of its halves and
    the answer defines the wrong thing.
    """
    haystack = text.replace("_", " ")
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    claimed: list[tuple[int, int]] = []

    for surface in sorted(
        [*TERMS.keys(), *ALIASES.keys()],
        key=lambda s: len(s),
        reverse=True,
    ):
        pattern = r"\b" + re.escape(surface.replace("_", " ")) + r"\b"
        m = re.search(pattern, haystack, re.I)
        if not m:
            continue

        # A shorter term inside a longer one already matched is not a second
        # mention. "what is rc_transfer_stall" contains "rc", and without this
        # the answer led with the definition of an RC case — correct about a
        # term the operator did not ask about. Longest-match has to be enforced
        # over spans, not just tried in length order.
        if any(cs <= m.start() < ce for cs, ce in claimed):
            continue

        key = canonical(surface)
        if key and key not in seen:
            seen.add(key)
            claimed.append(m.span())
            hits.append((m.start(), key))

    return [TERMS[k] for _, k in sorted(hits)]


def for_prompt(query: str, limit: int = 4) -> list[str]:
    """
    Definition lines for the fact block, or nothing.

    Only for questions that actually ask for a meaning. Attaching the glossary
    to every prompt would cost tokens on every diagnosis and, worse, give the
    model more domain vocabulary to build plausible-sounding causal stories out
    of — which is the failure ADR-035 exists to prevent. Definitions are served
    where they are asked for.

    Capped at `limit` so "explain this order" cannot drag the whole glossary in.
    """
    if not wants_definition(query):
        return []
    return [f"{t.term}: {t.definition}" for t in find(query)[:limit]]
