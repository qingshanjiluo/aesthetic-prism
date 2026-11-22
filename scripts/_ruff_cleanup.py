# One-shot ruff cleanup for the 12 remaining real violations.
# Pure ASCII source. All edits are surgical string replacements with assertions:
# if an anchor is missing the script aborts instead of silently no-op'ing.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILS: list[str] = []


def patch(rel: str, pairs: list[tuple[str, str]]) -> None:
    p = ROOT / rel
    t = p.read_text(encoding="utf-8")
    orig = t
    for old, new in pairs:
        if old not in t:
            FAILS.append(f"{rel}: anchor missing -> {old[:70]!r}")
            return
        t = t.replace(old, new)
    if t != orig:
        p.write_text(t, encoding="utf-8", newline="\n")
        print(f"[ok] {rel}")


# ---- 1) bench/ts_mae.py:91  E741 ambiguous name `l` ----
patch(
    "src/aesthetic_prism/bench/ts_mae.py",
    [("labs = [l for s, _, l in paths if s == sp]",
      "labs = [lab for s, _, lab in paths if s == sp]")],
)

# ---- 2) data/synthetic.py:148  SIM108 if/else -> ternary ----
patch(
    "src/aesthetic_prism/data/synthetic.py",
    [(
        '    if side is not None:  # side None -> column free, w moves mass centre instead\n'
        '        if side == "left":\n'
        '            gx = gx if gx < 0.5 else 1 - gx\n'
        '        else:\n'
        '            gx = gx if gx > 0.5 else 1 - gx\n',
        '    if side is not None:  # side None -> column free, w moves mass centre instead\n'
        '        # mirror the anchor into the requested half of the frame\n'
        '        gx = (gx if gx < 0.5 else 1 - gx) if side == "left" else (gx if gx > 0.5 else 1 - gx)\n',
    )],
)

# ---- 3) data/synthetic.py:174  RUF005 tuple concat -> unpack ----
patch(
    "src/aesthetic_prism/data/synthetic.py",
    [("a = color if len(color) == 4 else color + (230,)",
      "a = color if len(color) == 4 else (*color, 230)")],
)

# ---- 4) data/synthetic.py RUF046 x5 : int(round(x)) drops the redundant int() ----
patch(
    "src/aesthetic_prism/data/synthetic.py",
    [("sides = 3 + int(round(3 * (u / 0.5)))  # 3,4,5,6",
      "sides = 3 + round(3 * (u / 0.5))  # 3,4,5,6"),
     ("sides = 3 + int(round(3 * ((u - 0.5) / 0.5)))  # 3,4,5,6 star points",
      "sides = 3 + round(3 * ((u - 0.5) / 0.5))  # 3,4,5,6 star points")],
)

# ---- 5) serve/app.py:38  E402 : datetime import hoisted above the app import ----
patch(
    "src/aesthetic_prism/serve/app.py",
    [(
        "log = logging.getLogger(\"aesthetic_prism.serve\")\n"
        "\n"
        "# ---- \u6bb55 T-5-02\uff1a\u7ed3\u6784\u5316 JSON \u65e5\u5fd7\uff08stdout \u4e00\u884c\u4e00\u6761 JSON\uff09+ X-Request-ID ----\n"
        "import datetime as _dt\n",
        "import datetime as _dt\n"
        "\n"
        "log = logging.getLogger(\"aesthetic_prism.serve\")\n"
        "\n"
        "# ---- \u6bb55 T-5-02\uff1a\u7ed3\u6784\u5316 JSON \u65e5\u5fd7\uff08stdout \u4e00\u884c\u4e00\u6761 JSON\uff09+ X-Request-ID ----\n",
    )],
)

# ---- 6) eval.py:41,43  E702 semicolons -> separate statements ----
patch(
    "src/eval.py",
    [(
        "        gt_t.append(gt_total); pr_t.append(pr_total)\n",
        "        gt_t.append(gt_total)\n"
        "        pr_t.append(pr_total)\n",
    ),
     (
        "    gt = np.array(gt_t); pr = np.array(pr_t)\n",
        "    gt = np.array(gt_t)\n"
        "    pr = np.array(pr_t)\n",
    )],
)

print("FAILS=" + repr(FAILS))
raise SystemExit(1 if FAILS else 0)
