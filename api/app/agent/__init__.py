"""
The agentic layer. docs/IMPL.md §4.

    planner.py     AGT-1 (model router) + AGT-3 (planner) — NL to validated IR
    resolve.py     AGT-4 — IR entity refs to an RLS-scoped snapshot
    synthesise.py  AGT-5 — established facts to prose, checked before it ships
    tier2.py       OBS-5 — the auto-reply gate, structured state only

Six steps in fixed order, no cycles, and the model picks none of the
transitions. That is why there is no graph runtime here — ADR-007.
"""
