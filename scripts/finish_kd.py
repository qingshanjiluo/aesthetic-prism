# Finish-only driver: stage3 KD training already completed (step 3000 +
# best.pt on disk). Rebuild pruned-width student from best.pt, export ONNX,
# write distill_report.json. No training.
import json, time, sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aesthetic_prism.export.onnx_export import export_onnx
from aesthetic_prism.model.model import HAPNet, teacher
from aesthetic_prism.model.params import count_params
from aesthetic_prism.train import cli as tcli

repo = Path(__file__).resolve().parents[1]
ckpt_root = repo / "checkpoints" / "distill"
teacher_ckpt = ckpt_root / "teacher" / "best.pt"
s1_best = ckpt_root / "student" / "stage1" / "best.pt"
s2_best = ckpt_root / "student" / "stage2" / "best.pt"
s3_dir = ckpt_root / "student" / "stage3"
artifacts_dir = repo / "artifacts"
models_dir = repo / "models"
reports_dir = repo / "reports"

bundle = tcli._load_bundle(s3_dir / "best.pt")
widths = bundle["config"]["prune"]["widths"]
s3_metrics = bundle.get("val_metrics", {})

t_model = teacher()
t_model.load_state_dict(tcli._load_bundle(teacher_ckpt)["model"], strict=True)
t_model.eval()
s_model = HAPNet(
    stem_channels=widths["stem_channels"],
    trunk_channels=widths["trunk_channels"],
    branch_feat_dim=widths["branch_feat_dim"],
    gate_hidden=widths["gate_hidden"],
    ranking_hidden=widths["ranking_hidden"],
)
s_model.load_state_dict(bundle["model"], strict=True)
s_model.eval()
teacher_params = count_params(t_model)
student_params = count_params(s_model)
assert student_params < 10_000_000, f"student {student_params} over budget"
print(f"params: teacher={teacher_params} student={student_params}", flush=True)

student_onnx = artifacts_dir / "student.onnx"
teacher_onnx = models_dir / "hapnet_teacher.onnx"
meta_s = export_onnx(s_model, student_onnx)
meta_t = export_onnx(t_model, teacher_onnx)
print(f"exported {student_onnx} + {teacher_onnx}", flush=True)

# onnxruntime smoke: real inference on one synthetic image
import numpy as np
import onnxruntime as ort
from PIL import Image

img = Image.open(repo / "data" / "synthetic" / "syn_000001.png").convert("RGB").resize((224, 224))
x = (np.asarray(img, dtype=np.float32) / np.float32(255.0) - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
x = np.transpose(x, (2, 0, 1))[None]
sess = ort.InferenceSession(str(student_onnx), providers=["CPUExecutionProvider"])
out = sess.run(None, {sess.get_inputs()[0].name: x})
print(f"ort smoke ok, outputs={[o.shape for o in out]}", flush=True)

report = {
    "schema_version": 1,
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "resumed": True,
    "finished_by": "finish_kd.py (post-training export; KD run2 completed step 3000)",
    "teacher": {"params": teacher_params, "checkpoint": str(teacher_ckpt), "onnx": str(teacher_onnx), "onnx_meta": meta_t},
    "student": {
        "params": student_params,
        "budget": 10_000_000,
        "within_budget": student_params < 10_000_000,
        "prune_widths": widths,
        "best_step": bundle.get("step"),
        "stages": {
            "stage1_pairwise": tcli._load_bundle(s1_best).get("val_metrics", {}),
            "stage2_regression_joint": tcli._load_bundle(s2_best).get("val_metrics", {}),
            "stage3_kd_finetune": s3_metrics,
        },
        "checkpoint": str(s3_dir / "best.pt"),
        "final_step_checkpoint": str(s3_dir / "stage3_step003000.pt"),
        "onnx": str(student_onnx),
        "onnx_meta": meta_s,
    },
}
rp = reports_dir / "distill_report.json"
rp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"report -> {rp}", flush=True)
print("finish ok", flush=True)
