# Resume-only driver: reuse teacher/stage1/stage2 checkpoints, run KD fine-tune
# + params check + ONNX export + distill_report.json (mirrors distill.py tail).
import json, sys, time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aesthetic_prism import distill as D
from aesthetic_prism.export.onnx_export import export_onnx
from aesthetic_prism.model.model import HAPNet, student, teacher
from aesthetic_prism.model.params import count_params
from aesthetic_prism.train import cli as tcli

repo = Path(__file__).resolve().parents[1]
ckpt_root = repo / "checkpoints" / "distill"
teacher_dir = ckpt_root / "teacher"
student_root = ckpt_root / "student"
s2_dir = student_root / "stage2"
s3_dir = student_root / "stage3"
artifacts_dir = repo / "artifacts"
models_dir = repo / "models"
reports_dir = repo / "reports"

source = repo / "data" / "synthetic" / "index.json"
seed, tau, alpha = 42, 10.0, tcli.ALPHA
steps_scale = 1.0

train_ds = tcli._load_real(source, split="train")
val_ds = tcli._load_real(source, split="val")
print(f"data: train={len(train_ds)} val={len(val_ds)}", flush=True)

teacher_ckpt = teacher_dir / "best.pt"
s2_best = tcli._load_bundle(s2_dir / "best.pt")
s2_metrics = s2_best.get("val_metrics", {})

kd_steps = max(500, int(D.KD_STEPS_DEFAULT * steps_scale))
kd_info = D.kd_finetune(
    train_ds, val_ds, teacher_ckpt, s3_dir,
    init_ckpt=s2_dir / "best.pt",
    steps=kd_steps, seed=seed, tau=tau, alpha=alpha, source=str(source),
)
s3_metrics = kd_info["val_metrics"]

t_model = teacher()
t_model.load_state_dict(tcli._load_bundle(teacher_ckpt)["model"], strict=True)
# stage-3 best is the pruned-width net; rebuild from recorded prune widths
# (student() factory width no longer matches the S6-01 pruned checkpoint)
pruned_widths = kd_info["config"]["prune"]["widths"]
s_model = HAPNet(
    stem_channels=pruned_widths["stem_channels"],
    trunk_channels=pruned_widths["trunk_channels"],
    branch_feat_dim=pruned_widths["branch_feat_dim"],
    gate_hidden=pruned_widths["gate_hidden"],
    ranking_hidden=pruned_widths["ranking_hidden"],
)
s_model.load_state_dict(tcli._load_bundle(s3_dir / "best.pt")["model"], strict=True)
teacher_params = count_params(t_model)
student_params = count_params(s_model)
if student_params >= D.STUDENT_BUDGET:
    raise SystemExit(f"student params {student_params} violates hard budget < {D.STUDENT_BUDGET}")
print(f"params: teacher={teacher_params} student={student_params} (<{D.STUDENT_BUDGET} ok)", flush=True)

student_onnx = artifacts_dir / "student.onnx"
teacher_onnx = models_dir / "hapnet_teacher.onnx"
meta_s = export_onnx(s_model, student_onnx)
meta_t = export_onnx(t_model, teacher_onnx)
print(f"exported {student_onnx} + {teacher_onnx}", flush=True)

report = {
    "schema_version": 1,
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "source": str(source),
    "seed": seed,
    "steps_scale": steps_scale,
    "resumed": True,
    "data": {"train_n": len(train_ds), "val_n": len(val_ds)},
    "teacher": {
        "params": teacher_params,
        "budget": D.TEACHER_BUDGET,
        "checkpoint": str(teacher_ckpt),
        "onnx": str(teacher_onnx),
        "onnx_meta": meta_t,
    },
    "student": {
        "params": student_params,
        "budget": D.STUDENT_BUDGET,
        "within_budget": student_params < D.STUDENT_BUDGET,
        "stages": {
            "stage1_pairwise": tcli._load_bundle(student_root / "stage1" / "best.pt").get("val_metrics", {}),
            "stage2_regression_joint": s2_metrics,
            "stage3_kd_finetune": s3_metrics,
        },
        "checkpoint": str(s3_dir / "best.pt"),
        "onnx": str(student_onnx),
        "onnx_meta": meta_s,
    },
    "kd_config": {"t_mse_weight": D.KD_T_MSE_WEIGHT,
                  "total_mse_weight": D.KD_TOTAL_MSE_WEIGHT,
                  "reg_weight": D.KD_REG_WEIGHT,
                  "steps": kd_steps},
}
report_path = reports_dir / "distill_report.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"report -> {report_path}", flush=True)
print(f"final: student_params={student_params} stage3_val={s3_metrics}", flush=True)
