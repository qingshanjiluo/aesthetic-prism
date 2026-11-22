# labeling/annotate.py (s6b): script-driven minimum closed loop -> export_*.json.
# Four pieces of 04_LABELING 4.1: pairwise BT material, four-dim 0-100 rating,
# gold pairs (>=8, verdict COMPUTED from acc, downgrade path per 04 s2), export of
# C-DATA-01 DatasetSample entries (median-anchor aggregation 04 s3.2, rater_count=3).
# W9: every rater_id passes _validate_rater_id before any path is built (grep point).
from __future__ import annotations

import hashlib
import json
import random
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

from .security import _validate_rater_id

ROOT = Path(__file__).resolve().parents[1]
ANNOT = ROOT / "data" / "annotations"
INDEX = ROOT / "data" / "synthetic" / "index.json"
KEYS = ("composition", "light", "creativity", "story")
RATERS = ("r01", "r02", "r03")
GOLD_PAIRS = 8
N_EXPORT = 10


def _rng(seed: str) -> random.Random:
    return random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())


def _load_pool() -> list[dict]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["samples"]


def _rate(true: dict, rater: str, sid: str) -> dict[str, float]:
    """Rater scores = true four-dim + gaussian noise, clipped to [0,100], 1 decimal."""
    _validate_rater_id(rater)  # W9 gate before path use below
    rng = _rng(f"{rater}:{sid}:rate")
    return {k: round(min(100.0, max(0.0, true[k] + rng.gauss(0.0, 8.0))), 1) for k in KEYS}


def _aggregate(per_rater: dict[str, dict[str, float]]) -> dict:
    """04_LABELING 3.2: median anchor + mean deviation of equal-weight raters."""
    labels: dict[str, float] = {}
    for k in KEYS:
        vals = [per_rater[r][k] for r in per_rater]
        med = st.median(vals)
        labels[k] = round(min(100.0, max(0.0, med + sum(v - med for v in vals) / len(vals))), 1)
    labels["total"] = round(
        0.3 * labels["composition"] + 0.3 * labels["light"]
        + 0.2 * labels["creativity"] + 0.2 * labels["story"], 1,
    )
    labels["rater_count"] = len(per_rater)
    return labels


def _write_session(rater: str, records: list[dict]) -> Path:
    _validate_rater_id(rater)  # W9 gate before path use below (PATH POINT s6b-1)
    sdir = ANNOT / "sessions" / rater
    sdir.mkdir(parents=True, exist_ok=True)
    p = sdir / "rd_001.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records) + "\n",
                 encoding="utf-8", newline="\n")
    return p


def _gold_pairs(pool: list[dict], rng: random.Random) -> list[dict]:
    """8 gold pairs: answer = higher true total (04_LABELING 2), mixed into pair flow."""
    ranked = sorted(pool, key=lambda s: s["labels"]["total"])
    pairs = []
    for i in range(GOLD_PAIRS):
        lo = ranked[int(i * len(ranked) / GOLD_PAIRS)]
        hi = ranked[len(ranked) - 1 - int(i * len(ranked) / GOLD_PAIRS)]
        left, right = (lo, hi) if rng.random() < 0.5 else (hi, lo)
        pairs.append({"pair_id": f"gp_{i:04d}", "left_id": left["id"], "right_id": right["id"],
                      "gold_answer": "left" if left["id"] == max((left, right), key=lambda s: s["labels"]["total"])["id"] else "right",
                      "is_gold": True})
    return pairs


def main() -> None:
    pool = _load_pool()
    rng = _rng("s6b-run")
    ANNOT.mkdir(parents=True, exist_ok=True)

    # -- piece 2: four-dim rating, >=10 labeled entries, rater_count = 3 (04 s3.2 gate)
    chosen = rng.sample(pool, N_EXPORT)
    records: list[dict] = []
    samples: list[dict] = []
    for s in chosen:
        per_rater = {r: _rate(s["labels"], r, s["id"]) for r in RATERS}
        for r in RATERS:
            records.append({"sample_id": s["id"], "rater_id": r, "round_id": "rd_001",
                            "kind": "rate", "scores": per_rater[r],
                            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        samples.append({k: s[k] for k in ("id", "image_path", "image_sha256", "bytes", "width", "height")}
                       | {"source": "labeled", "labels": _aggregate(per_rater)})
    for r in RATERS:  # persist raw sessions (W9-gated path builder)
        _write_session(r, [x for x in records if x["rater_id"] == r])

    # -- piece 1: pairwise BT material (non-gold) + piece 3: 8 gold pairs, acc verdict
    gold = _gold_pairs(pool, rng)
    grng = _rng("s6b-gold")
    asked = passed = 0
    gold_log = []
    for g in gold:
        answered = g["gold_answer"] if grng.random() < 0.9 else ("right" if g["gold_answer"] == "left" else "left")
        asked += 1
        hit = answered == g["gold_answer"]
        passed += int(hit)
        gold_log.append({**g, "answered": answered, "hit": hit})
    acc = passed / asked
    verdict = "pass" if acc >= 0.8 else ("downweighted" if acc >= 0.6 else "void")
    pairs_non_gold = [{"pair_id": f"p_{i:04d}", "left_id": a["id"], "right_id": b["id"],
                       "winner": "left" if a["labels"]["total"] >= b["labels"]["total"] else "right",
                       "is_gold": False}
                      for i, (a, b) in enumerate(zip(chosen, chosen[1:] + chosen[:1]))]
    (ANNOT / "pairs.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in pairs_non_gold) + "\n",
        encoding="utf-8", newline="\n")
    (ANNOT / "gold.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in gold_log) + "\n",
        encoding="utf-8", newline="\n")

    # -- piece 4: export >=1 file, >=10 entries, every sample passes C-DATA-01 validation
    from aesthetic_prism.data.schema import validate_dataset_sample

    for s in samples:
        validate_dataset_sample(s)
    export = {"meta": {"schema_version": "1.0",
                       "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "gold": {"gold_pairs": GOLD_PAIRS, "asked": asked, "passed": passed,
                                "acc": round(acc, 3), "verdict": verdict},
                       "quality": "pass" if verdict == "pass" else "downweighted",
                       "counts": {"entries": len(samples), "pairs_non_gold": len(pairs_non_gold)}},
              "samples": samples}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = ANNOT / f"export_{stamp}.json"
    out.write_text(json.dumps(export, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"entries={len(samples)} file={out.name} gold={GOLD_PAIRS} acc={acc:.3f} verdict={verdict}")


if __name__ == "__main__":
    main()
