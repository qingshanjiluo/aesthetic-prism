"""渲染信噪比修复实验：降低逐主体位置抖动的 e 系数，看 composition/creativity 能否从像素恢复。

诊断结论：_subject_xy 的 x = cx + (ax-cx)*d3 + N(0, e*0.05*n)，
k 个主体各自独立抖动，相干信号被 1/sqrt(k) 摊薄，k=12 时信噪比降到 ~0.96。

修复：把 0.05 这个系数降下来（例如 0.012），让 d3 信号占主导。
本实验在内存里重渲染一批样本（不落盘、不改仓库数据），对比不同系数下
composition 的像素可恢复性（kNN R2 / MAE）。
"""
from __future__ import annotations

import io
import json
import math
import os
import pathlib
import sys

AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
sys.path.insert(0, os.path.join(AP_ROOT, "src"))
os.chdir(AP_ROOT)

import numpy as np
from numpy.random import PCG64, Generator
from PIL import Image, ImageDraw

from aesthetic_prism.data import synthetic as syn

SAMPLE_IDS = [f"syn_{i:06d}" for i in range(1, 401)]


def render_with_noise_scale(sample_id: str, jitter_scale: float) -> tuple[np.ndarray, dict]:
    """复刻 _render，但把 e*0.05*n 里的 0.05 换成 jitter_scale。"""
    rng, p = syn._params(sample_id)
    # 重新开一条完全相同的 rng 流
    rng = Generator(PCG64(int(sample_id[-6:])))
    _r, p = syn._params(sample_id)
    rng = Generator(PCG64(int(sample_id[-6:])))

    n = p["size"]
    img = Image.fromarray(syn._gradient(rng, p).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    k = p["k"]
    area = (1.0 - p["g"]) * n * n * 0.9
    r_sub = max(6.0, math.sqrt(area / max(k, 1) / math.pi))
    layers = [Image.new("RGBA", (n, n), (0, 0, 0, 0)) for _ in range(p["L"])]

    for i in range(k):
        side = "left" if rng.random() < p["w"] else "right"
        # 内联 _subject_xy，替换抖动系数
        gx, gy = float(rng.choice([1 / 3, 2 / 3])), float(rng.choice([1 / 3, 2 / 3]))
        if side == "left":
            gx = gx if gx < 0.5 else 1 - gx
        else:
            gx = gx if gx > 0.5 else 1 - gx
        cx, cy = 0.5 * n, 0.5 * n
        ax, ay = gx * n, gy * n
        x = cx + (ax - cx) * p["d3"] + rng.normal(0, p["e"] * jitter_scale * n)
        y = cy + (ay - cy) * p["d3"] + rng.normal(0, p["e"] * jitter_scale * n)
        x = float(np.clip(x, 8, n - 8))
        y = float(np.clip(y, 8, n - 8))

        exotic = 3 + int(p["u"] * 3)
        kind = int(rng.integers(0, exotic)) if p["u"] > 0.5 else int(rng.integers(0, 3))
        rot = p["e"] * rng.random() * math.tau
        rr = r_sub * (0.7 + 0.6 * rng.random()) * (1.0 - 0.35 * p["h"] * (i % 2))
        col = syn._hue_rgb(p["h1"] + 0.5 * (i / max(k, 1)), 0.8, 1.0)
        layer = layers[i % len(layers)]
        syn._draw_subject(ImageDraw.Draw(layer, "RGBA"), rng, kind, x, y, rr, col, rot)
        if p["b"] and i == 0:
            d.line((0, 0, x, y), fill=(25, 25, 25, 245), width=max(6, n // 40))

    if p["b"]:
        hy = int(n * (0.45 + 0.2 * p["h"]))
        d.line((0, hy, n, hy), fill=(30, 30, 30, 255), width=max(5, n // 40))
        d.rectangle((0, hy + 5, n, n), fill=(35, 40, 70, 90))

    base = img.convert("RGBA")
    for lay in layers:
        base = Image.alpha_composite(base, lay)
    d2 = ImageDraw.Draw(base, "RGBA")
    if p["r"]:
        for i in range(p["r"]):
            x0 = n * (0.12 + 0.28 * i)
            y0 = n * 0.82
            x1, y1 = x0 + n * 0.28, y0 - n * 0.28
            d2.line((x0, y0, x1, y1), fill=(240, 240, 40, 255), width=max(8, n // 24))
            hw = n * 0.09
            d2.polygon([(x1 + hw * 0.5, y1 - hw * 0.5), (x1 - hw, y1 + hw * 0.2),
                        (x1 + hw * 0.2, y1 + hw)], fill=(240, 240, 40, 255))

    arr = np.asarray(base.convert("RGB"), dtype=np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    dist = np.sqrt((xx - p["dL"] * n) ** 2 + (yy - (1 - p["dL"]) * n) ** 2) / (n * 1.414)
    arr *= (1.0 + 0.55 * (1.0 - dist) ** 1.5)[..., None]
    arr *= (1.0 - 0.35 * p["v"] * dist ** 1.5)[..., None]
    arr = 127.5 + (arr - 127.5) * p["c"]
    arr += rng.normal(0.0, p["sigma"], arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    # resize 到 64x64 供特征提取
    small = np.asarray(Image.fromarray(arr, "RGB").resize((64, 64), Image.BILINEAR), dtype=np.float32) / 255.0
    return small, syn._labels(p)


def feats(a: np.ndarray) -> np.ndarray:
    g = a.mean(2)
    hist, _ = np.histogram(g, bins=16, range=(0, 1), density=True)
    grid = [g[i * 16:(i + 1) * 16, j * 16:(j + 1) * 16].mean() for i in range(4) for j in range(4)]
    ch = list(a.mean((0, 1))) + list(a.std((0, 1)))
    return np.array(list(hist) + grid + ch)


def knn_r2(X, Y, k=10):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    A = (X - mu) / sd
    d2 = ((A[:, None, :] - A[None, :, :]) ** 2).sum(2)
    np.fill_diagonal(d2, np.inf)
    idx = np.argsort(d2, axis=1)[:, :k]
    pred = Y[idx].mean(1)
    r2 = 1 - ((Y - pred) ** 2).sum() / ((Y - Y.mean()) ** 2).sum()
    return float(r2), float(np.abs(Y - pred).mean())


def main():
    out = {"experiment": "jitter coefficient sweep vs pixel-recoverability", "n": len(SAMPLE_IDS), "results": {}}
    for scale in (0.05, 0.02, 0.012, 0.006, 0.0):
        X, comp, creat = [], [], []
        for sid in SAMPLE_IDS:
            a, lab = render_with_noise_scale(sid, scale)
            X.append(feats(a))
            comp.append(lab["composition"])
            creat.append(lab["creativity"])
        X = np.array(X)
        comp = np.array(comp)
        creat = np.array(creat)
        r2c, maec = knn_r2(X, comp)
        r2cr, maecr = knn_r2(X, creat)
        out["results"][str(scale)] = {
            "composition": {"r2": round(r2c, 4), "mae": round(maec, 2)},
            "creativity": {"r2": round(r2cr, 4), "mae": round(maecr, 2)},
            "label_std": {"composition": round(float(comp.std()), 2), "creativity": round(float(creat.std()), 2)},
        }
        print(f"jitter={scale:.3f}  composition R2={r2c:6.3f} MAE={maec:6.2f} | "
              f"creativity R2={r2cr:6.3f} MAE={maecr:6.2f}", flush=True)

    pathlib.Path("reports/jitter_sweep.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/jitter_sweep.json")


if __name__ == "__main__":
    main()
