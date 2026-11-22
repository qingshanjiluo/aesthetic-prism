"""参数可观测性判决实验（可判定，而非回归推断）。

原理：同一 sample_id 下 rng 由 id 固定，参数派生出的像素与标签都是确定函数。
把某个参数 p 的其他值固定、只在取值范围内扫描 p，重新渲染：
  - 若不同 p 得到**逐字节相同的 PNG** → p 在该区间对像素零影响 → 标签里由 p 决定的部分不可学习（硬证明）
  - 若像素不同 → 记录像素差幅度与标签差幅度，给出「信息量 vs 噪声」比值

对 creativity 的 u / e / L 逐项扫描，量化各自的实际可观测性。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import sys

AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
sys.path.insert(0, os.path.join(AP_ROOT, "src"))
os.chdir(AP_ROOT)

import numpy as np
from numpy.random import PCG64, Generator
from PIL import Image

from aesthetic_prism.data import synthetic as syn

SWEEP_IDS = ["syn_000007", "syn_000123", "syn_000888", "syn_001234", "syn_001777"]


def render_with(sample_id: str, override: dict) -> tuple[bytes, dict]:
    """用 id 的 rng 抽参数，按 override 改指定参数后渲染 + 出标签。"""
    rng, p = syn._params(sample_id)
    p = dict(p)
    p.update(override)
    # 重新开一条 rng，consumed 序列与 _render 内部一致
    rng2 = Generator(PCG64(int(sample_id[-6:])))
    rng2, _ = syn._params(sample_id)  # advance identical stream
    arr = syn._render(rng2, p)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG", optimize=False)
    return buf.getvalue(), syn._labels(p)


def sweep_param(name: str, values: list, ids: list[str]) -> dict:
    rows = []
    for sid in ids:
        base_sha, base_lab = render_with(sid, {})
        for v in values:
            blob, lab = render_with(sid, {name: v})
            sha = hashlib.sha256(blob).hexdigest()
            same_pixels = sha == base_sha
            rows.append({
                "id": sid,
                "value": v,
                "pixels_identical_to_base": same_pixels,
                "label_delta_creativity": round(lab["creativity"] - base_lab["creativity"], 3),
                "label_delta_total": round(lab["total"] - base_lab["total"], 3),
            })
    n = len(rows)
    ident = sum(1 for r in rows if r["pixels_identical_to_base"])
    # 对「像素有变化」的行，统计标签变化幅度
    changed = [r for r in rows if not r["pixels_identical_to_base"]]
    deltas = [abs(r["label_delta_creativity"]) for r in changed]
    return {
        "param": name,
        "sweep": [float(v) for v in values],
        "n_cases": n,
        "pixels_identical_cases": ident,
        "pixels_identical_ratio": round(ident / n, 4),
        "cases_with_pixel_change": len(changed),
        "mean_abs_creativity_delta_when_pixels_changed": round(float(np.mean(deltas)), 4) if deltas else None,
        "max_abs_creativity_delta_when_pixels_changed": round(float(np.max(deltas)), 4) if deltas else None,
        "rows": rows,
    }


def main():
    out = {
        "method": "sweep one param with all others fixed; byte-identical PNG ⇒ that param is invisible in pixels",
        "ids": SWEEP_IDS,
        "results": {},
    }
    # creativity = 100*(0.5u + 0.3e + 0.2*min(L,3)/3)
    out["results"]["u"] = sweep_param("u", [0.05, 0.2, 0.4, 0.55, 0.7, 0.85, 0.95], SWEEP_IDS)
    out["results"]["e"] = sweep_param("e", [0.05, 0.2, 0.4, 0.6, 0.8, 0.95], SWEEP_IDS)
    out["results"]["L"] = sweep_param("L", [1, 2, 3, 4], SWEEP_IDS)

    for k, r in out["results"].items():
        print(f"\n=== {k} === sweep={r['sweep']}")
        print(f"  cases={r['n_cases']}  pixels-identical={r['pixels_identical_cases']} ({r['pixels_identical_ratio']:.1%})")
        print(f"  when pixels DID change: |Δcreativity| mean={r['mean_abs_creativity_delta_when_pixels_changed']} "
              f"max={r['max_abs_creativity_delta_when_pixels_changed']}")

    pathlib.Path("reports/param_observability.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/param_observability.json")


if __name__ == "__main__":
    main()
