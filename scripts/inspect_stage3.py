# -*- coding: utf-8 -*-
"""读取 stage3/best.pt 元数据：step / config / eval 指标，判断 KD 是否跑满 3000 步。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import torch

ckpt_path = r"G:\皮皮\编程项目\aesthetic-prism\checkpoints\distill\student\stage3\best.pt"
ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)

print("top-level keys:", sorted(ck.keys()) if isinstance(ck, dict) else type(ck))
for k in ("step", "global_step", "steps", "config", "meta", "metrics", "val", "history", "best"):
    if isinstance(ck, dict) and k in ck:
        v = ck[k]
        if k in ("config", "meta", "metrics", "val", "best"):
            print(f"{k}: {v}")
        elif isinstance(v, (int, float)):
            print(f"{k}: {v}")
        else:
            print(f"{k}: type={type(v)} len={len(v) if hasattr(v,'__len__') else 'n/a'}")
            try:
                tail = v[-3:] if isinstance(v, list) else None
                if tail:
                    print(f"  tail: {tail}")
            except Exception as e:
                print(f"  tail-err: {e}")

sd = ck.get("model_state_dict", ck.get("state_dict")) if isinstance(ck, dict) else None
if sd:
    n_params = sum(t.numel() for t in sd.values())
    print(f"state_dict tensors: {len(sd)}  total_params: {n_params:,}")
