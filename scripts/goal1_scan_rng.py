"""List every generator draw site in synthetic.py, grouped by enclosing function.

ASCII only. Read-only scan; no rendering.
"""
from __future__ import annotations

import ast
import io
import os
import sys

SRC = os.environ.get("AP_SRC") or os.path.join(
    os.environ.get("AP_ROOT", r"G:\pipip\temp"), "src",
    "aesthetic_prism", "data", "synthetic.py")

DRAWS = {
    "choice", "random", "uniform", "integers", "normal",
    "standard_normal", "gumbel", "lognormal", "permutation", "shuffle",
}


def main() -> None:
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        sites = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in DRAWS:
                    sites.append((node.lineno, node.func.attr))
        if sites:
            print(f"def {fn.name}  (line {fn.lineno})")
            for ln, nm in sorted(sites):
                print(f"    L{ln:<5} rng.{nm}")
    print("--- end ---")


if __name__ == "__main__":
    sys.exit(main())
