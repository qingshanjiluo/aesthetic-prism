# -*- coding: utf-8 -*-
"""Debug v2: run prune_state_dict via build path, dump mismatch keys."""
from pathlib import Path

import torch

from aesthetic_prism.distill import _widths_from_rho, prune_state_dict, PRUNE_RHO_DEFAULT
from aesthetic_prism.model.model import HAPNet
from aesthetic_prism.train import cli as tcli

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "checkpoints" / "distill" / "student" / "stage2" / "best.pt"

widths = _widths_from_rho(PRUNE_RHO_DEFAULT)
bundle = tcli._load_bundle(CKPT)
print("bundle keys:", list(bundle.keys())[:8])
state = prune_state_dict(bundle["model"], widths)
model = HAPNet(
    stem_channels=widths["stem_channels"],
    trunk_channels=widths["trunk_channels"],
    branch_feat_dim=widths["branch_feat_dim"],
    gate_hidden=widths["gate_hidden"],
    ranking_hidden=widths["ranking_hidden"],
)
msd = model.state_dict()
sk, mk = set(state), set(msd)
print("missing in pruned:", sorted(mk - sk)[:20])
print("extra in pruned:", sorted(sk - mk)[:20])
bad = []
for k in sorted(sk & mk):
    if state[k].shape != msd[k].shape:
        bad.append((k, tuple(state[k].shape), tuple(msd[k].shape)))
print("shape mismatches:", len(bad))
for k, a, b in bad[:20]:
    print(" ", k, a, b)
try:
    model.load_state_dict(state, strict=True)
    print("STRICT_LOAD_OK")
except RuntimeError as e:
    print("FAIL:", str(e)[:300])
