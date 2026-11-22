# -*- coding: utf-8 -*-
"""Isolate: is prune_state_dict itself stale? Check its idempotence markers."""
import torch

from aesthetic_prism.distill import _widths_from_rho, prune_state_dict, PRUNE_RHO_DEFAULT
from aesthetic_prism.train import cli as tcli

ROOT = r"G:\皮皮\编程项目\aesthetic-prism"
bundle = tcli._load_bundle(__import__("pathlib").Path(ROOT) / "checkpoints" / "distill" / "student" / "stage2" / "best.pt")
widths = _widths_from_rho(PRUNE_RHO_DEFAULT)
state = prune_state_dict(bundle["model"], widths)
k = "trunk.blocks.0.conv.dw3.weight"
print("key present:", k in state)
print("shape:", tuple(state[k].shape))
print("expected:", widths["trunk_channels"] // 2)
# call the function object directly from this exact module
print("func module:", prune_state_dict.__module__, "qualname:", prune_state_dict.__qualname__)
import inspect
print("first lines of loaded source:")
print("\n".join(inspect.getsource(prune_state_dict).splitlines()[:3]))
# also check whether there's a stale .pyc shadowing
import aesthetic_prism.distill as D
print("spec origin:", D.__spec__.origin)
print("spec cached:", D.__spec__.cached)
import os, time
print("py mtime:", os.path.getmtime(D.__file__))
print("pyc mtime:", os.path.getmtime(D.__spec__.cached) if os.path.exists(D.__spec__.cached) else "none")
