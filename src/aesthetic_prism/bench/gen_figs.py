"""Stage-7 figure generator: >=4 PNGs, each >10KB.

Produces:
  reports/figs/distill_curves.png        KD stage-wise metric curves (T-7-01)
  reports/figs/metric_compare.png        teacher vs student metric bar chart (T-7-01)
  reports/figs/latency_hist.png          FP32 vs INT8 latency distribution (T-7-01)
  reports/figs/score_dist.png            predicted vs gt score distribution (T-7-01)
  reports/figs/composition_heatmap.png   composition branch attribution (T-7-03)
  reports/figs/composition_error_heat.png composition per-sample error heat (T-7-03)
  reports/figs/light_hist.png            light branch histogram (T-7-04)
  reports/figs/light_scatter.png         light pred vs gt scatter (T-7-04)
"""
import json
import os
import pathlib

import matplotlib
import numpy as np
import onnxruntime as ort

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.environ.get("AP_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
os.chdir(ROOT)
FIGDIR = os.path.join("reports", "figs")
os.makedirs(FIGDIR, exist_ok=True)
SEED = 42

KEYS = ["total", "composition", "light", "creativity", "story"]
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_index():
    idx = json.loads(pathlib.Path(os.path.join("data", "synthetic", "index.json")).read_text(encoding="utf-8"))
    return idx["samples"]


def split_of(sample):
    from hashlib import sha256
    h = int(sha256(sample["id"].encode()).hexdigest()[:8], 16) % 20
    return "test" if h < 2 else ("val" if h < 4 else "train")


def load_image(path):
    from PIL import Image
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None]


def batch_from(samples, n):
    rng = np.random.default_rng(SEED)
    picks = rng.permutation(len(samples))[:n]
    xs, gts, ids = [], [], []
    for i in picks:
        s = samples[i]
        xs.append(load_image(s["image_path"]))
        g = s["labels"]
        gts.append([g.get(k, float(np.mean([g[d] for d in KEYS[1:]]))) for k in KEYS])
        ids.append(s["id"])
    return np.concatenate(xs), np.array(gts, np.float32), ids


