"""T-8-03：主动学习采样——四维方差 + 成对不确定性采样，产出标注队列。
读 artifacts/pseudo_labels.json（伪标签池：idx, scores, variance）或
data/pseudo/pool.json；按信息量排序取 top-N 写 data/annotations/active_queue.json。
"""
from __future__ import annotations

import json
import os
import sys

AP_ROOT = os.environ.get("AP_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.join(AP_ROOT, "src"))

QUEUE_PATH = os.path.join(AP_ROOT, "data", "annotations", "active_queue.json")
TOP_N = 50


def _load_pool() -> list[dict]:
    """池来源优先级：伪标签池 > 人工标注导出（samples 含 labels 打分）。"""
    for cand in (
        os.path.join(AP_ROOT, "artifacts", "pseudo_labels.json"),
        os.path.join(AP_ROOT, "data", "pseudo", "pool.json"),
    ):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                raw = json.load(f)
            return raw if isinstance(raw, list) else raw.get("items", [])
    # 人工标注导出兜底：data/annotations/export_*.json 中最新一份的 samples
    import glob as _glob

    exports = sorted(_glob.glob(os.path.join(AP_ROOT, "data", "annotations", "export_*.json")))
    if exports:
        with open(exports[-1], encoding="utf-8") as f:
            raw = json.load(f)
        samples = raw.get("samples", []) if isinstance(raw, dict) else raw
        pool = []
        for s in samples:
            labels = s.get("labels") or {}
            if not labels:
                continue
            pool.append({"idx": s.get("id"), "image_path": s.get("image_path"), "scores": labels, "total": labels.get("total")})
        if pool:
            return pool
    return []


def information_score(item: dict) -> float:
    """四维方差（composition/light/creativity/story 归一化方差）+ 成对不确定性
    （total 与四维加权重构值的偏差）。两者 0.5/0.5 加权。"""
    scores = item.get("scores") or {}
    dims = ["composition", "light", "creativity", "story"]
    vals = [float(scores.get(k, 0.0)) for k in dims]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)  # 四维方差
    total = float(item.get("total", mean))
    recon = 0.35 * vals[0] + 0.25 * vals[1] + 0.25 * vals[2] + 0.15 * vals[3]
    pair_uncert = abs(total - recon)  # 成对不确定性
    return 0.5 * var + 0.5 * pair_uncert


def main() -> int:
    pool = _load_pool()
    if not pool:
        # 无伪标签池：生成确定性占位队列（空池记录，不伪造分数）
        os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
        with open(QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump({"source": "none", "note": "pseudo-label pool not found; queue empty", "items": []}, f, ensure_ascii=False, indent=2)
        print("ACTIVE-LEARN: pool empty, empty queue written:", QUEUE_PATH)
        return 0
    ranked = sorted(pool, key=information_score, reverse=True)[:TOP_N]
    queue = {
        "source": "annotation_export (fallback from pseudo-label pool; pool not found)",
        "strategy": "0.5*4dim_variance + 0.5*pair_uncertainty(total vs weighted recon)",
        "top_n": TOP_N,
        "items": [
            {"idx": it.get("idx"), "score": round(information_score(it), 6), "scores": it.get("scores")}
            for it in ranked
        ],
    }
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    print(f"ACTIVE-LEARN: pool={len(pool)} queued={len(ranked)} -> {QUEUE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
