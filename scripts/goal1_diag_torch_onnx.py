"""排查：torch teacher best.pt 直推 vs models/hapnet_teacher.onnx 的数值差异。
若两者不一致，说明 ONNX 图与 checkpoint 不是同一份权重/同一预处理，
则此前所有「教师 4.12」的结论都不能用于学生重训的对齐目标。
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
import onnxruntime as ort
import torch
from PIL import Image

from aesthetic_prism.model.model import BRANCH_KEYS, teacher

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_index():
    idx = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))
    return sorted(idx["samples"], key=lambda s: s["id"])


def preprocess(path):
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None].astype(np.float32)


def main():
    samples = load_index()[:5]
    m = teacher()
    b = torch.load("checkpoints/distill/teacher/best.pt", map_location="cpu", weights_only=False)
    m.load_state_dict(b["model"], strict=True)
    m.eval()
    print("ckpt step:", b.get("step"), "val_metrics:", b.get("val_metrics"))
    print("bn running_mean sample:", float(m.trunk.blocks[0].conv.norm3.running_mean[0]))

    sess = ort.InferenceSession("models/hapnet_teacher.onnx", providers=["CPUExecutionProvider"])
    print("onnx inputs:", [(i.name, i.shape) for i in sess.get_inputs()])

    for s in samples:
        x = preprocess(os.path.join(".", s["image_path"]))
        with torch.no_grad():
            out = m(torch.from_numpy(x), return_ranking=False)
        t_vals = [float(out["total"][0, 0])] + [float(out[k][0, 0]) for k in BRANCH_KEYS]
        r = sess.run(None, {"images": x})
        o_vals = [float(r[0][0][0])] + [float(o[0][0]) for o in r[1:]]
        lab = s["labels"]
        g_vals = [float(lab["total"])] + [float(lab[k]) for k in BRANCH_KEYS]
        print(f"\n{s['id']}")
        print(f"  gt   {['%.2f' % v for v in g_vals]}")
        print(f"  torch{['%.2f' % v for v in t_vals]}")
        print(f"  onnx {['%.2f' % v for v in o_vals]}")
        d = max(abs(a - c) for a, c in zip(t_vals, o_vals))
        print(f"  |torch-onnx| max = {d:.6f}")


if __name__ == "__main__":
    main()
