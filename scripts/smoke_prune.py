# -*- coding: utf-8 -*-
"""Smoke test: S6-01 pruned student build + strict load + forward."""
from pathlib import Path

import torch

from aesthetic_prism.distill import build_pruned_student
from aesthetic_prism.model.params import STUDENT_BUDGET, count_params

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "checkpoints" / "distill" / "student" / "stage2" / "best.pt"

model, info = build_pruned_student(CKPT)
n = count_params(model)
print("rho:", info["rho"])
print("widths:", info["widths"])
print("params:", n, "budget:", STUDENT_BUDGET, "ok:", n < STUDENT_BUDGET)

x = torch.randn(2, 3, 224, 224)
model.eval()
with torch.no_grad():
    out = model(x)
if isinstance(out, dict):
    for k, v in out.items():
        print(k, tuple(v.shape))
    print("finite:", torch.isfinite(out["total"]).all().item())
else:
    print("shapes:", [tuple(t.shape) for t in out])
print("SMOKE_OK")
