"""
Generate TypeScript types for the console from the Pydantic IR.

Run: python scripts_gen_types.py > ../ui/src/types/ir.generated.ts

The point of the FastAPI port was that the IR is declared once. This script is
what makes that true across the language boundary: the console's types are
derived from the same model the API validates against and the planner is handed,
so client and server cannot drift.
"""
from __future__ import annotations

import sys
from enum import Enum

from app.core import ir


def emit_enum(name: str, e: type[Enum]) -> str:
    members = "\n".join(f"  | '{m.value}'" for m in e)
    return f"export type {name} =\n{members}\n"


def main() -> None:
    out = [
        "/**",
        " * GENERATED — do not edit.",
        " * Source: api/app/core/ir.py.  Regenerate: python api/scripts_gen_types.py",
        " *",
        " * The IR is declared once, in Pydantic. These types are derived from it, so",
        " * the console and the API cannot disagree about the contract.",
        " */",
        "",
    ]
    for name, obj in vars(ir).items():
        if isinstance(obj, type) and issubclass(obj, Enum) and obj is not Enum:
            out.append(emit_enum(name, obj))
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
