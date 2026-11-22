"""mae4 可达上限分析：标签由 16 个隐参数经冻结公式算出，其中一部分参数
在像素上只能弱观测（u 只改变形状种类采样区间、e 只改变抖动幅度、L 只改变图层数）。
若这些参数不可恢复，mae4 就存在不可消除的下限。

做法（不训练，纯统计）：
1. 用生成器同一 rng 流复现每个样本的 16 个参数 p（生成器保证 id 决定参数）。
2. 对每个标签维 k，用「除该维主导参数外的全部参数」线性回归预测标签，
   看残差 std —— 即如果模型只能观测到其他参数、观测不到主导参数时的误差下限。
   更直接：用线性回归以 p 预测 label（应完美 → 验证复现正确），
   再用「只保留可观测参数子集」的回归看残差增长。
3. 输出每维的可观测性判定与 mae4 理想下限估计。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
sys.path.insert(0, os.path.join(AP_ROOT, "src"))
os.chdir(AP_ROOT)

import numpy as np

from aesthetic_prism.data import synthetic as syn

DIMS = ("composition", "light", "creativity", "story")


def params_of(sample_id: str) -> dict:
    _rng, p = syn._params(sample_id)
    # h1/h2/theta moved to _derived() in the SNR fix (r11); merge them back so
    # the parameter matrix includes every label-relevant pixel driver.
    d = syn._derived(p)
    merged = dict(p)
    for k, v in d.items():
        merged.setdefault(k, v)
    return merged


def main():
    idx = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))
    samples = idx["samples"]
    print(f"n={len(samples)}")

    # 复现参数并校验标签完全一致（证明复现链正确）
    keys = ["size", "h1", "h2", "theta", "d3", "w", "g", "dL", "c", "v", "sigma", "u", "e", "L", "k", "b", "h", "r"]
    P = np.array([[params_of(s["id"])[k] for k in keys] for s in samples], dtype=np.float64)
    labels = {d: np.array([float(s["labels"][d]) for s in samples]) for d in DIMS}
    total = np.array([float(s["labels"]["total"]) for s in samples])

    # 用公式从复现参数重算标签，确认与磁盘一致（用原始 p，不做类型转换：
    # _labels 对 L/k/b/r 只做 min()/算术，int 化后 round 边界可能不同）
    mism = 0
    for i, s in enumerate(samples):
        _rng2, p2 = syn._params(s["id"])
        rec = syn._labels(p2)
        if abs(rec["total"] - float(s["labels"]["total"])) > 1e-6:
            mism += 1
    print(f"label reproduction mismatches: {mism}/{len(samples)}")

    # 每维的主导参数（按公式）
    DOMINANT = {
        "composition": ["d3", "w", "g"],
        "light": ["dL", "c", "v", "sigma"],
        "creativity": ["u", "e", "L"],
        "story": ["k", "b", "h", "r"],
    }
    # 「弱可观测」判定：该参数是否只通过离散/幅度方式进入像素
    WEAK = {
        "u": "只改形状种类采样区间 randint(0, 3+int(u*3)) 且仅当 u>0.5 生效 → 离散化，u 连续值不可恢复",
        "e": "只缩放抖动 std(e*0.05n) 与旋转角 e*rand*tau → 与独立 rng 抽样混淆，e 连续值不可恢复",
        "L": "只决定叠加图层数 1..4 → 离散，且图层 alpha 合成后大部分被覆盖",
        "h": "改地平线位置 0.45+0.2h 与主体尺寸调制 → 可观测但与其他参数耦合",
    }

    out = {"n": len(samples), "label_reproduction_mismatch": mism, "dims": {}}
    for d in DIMS:
        y = labels[d]
        cols_dom = [keys.index(k) for k in DOMINANT[d]]
        cols_all = list(range(len(keys)))
        def r2(cols):
            X = np.column_stack([np.ones(len(y)), P[:, cols]])
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            pred = X @ beta
            ss_res = ((y - pred) ** 2).sum()
            ss_tot = ((y - y.mean()) ** 2).sum()
            return 1 - ss_res / ss_tot, np.abs(y - pred).mean()
        r2_dom, mae_dom = r2(cols_dom)
        r2_all, mae_all = r2(cols_all)
        # 去掉弱可观测参数后的上限
        weak_cols = [keys.index(k) for k, why in WEAK.items() if k in DOMINANT[d]]
        obs_cols = [c for c in cols_dom if c not in weak_cols]
        if obs_cols:
            r2_obs, mae_obs = r2(obs_cols)
        else:
            r2_obs, mae_obs = 0.0, float(y.std())
        out["dims"][d] = {
            "gt_std": round(float(y.std()), 3),
            "dominant_params": DOMINANT[d],
            "r2_from_dominant": round(float(r2_dom), 4),
            "mae_from_dominant": round(float(mae_dom), 4),
            "r2_from_all_params": round(float(r2_all), 4),
            "weak_params": [k for k in DOMINANT[d] if k in WEAK],
            "r2_from_observable_only": round(float(r2_obs), 4),
            "mae_floor_observable_only": round(float(mae_obs), 4),
        }
        print(f"\n{d}: gt_std={y.std():.2f}")
        print(f"  dominant {DOMINANT[d]} -> R2={r2_dom:.4f} mae={mae_dom:.3f}")
        print(f"  all params        -> R2={r2_all:.4f} mae={mae_all:.3f}")
        print(f"  observable only   -> R2={r2_obs:.4f} mae_floor={mae_obs:.3f}  (dropped {out['dims'][d]['weak_params']})")

    floors = [out["dims"][d]["mae_floor_observable_only"] for d in DIMS]
    out["mae4_floor_estimate"] = round(float(np.mean(floors)), 4)
    out["gate"] = 5.0
    out["gate_reachable_if_observable_only"] = bool(np.mean(floors) <= 5.0)
    out["weakness_notes"] = WEAK

    pathlib.Path("reports/mae4_ceiling.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nmae4 floor estimate (observable-only params) = {out['mae4_floor_estimate']}")
    print(f"gate 5.0 reachable under this estimate: {out['gate_reachable_if_observable_only']}")
    print("wrote reports/mae4_ceiling.json")


if __name__ == "__main__":
    main()
