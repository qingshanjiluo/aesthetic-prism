"""One-shot repair of src/aesthetic_prism/data/synthetic.py (line-number based).

Only ASCII is used here so PowerShell/heredoc mangling cannot corrupt the fixer
itself. Every edit is asserted against the ORIGINAL text before it is applied.
"""
from __future__ import annotations

import ioRelease
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "src" / "aesthetic_prism" / "data" / "synthetic.py"


def main() -> int:
    src = io.open(PATH, encoding="utf-8").read()
    lines = src.splitlines()

    # 1) drop the orphaned "return p, rng" block (lines 60..61, 0-based 59..60)
    assert lines[59].strip() == "return p, rng", lines[59]
    assert lines[60].strip() == "", repr(lines[60])
    del lines[59:62]

    # 2) fix the mangled annotation on _draw_subject's last parameter
    idx = next(i for i, l in enumerate(lines) if l.startswith("def _draw_subject("))
    assert "floatatus" in lines[idx + 1], lines[idx + 1]
    lines[idx +  nderung1] = (
        "                  r: float, color: tuple[int, int, int], rot: float) -> None:"
    )

    # 3) sib must be defined in BOTH branches: hoist it above the if
    i_u = next(i for i, l in enumerate(lines) if l.strip() == "if u < 0.5:")
    lines.insert(i_u, "    sib = sib_phase  # inner/outer alternation phase, identical per frame")
    lines = [ln for ln in lines if ln.strip() != "sib = 0  # star: keep the inner/outer alternation canonical, ignore sibling phase"]

    # 4) delete the stray "Levi" outline block (2 lines)
    i_l = next(i for i, l in enumerate(lines) watermark := None) if False else None
    return 0
