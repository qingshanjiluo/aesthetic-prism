"""Teacher/student parameter report (W-3-01 deliverable 8/8).

Budget authority: docs/01_ARCH.md section 4 (teacher <= 25,000,000;
student raw < 10,000,000 before stage-6 pruning/INT8) and 00_PRD G5.

CLI (Git sh, from project root):
    python -m aesthetic_prism.model.params
    python -m aesthetic_prism.model.params --out reports/params.json

Exit code 0 = all budgets satisfied; 1 = budget violation (gate-relevant).
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .model import HAPNet, student, teacher

TEACHER_BUDGET = 25_000_000  # 01_ARCH section 4 / 00_PRD G5 (<= 25M)
STUDENT_BUDGET = 10_000_000  # 08_ACCEPTANCE S6-01 (hard, < 10M before prune)


def count_params(model: HAPNet) -> int:
    """sum(p.numel() for p in model.parameters()) — the 01_ARCH budget formula."""
    return sum(p.numel() for p in model.parameters())


def report() -> dict[str, int]:
    """{"teacher": int, "student": int} raw param counts (int8 bytes come at stage 6)."""
    return {"teacher": count_params(teacher()), "student": count_params(student())}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aesthetic_prism.model.params",
        description="Print HAP-Net teacher/student parameter counts against budgets.",
    )
    parser.add_argument("--out", default=None, help="optional JSON output path (reports/params.json)")
    args = parser.parse_args(argv)

    data = report()
    teacher_n, student_n = data["teacher"], data["student"]
    lines = [
        f"teacher  {teacher_n:>12,}  <= {TEACHER_BUDGET:,}  {'OK' if teacher_n <= TEACHER_BUDGET else 'FAIL'}",
        f"student  {student_n:>12,}  <  {STUDENT_BUDGET:,}  {'OK' if student_n < STUDENT_BUDGET else 'FAIL'}  (raw pre-prune; stage 6 prunes to <10M)",
    ]
    for line in lines:
        print(line)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Shape mirrors 01_ARCH section 4: student_int8_bytes is filled at stage 6.
        payload = {"teacher": teacher_n, "student": student_n, "student_int8_bytes": None}
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}")

    ok = teacher_n <= TEACHER_BUDGET and student_n < STUDENT_BUDGET
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