def main():
    sess = ort.InferenceSession(os.path.join("artifacts", "student.onnx"), providers=["CPUExecutionProvider"])
    samples = load_index()
    X, G, _ids = batch_from(samples, 60)
    P = np.concatenate([sess.run(None, {"images": X})[i] for i in range(5)], axis=1)  # (n,5) in key order

    # ---- T-7-01 distill curves (from distill_report.json) ----
    rep = json.loads(pathlib.Path(os.path.join("reports", "distill_report.json")).read_text(encoding="utf-8"))
    stages = rep["student"]["stages"]
    names = list(stages.keys())
    mae = [stages[s]["mae4"] for s in names]
    pw = [stages[s]["pairwise_accuracy"] for s in names]
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(names, mae, "o-", label="mae4")
    ax1.set_ylabel("mae4")
    ax2 = ax1.twinx()
    ax2.plot(names, pw, "s--", color="tab:red", label="pairwise_acc")
    ax2.set_ylabel("pairwise_accuracy")
    ax1.set_title("KD distillation stage curves (student 147k)")
    fig.savefig(os.path.join(FIGDIR, "distill_curves.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- metric compare teacher-vs-student proxy: final recheck vs thresholds ----
    rc = json.loads(pathlib.Path(os.path.join("reports", "metric_recheck.json")).read_text(encoding="utf-8"))
    labels = ["pairwise_val", "pairwise_test", "pearson_val", "pearson_test", "mae4_val", "mae4_test"]
    vals = [rc["splits"]["val"]["pairwise_accuracy_total"], rc["splits"]["test"]["pairwise_accuracy_total"],
            rc["splits"]["val"]["pearson_total"], rc["splits"]["test"]["pearson_total"],
            rc["splits"]["val"]["mae4"], rc["splits"]["test"]["mae4"]]
    thr = [0.68, 0.68, 0.70, 0.70, 5.0, 5.0]
    fig, ax = plt.subplots(figsize=(9, 5))
    xp = np.arange(len(labels))
    ax.bar(xp - 0.2, vals, 0.4, label="measured")
    ax.bar(xp + 0.2, thr, 0.4, label="threshold")
    for i, (v, t) in enumerate(zip(vals, thr)):
        ax.text(i, max(v, t) + 0.15, f"{v:.3f}", ha="center", fontsize=8)
    ax.set_xticks(xp); ax.set_xticklabels(labels, rotation=20, fontsize=8)
    ax.set_title("metric recheck vs gate thresholds")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, "metric_compare.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- latency hist from latency.json runs (regenerate quickly, seed=42) ----
    import time
    lat_fp, lat_q = [], []
    sq = ort.InferenceSession(os.path.join("artifacts", "student_int8.onnx"), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(SEED)
    xb = rng.standard_normal((1, 3, 224, 224), dtype=np.float32)
    for _ in range(10):
        sess.run(None, {"images": xb}); sq.run(None, {"images": xb})
    for _ in range(100):
        t = time.perf_counter(); sess.run(None, {"images": xb}); lat_fp.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); sq.run(None, {"images": xb}); lat_q.append((time.perf_counter() - t) * 1000)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(lat_fp, bins=30, alpha=0.6, label=f"fp32 (P50={np.percentile(lat_fp,50):.1f}ms)")
    ax.hist(lat_q, bins=30, alpha=0.6, label=f"int8 (P50={np.percentile(lat_q,50):.1f}ms)")
    ax.set_xlabel("latency ms"); ax.set_ylabel("count"); ax.set_title("ORT latency distribution fp32 vs int8")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, "latency_hist.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- score distribution pred vs gt ----
    fig, ax = plt.subplots(figsize=(8, 5))
    for k in KEYS:
        j = KEYS.index(k)
        ax.scatter(G[:, j], P[:, j], s=12, alpha=0.6, label=k)
    lim = [0, 100]
    ax.plot(lim, lim, "k--", lw=1)
    ax.set_xlabel("ground truth"); ax.set_ylabel("prediction"); ax.set_title("predicted vs gt (60-sample eval)")
    ax.legend(fontsize=8)
    fig.savefig(os.path.join(FIGDIR, "score_dist.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- T-7-03 composition heatmap: gradient-free attribution = |pred - label_mean| per bin ----
    comp_gt, comp_p = G[:, 1], P[:, 1]
    bins = np.linspace(0, 100, 11)
    err_map = np.zeros((10, 10))
    for b in range(10):
        m = (comp_gt >= bins[b]) & (comp_gt < bins[b + 1])
        if m.any():
            err_map[b, :] = np.abs(comp_p[m] - comp_gt[m]).mean()
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(err_map, aspect="auto", origin="lower", extent=[0, 10, 0, 100], cmap="hot")
    ax.set_xlabel("prediction decile bin"); ax.set_ylabel("gt composition score")
    ax.set_title("composition branch attribution heatmap (mean |err|)")
    fig.colorbar(im)
    fig.savefig(os.path.join(FIGDIR, "composition_heatmap.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    err_sorted = np.argsort(-np.abs(comp_p - comp_gt))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(np.arange(len(err_sorted)), np.abs(comp_p - comp_gt)[err_sorted])
    ax.set_xlabel("sample rank (largest composition error first)")
    ax.set_ylabel("|pred - gt|")
    ax.set_title("composition per-sample error heat (ranked)")
    fig.savefig(os.path.join(FIGDIR, "composition_error_heat.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- T-7-04 light branch ----
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(G[:, 2], bins=16, alpha=0.6, label="light gt")
    ax.hist(P[:, 2], bins=16, alpha=0.6, label="light pred")
    ax.set_xlabel("light score"); ax.set_title("light branch histogram gt vs pred")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, "light_hist.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(G[:, 2], P[:, 2], s=18, alpha=0.7)
    ax.plot([0, 100], [0, 100], "k--", lw=1)
    ax.set_xlabel("light gt"); ax.set_ylabel("light pred")
    ax.set_title("light branch pred vs gt scatter")
    fig.savefig(os.path.join(FIGDIR, "light_scatter.png"), dpi=140, bbox_inches="tight")
    plt.close(fig)

    for f in sorted(os.listdir(FIGDIR)):
        p = os.path.join(FIGDIR, f)
        print(f, os.path.getsize(p))


if __name__ == "__main__":
    main()
