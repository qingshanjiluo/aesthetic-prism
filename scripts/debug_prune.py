# -*- coding: utf-8 -*-
"""Debug: widths vs model shapes for pruned student."""
from pathlib import Path

from aesthetic_prism.distill import _widths_from_rho, prune_state_dict, PRUNE_RHO_DEFAULT
from aesthetic_prism.model.model import HAPNet
from aesthetic_prism.train import cli as tcli

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "checkpoints" / "distill" / "student" / "stage2" / "best.pt"

widths = _widths_from_rho(PRUNE_RHO_DEFAULT)
print("widths:", widths)

bundle = tcli._load_bundle(CKPT)
state = prune_state_dict(bundle["model"], widths)
for k in ("trunk.blocks.0.conv.dw3.weight", "trunk.blocks.1.conv.dw3.weight",
          "trunk.blocks.0.conv.dw3.bias", "ranking_head.mlp.2.weight"):
    print("out:", k, tuple(state[k].shape) if k in state else "MISSING")

model = HAPNet(
    stem_channels=widths["stem_channels"],
    trunk_channels=widths["trunk_channels"],
    branch_feat_dim=widths["branch_feat_dim"],
    gate_hidden=widths["gate_hidden"],
    ranking_hidden=widths["ranking_hidden"],
)
msd = model.state_dict()
for k in ("trunk.blocks.0.conv.dw3.weight", "trunk.blocks.1.conv.dw3.weight",
          "trunk.blocks.0.conv.dw3.bias", "ranking_head.mlp.2.weight"):
    print("model:", k, tuple(msd[k].shape))
