"""欠拟合 vs 噪声上限判定（goal① 关键实验）。

思路：用"最优线性探针"直接作用在**标签的生成参数**上，测得「若模型能完美反解参数
再线性映射到分数」时的误差。这是参数充足模型的保守上限。
若该上限已 > 5.0，说明门限不可能靠模型容量/训练量达成，问题在标签可学性；
若该上限 < 5.0，说明只是训练不足，继续训练有希望。

与 round 1 的错误方法区别：
- round 1 用「删掉主导参数」制造不可观测，是循环论证。
- 本次用**全部参数** + **充分非线性特征**（每参数的单调变换 + 交互项 + 该维公式项），
  测得的是「信息充足时的可达精度」，即真实上界。
"""
from __future__ import annotations

import itertools
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


def build_features(ids: list[str]) -> tuple[np.ndarray, dict]:
    """把每个样本的全部生成参数展开成非线性特征矩阵。"""
    rows, labs = [], {d: [] for d in DIMS}
    for sid in ids:
        _rng, p = syn._params(sid)
        lab = syn._labels(p)
        for d in DIMS:
            labs[d].append(lab[d])
        # 每个连续参数：原值 + 平方；离散参数：原值 + 独热
        f = []
        for k in ("h1", "h2", "theta", "d3", "w", "g", "dL", "c", "v", "sigma", "u", "e", "h"):
            x = float(p[k])
            f += [x, x * x]
        for k, hi in (("L", 4), ("k", 12), ("b", 1), ("r", 3)):
            x = int(p[k])
            f += [float(x)] + [1.0 if x == v else 0.0 for v in range(1, hi + 1)]
        # 关键交互项（公式里出现 min/abs 的地方）
        f += [min(int(p["k"]), 6) / 6.0, min(int(p["L"]), 3) / 3.0, min(int(p["r"]), 3) / 3.0,
              abs(float(p["w"]) - 0.5), abs(float(p["g"]) - 0.35), abs(float(p["c"]) - 1.1),
              float(p["d3"]) * float(p["w"]), float(p["u"]) * float(p["e"])]
        rows.append(f)
    X = np.asarray(rows, dtype=np.float64)
    X = np.column_stack([np.ones(len(X)), X])
    return X, {d: np.asarray(v, dtype=np.float64) for d, v in labs.items()}


def ridge_fit_eval(Xtr, ytr, Xte, yte, lam=1e-3):
    """闭式 ridge；返回 test MAE。"""
    A = Xtr.T @ Xtr + lam * np.eye(Xtr.shape[1])
    b = Xtr.T @ ytr
    coef = np.linalg.solve(A, b)
    return float(np.abs(Xte @ coef - yte).mean())


def main():
    idx = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    from aesthetic_prism.data.schema import split_of
    tr = [s["id"] for s in idx if split_of(s["id"]) == "train"]
    va = [s["id"] for s in idx if split_of(s["id"]) == "val"]
    te = [s["id"] for s in idx if split_of(s["id"]) == "test"]
    print(f"train={len(tr)} val={len(va)} test={len(te)}", flush=True)

    Xtr, Ytr = build_features(tr)
    Xva, Yva = build_features(va)
    Xte, Yte = build_features(te)
    print(f"feature dim = {Xtr.shape[1]}  (n_train={Xtr.shape[0]})", flush=True)

    out = {"method": "ridge probe on ALL generation params + nonlinear/one-hot/interaction features",
           "n_train": len(tr), "n_val": len(va), "n_test": len(te),
           "feature_dim": int(Xtr.shape[1]), "dims": {}}
    maes_va, maes_te = [], []
    for d in DIMS:
        m_va = ridge_fit_eval(Xtr, Ytr[d], Xva, Yva[d])
        m_te = ridge_fit_eval(Xtr, Ytr[d], Xte, Yte[d])
        m_tr = ridge_fit_eval(Xtr, Ytr[d], Xtr, Ytr[d], lam=1e-6)
        out["dims"][d] = {"mae_train": round(m_tr, 4), "mae_val": round(m_va, 4), "mae_test": round(m_te, 4)}
        maes_va.append(m_va)
        maes_te.append(m_te)
        print(f"  {d:12s} ridge-probe mae: train={m_tr:.3f} val={m_va:.3f} test={m_te:.3f}", flush=True)

    out["mae4_probe_val"] = round(float(np.mean(maes_va)), 4)
    out["mae4_probe_test"] = round(float(np.mean(maes_te)), 4)
    out["gate"] = 5.0
    out["gate_reachable_by_param_probe"] = bool(np.mean(maes_va) <= 5.0 and np.mean(maes_te) <= 5.0)
    print(f"\n  mae4 (param-probe upper bound): val={out['mae4_probe_val']} test={out['mae4_probe_test']}")
    print(f"  gate 5.0 reachable if model could read params: {out['gate_reachable_by_param_probe']}")

    pathlib.Path("reports/mae4_param_probe.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/mae4_param_probe.json")


if __name__ == "__main__":
    main()
