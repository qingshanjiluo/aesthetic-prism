"""Distill + prune: HapNet teacher (<=25M) -> student (<10M), 3-stage training.

Pipeline (all stages trained to convergence here; train/cli.py stage 3 is a stub):
  stage 0  teacher training (BT stage-1 style + regression), on same data
  stage 1  student Bradley-Terry ranking pretrain (reuses cli.run_stage)
  stage 2  student regression + joint (reuses cli.run_stage)
  stage 3  student KD fine-tune: regression loss + MSE match to teacher
           sub-scores (4 branches) and total score (hard-label KD, cli-style
           loop with val eval + best.pt semantics)

Outputs:
  checkpoints/distill/teacher/best.pt
  checkpoints/distill/student/{stage1,stage2,stage3}/best.pt
  artifacts/student.onnx            (C-EXPORT-01, via ScoreOnlyWrapper)
  models/hapnet_teacher.onnx        (same IO contract)
  reports/distill_report.json       (T-4-02: params + before/after val metrics)

Usage:
  PYTHONPATH=src python -m aesthetic_prism.distill \
      --source data/synthetic/index.json [--steps-scale 1.0] [--seed 42]
"""
from __future__ import annotations

import argparse
import argparse as _argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from aesthetic_prism.export.onnx_export import export_onnx
from aesthetic_prism.model.model import HAPNet, teacher
from aesthetic_prism.model.params import STUDENT_BUDGET, TEACHER_BUDGET, count_params
from aesthetic_prism.train import cli as tcli

STUDENT_KEY_TOTAL = "total"


def _log(line: str) -> None:
    print(f"[distill] {line}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# teacher training (cli-style loop; BT pairs + regression, joint from halfway)
# --------------------------------------------------------------------------- #
def train_teacher(
    train_ds: Any,
    val_ds: Any,
    out_dir: Path,
    *,
    steps: int,
    seed: int,
    tau: float,
    alpha: float,
    batch: int = 32,
    lr: float = 2e-4,
    final_lr: float = 2e-5,
    eval_interval: int = 250,
    save_interval: int = 200,
) -> dict[str, Any]:
    """Train the HapNet teacher (<=25M budget) with BT + regression joint loss."""
    n = len(train_ds)
    if n < 64:
        raise SystemExit(f"teacher training needs >= 64 labeled train samples, got {n}")
    pool = tcli._PairCursor(tcli._totals(train_ds), seed, tcli.MAX_PAIRS_DEFAULT)
    if pool.pool_size < 100:
        raise SystemExit(f"teacher training: non-tied pairs {pool.pool_size} < 100")

    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    model = teacher()
    n_params = count_params(model)
    if n_params > TEACHER_BUDGET:
        raise SystemExit(f"teacher params {n_params} exceeds budget {TEACHER_BUDGET}")
    model.train()
    optimizer = tcli._optimizer(model)
    idx_cursor = tcli._IndexCursor(n, seed)

    config = {"stage": "teacher", "steps": steps, "lr": lr, "seed": seed,
              "source": str(out_dir), "tau": tau, "alpha": alpha}
    best_metrics: dict[str, float] = {}
    best_state: dict[str, torch.Tensor] | None = None
    best_step = 0
    losses: list[float] = []
    joint_from = max(1, steps // 2)
    report_every = max(1, steps // 20)

    def _maybe_eval(step: int, force: bool) -> None:
        nonlocal best_metrics, best_state, best_step
        if not force and (eval_interval <= 0 or step % eval_interval != 0):
            return
        if val_ds is None or len(val_ds) == 0:
            return
        metrics = tcli.evaluate(model, val_ds)
        _log(
            f"teacher eval step {step} (val n={int(metrics['n_eval'])}): "
            f"pairwise={metrics['pairwise_accuracy']:.4f} mae4={metrics['mae4']:.4f}"
        )
        if not best_metrics or metrics["mae4"] < best_metrics.get("mae4", float("inf")):
            best_metrics = dict(metrics)
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_step = step
            tcli._save_atomic(
                out_dir / "best.pt",
                tcli._bundle(model, optimizer, 0, step, config, metrics, best_state),
            )

    for step in range(1, steps + 1):
        lr_at = tcli._lr_at(step, steps, lr, final_lr, warmup=False)
        tcli._set_lr(optimizer, lr_at)
        pairs = pool.next_batch(batch)
        imgs, totals = tcli._gather_pairs(train_ds, pairs)
        out = model(imgs)
        loss = tcli.bradley_terry_loss(out["ranking_logit"], totals, tau=tau)
        idxs = idx_cursor.next_batch(batch)
        imgs2, subs2, totals2 = tcli._gather(train_ds, idxs)
        out2 = model(imgs2)
        if step >= joint_from:
            loss2 = alpha * tcli.bradley_terry_loss(out2["ranking_logit"], totals2, tau=tau) \
                + (1.0 - alpha) * tcli.regression_loss(out2, totals2, subs2)
        else:
            loss2 = tcli.regression_loss(out2, totals2, subs2)
        loss = loss + loss2
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if not tcli._record(losses, float(loss.detach())):
            raise SystemExit("teacher training aborted: non-finite loss")
        if step % report_every == 0:
            _log(f"teacher step {step}/{steps} loss={losses[-1]:.6f} lr={lr_at:.3g}")
        if save_interval > 0 and step % save_interval == 0:
            tcli._save_atomic(out_dir / "latest.pt",
                              tcli._bundle(model, optimizer, 0, step, config, {}, None))
        _maybe_eval(step, force=False)

    _maybe_eval(steps, force=True)
    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        tcli._save_atomic(out_dir / "best.pt",
                          tcli._bundle(model, optimizer, 0, steps, config, {}, best_state))
    tcli._save_atomic(out_dir / f"teacher_step{steps:06d}.pt",
                      tcli._bundle(model, optimizer, 0, steps, config, best_metrics, None))
    _log(f"teacher done: best_step={best_step} val={best_metrics or 'n/a'}")
    return {"params": n_params, "best_step": best_step, "val_metrics": best_metrics,
            "checkpoint": str(out_dir / "best.pt")}


# --------------------------------------------------------------------------- #
# stage 1 / 2 via cli.run_stage (BT pretrain -> reg+joint)
# --------------------------------------------------------------------------- #
def _stage_args(
    source: Path,
    out_dir: Path,
    *,
    stage: int,
    steps: int,
    seed: int,
    tau: float,
    alpha: float,
    steps_scale: float = 1.0,
) -> _argparse.Namespace:
    """Namespace matching train/cli.py run_stage expectations (verified fields)."""
    eval_interval = {1: 200, 2: 500}[stage]
    return _argparse.Namespace(
        tau=tau,
        alpha=alpha,
        joint_from=max(1, int(steps * steps_scale * 0.7)),
        max_pairs=tcli.MAX_PAIRS_DEFAULT,
        eval_interval=eval_interval,
        save_interval=tcli.SAVE_INTERVAL_DEFAULT,
        out=str(out_dir),
        resume=None,
        init_from=None,
        source=str(source),
        fixture=False,
        loss_log=None,
        batch_size=None,
        lr=None,
    )


# --------------------------------------------------------------------------- #
# stage 3: KD fine-tune (implemented here; train/cli.py main stage-3 is a stub)
# --------------------------------------------------------------------------- #
KD_STEPS_DEFAULT = 3000
KD_LR = 1e-4
KD_LR_FINAL = 1e-5
KD_BATCH = 32
KD_EVAL_INTERVAL = 250
KD_T_MSE_WEIGHT = 1.0     # teacher sub-score MSE weight
KD_TOTAL_MSE_WEIGHT = 1.0  # teacher total MSE weight
KD_REG_WEIGHT = 0.5       # ground-truth regression weight during KD

# ---------------------------------------------------------------------------
# 03_TRAINING section 6: structured channel pruning (|w|_1 ranking, S6-01 gate)
# ---------------------------------------------------------------------------
PRUNE_RHO_DEFAULT = 0.40   # keep 60% of channels per layer
PRUNE_RHO_MAX = 0.60       # escalation cap (S6-01)
PRUNE_KEEP_MIN = 0.25      # per-layer keep floor
TEACHER_WIDTHS = {         # HAPNet() defaults the stage-1/2 checkpoints use
    "stem_channels": 32, "trunk_channels": 128, "branch_feat_dim": 64,
    "gate_hidden": 128, "ranking_hidden": 128,
}


def _keep(width: int, rho: float) -> int:
    """Channels kept in a layer: ceil(w*(1-rho)), never below the 25% floor."""
    k = max(1, math.ceil(width * (1.0 - rho)))
    return max(k, max(1, math.ceil(width * PRUNE_KEEP_MIN)))


def _widths_from_rho(rho: float) -> dict[str, int]:
    """Uniform structured widths so the pruned net is a valid HAPNet instance."""
    return {name: _keep(w, rho) for name, w in TEACHER_WIDTHS.items()}


def _slice_bn(sd: dict[str, Any], out: dict[str, Any], prefix: str, k: int) -> None:
    for key in ("weight", "bias", "running_mean", "running_var"):
        out[f"{prefix}.{key}"] = sd[f"{prefix}.{key}"][:k].clone()
    out[f"{prefix}.num_batches_tracked"] = sd[f"{prefix}.num_batches_tracked"].clone()



def prune_state_dict(src: dict[str, Any], widths: dict[str, int]) -> dict[str, Any]:
    """Structured channel pruning of a teacher-width HAPNet state dict.

    Channel selection inside each sliced conv follows |w|_1 ranking (03 §6):
    keep the top-keep_k output channels per pruned layer, then slice every
    dependent input side (pointwise/skip/linear fans-in) consistently. Heads
    are only fanned-in sliced (their unit count is untouched); buffers
    (sobel kernels, num_batches_tracked) are copied verbatim.
    """
    st = widths["stem_channels"]
    tr = widths["trunk_channels"]
    d = widths["branch_feat_dim"]
    gh = widths["gate_hidden"]
    rh = widths["ranking_hidden"]

    def _rank_idx(w: torch.Tensor, k: int, dim: int) -> torch.Tensor:
        """Top-k channel index by mean |w|_1 over the other dims (for aligned
        slicing of weights, biases and BN stats sharing one channel axis)."""
        score = w.detach().abs().mean(dim=tuple(i for i in range(w.dim()) if i != dim))
        return torch.argsort(score, descending=True)[:k]

    def _slice_bn_idx(sd: dict[str, Any], out: dict[str, Any], prefix: str,
                      idx: torch.Tensor) -> None:
        for key in ("weight", "bias", "running_mean", "running_var"):
            out[f"{prefix}.{key}"] = sd[f"{prefix}.{key}"][idx].clone()
        out[f"{prefix}.num_batches_tracked"] = sd[f"{prefix}.num_batches_tracked"].clone()

    out: dict[str, Any] = {}
    # stem: color/sobel fixed buffers verbatim; conv1 output channels ranked.
    # conv2 must consume conv1's ranked order on its input side, and its own
    # output side gets a fresh ranking (idx2) that trunk block 0 inherits.
    out["stem.color.proj.weight"] = src["stem.color.proj.weight"].clone()
    out["stem.sobel.gx"] = src["stem.sobel.gx"].clone()
    out["stem.sobel.gy"] = src["stem.sobel.gy"].clone()
    sidx = _rank_idx(src["stem.conv1.weight"], st, dim=0)
    out["stem.conv1.weight"] = src["stem.conv1.weight"][sidx].clone()
    out["stem.conv1.bias"] = src["stem.conv1.bias"][sidx].clone()
    _slice_bn_idx(src, out, "stem.bn1", sidx)
    idx2 = _rank_idx(src["stem.conv2.weight"], st, dim=0)
    out["stem.conv2.weight"] = src["stem.conv2.weight"][idx2][:, sidx].clone()
    out["stem.conv2.bias"] = src["stem.conv2.bias"][idx2].clone()
    _slice_bn_idx(src, out, "stem.bn2", idx2)

    # trunk: widths (tr//2, tr, tr, tr), strides (2,2,1,1). Depthwise dim0 is
    # the INPUT channel axis: dw3/dw5 weights follow the upstream keep-index,
    # their biases + norm3/norm5 follow this block's output ranking.
    in_idx = idx2
    for i, w in enumerate([max(1, tr // 2), tr, tr, tr]):
        p = f"trunk.blocks.{i}"
        out_idx = _rank_idx(src[f"{p}.conv.pw.weight"], w, dim=0)
        out[f"{p}.conv.dw3.weight"] = src[f"{p}.conv.dw3.weight"][in_idx].clone()
        if f"{p}.conv.dw3.bias" in src:
            out[f"{p}.conv.dw3.bias"] = src[f"{p}.conv.dw3.bias"][in_idx].clone()
        out[f"{p}.conv.dw5.weight"] = src[f"{p}.conv.dw5.weight"][in_idx].clone()
        if f"{p}.conv.dw5.bias" in src:
            out[f"{p}.conv.dw5.bias"] = src[f"{p}.conv.dw5.bias"][in_idx].clone()
        _slice_bn_idx(src, out, f"{p}.conv.norm3", in_idx)
        _slice_bn_idx(src, out, f"{p}.conv.norm5", in_idx)
        pw = src[f"{p}.conv.pw.weight"]
        out[f"{p}.conv.pw.weight"] = pw[out_idx][:, torch.cat([in_idx, in_idx])].clone()
        out[f"{p}.conv.pw.bias"] = src[f"{p}.conv.pw.bias"][out_idx].clone()
        _slice_bn_idx(src, out, f"{p}.conv.out_norm", out_idx)
        if f"{p}.skip.0.weight" in src:
            out[f"{p}.skip.0.weight"] = src[f"{p}.skip.0.weight"][out_idx][:, in_idx].clone()
            _slice_bn_idx(src, out, f"{p}.skip.1", out_idx)
        in_idx = out_idx

    # branches: DSRes tr->tr (Identity skip); block input channel order is the
    # final trunk output ranking; proj keeps its first d output features so the
    # gate/score fan-in columns stay contiguous.
    for j in range(4):
        p = f"branches.branches.{j}"
        out_idx = _rank_idx(src[f"{p}.block.conv.pw.weight"], tr, dim=0)
        out[f"{p}.block.conv.dw3.weight"] = src[f"{p}.block.conv.dw3.weight"][in_idx].clone()
        if f"{p}.block.conv.dw3.bias" in src:
            out[f"{p}.block.conv.dw3.bias"] = src[f"{p}.block.conv.dw3.bias"][in_idx].clone()
        out[f"{p}.block.conv.dw5.weight"] = src[f"{p}.block.conv.dw5.weight"][in_idx].clone()
        if f"{p}.block.conv.dw5.bias" in src:
            out[f"{p}.block.conv.dw5.bias"] = src[f"{p}.block.conv.dw5.bias"][in_idx].clone()
        _slice_bn_idx(src, out, f"{p}.block.conv.norm3", in_idx)
        _slice_bn_idx(src, out, f"{p}.block.conv.norm5", in_idx)
        pw = src[f"{p}.block.conv.pw.weight"]
        out[f"{p}.block.conv.pw.weight"] = pw[out_idx][:, torch.cat([in_idx, in_idx])].clone()
        out[f"{p}.block.conv.pw.bias"] = src[f"{p}.block.conv.pw.bias"][out_idx].clone()
        _slice_bn_idx(src, out, f"{p}.block.conv.out_norm", out_idx)
        out[f"{p}.proj.weight"] = src[f"{p}.proj.weight"][:d, :][:, out_idx].clone()
        out[f"{p}.proj.bias"] = src[f"{p}.proj.bias"][:d].clone()

    # gate: hidden units ranked; fan-in columns are first-d per branch because
    # proj rows are NOT permuted.
    out["gate.gate_logits.0.weight"] = src["gate.gate_logits.0.weight"][:gh, : 4 * d].clone()
    out["gate.gate_logits.0.bias"] = src["gate.gate_logits.0.bias"][:gh].clone()
    out["gate.gate_logits.2.weight"] = src["gate.gate_logits.2.weight"][:4, :gh].clone()
    out["gate.gate_logits.2.bias"] = src["gate.gate_logits.2.bias"].clone()

    # heads: unit counts untouched; only fan-in columns sliced
    for i in range(4):
        out[f"score_head.branch_linears.{i}.weight"] = \
            src[f"score_head.branch_linears.{i}.weight"][:1, :d].clone()
        out[f"score_head.branch_linears.{i}.bias"] = \
            src[f"score_head.branch_linears.{i}.bias"].clone()
    ridx = _rank_idx(src["ranking_head.mlp.0.weight"], rh, dim=0)
    out["ranking_head.mlp.0.weight"] = src["ranking_head.mlp.0.weight"][ridx][:, : 4 * d].clone()
    out["ranking_head.mlp.0.bias"] = src["ranking_head.mlp.0.bias"][ridx].clone()
    out["ranking_head.mlp.2.weight"] = src["ranking_head.mlp.2.weight"][:1, :][:, ridx].clone()
    out["ranking_head.mlp.2.bias"] = src["ranking_head.mlp.2.bias"].clone()
    return out


def build_pruned_student(src_ckpt: Path, *, rho: float = PRUNE_RHO_DEFAULT) -> tuple[Any, dict[str, Any]]:
    """Prune a teacher-width checkpoint down to the <10M student budget (S6-01).

    Escalates rho += 0.05 (cap 0.60) while count_params >= STUDENT_BUDGET.
    Returns (model, info) with info = {rho, widths, params, source}.
    """
    bundle = tcli._load_bundle(Path(src_ckpt))
    cur = rho
    while True:
        widths = _widths_from_rho(cur)
        state = prune_state_dict(bundle["model"], widths)
        model = HAPNet(
            stem_channels=widths["stem_channels"],
            trunk_channels=widths["trunk_channels"],
            branch_feat_dim=widths["branch_feat_dim"],
            gate_hidden=widths["gate_hidden"],
            ranking_hidden=widths["ranking_hidden"],
        )
        model.load_state_dict(state, strict=True)
        n = count_params(model)
        _log(f"prune rho={cur:.2f} widths={widths} params={n}")
        if n < STUDENT_BUDGET:
            return model, {"rho": cur, "widths": widths, "params": n,
                           "source": str(src_ckpt)}
        if cur >= PRUNE_RHO_MAX - 1e-9:
            raise SystemExit(
                f"prune escalation exhausted (rho={cur}): params {n} still >= {STUDENT_BUDGET} (S6-01)"
            )
        cur = round(cur + 0.05, 2)


def kd_finetune(
    train_ds: Any,
    val_ds: Any,
    teacher_ckpt: Path,
    out_dir: Path,
    *,
    init_ckpt: Path,
    steps: int,
    seed: int,
    tau: float,
    alpha: float,
    source: str,
) -> dict[str, Any]:
    """Stage-3 KD fine-tune: student matches teacher sub/total outputs while
    retaining ground-truth regression signal. cli-style loop + best.pt semantics."""
    n = len(train_ds)
    if n < 64:
        raise SystemExit(f"KD fine-tune needs >= 64 labeled train samples, got {n}")

    t_bundle = tcli._load_bundle(teacher_ckpt)
    t_model = teacher()
    t_model.load_state_dict(t_bundle["model"], strict=True)
    t_model.eval()
    for p in t_model.parameters():
        p.requires_grad_(False)

    # S6-01 structured pruning: stage-1/2 checkpoints are teacher-width
    # (cli.run_stage trains HAPNet() defaults); prune |w|_1-ranked channels
    # down to the <10M student budget, then KD fine-tune the pruned net.
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    model, prune_info = build_pruned_student(Path(init_ckpt))
    model.train()
    optimizer = tcli._optimizer(model)

    config = {"stage": 3, "steps": steps, "lr": KD_LR, "seed": seed,
              "source": source, "tau": tau, "alpha": alpha,
              "prune": prune_info,
              "kd": {"t_mse_weight": KD_T_MSE_WEIGHT,
                     "total_mse_weight": KD_TOTAL_MSE_WEIGHT,
                     "reg_weight": KD_REG_WEIGHT}}
    best_metrics: dict[str, float] = {}
    best_state: dict[str, torch.Tensor] | None = None
    best_meets = None
    best_criteria = None
    losses: list[float] = []
    idx_cursor = tcli._IndexCursor(n, seed)
    report_every = max(1, steps // 20)

    def _improved(m: dict[str, float]) -> bool:
        value = m.get("mae4", float("nan"))
        if math.isnan(value):
            return False
        if not best_metrics:
            return True
        return value < best_metrics.get("mae4", float("inf"))

    def _maybe_eval(step: int, force: bool) -> None:
        nonlocal best_metrics, best_state, best_meets, best_criteria
        if not force and (KD_EVAL_INTERVAL <= 0 or step % KD_EVAL_INTERVAL != 0):
            return
        if val_ds is None or len(val_ds) == 0:
            return
        metrics = tcli.evaluate(model, val_ds)
        meets, detail = tcli.stage_criteria(3, metrics)
        _log(
            f"kd eval step {step} (val n={int(metrics['n_eval'])}): "
            f"pairwise={metrics['pairwise_accuracy']:.4f} mae4={metrics['mae4']:.4f} "
            f"meets={meets}"
        )
        if _improved(metrics):
            best_metrics = dict(metrics)
            best_meets, best_criteria = meets, detail
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            tcli._save_atomic(
                out_dir / "best.pt",
                tcli._bundle(model, optimizer, 3, step, config, metrics, best_state,
                             meets_criteria=meets, criteria_detail=detail),
            )

    for step in range(1, steps + 1):
        lr_at = tcli._lr_at(step, steps, KD_LR, KD_LR_FINAL, warmup=False)
        tcli._set_lr(optimizer, lr_at)
        idxs = idx_cursor.next_batch(KD_BATCH)
        imgs, subs, totals = tcli._gather(train_ds, idxs)
        with torch.no_grad():
            t_out = t_model(imgs)
        s_out = model(imgs)
        l_reg = tcli.regression_loss(s_out, totals, subs)
        sub_keys = ("composition", "light", "creativity", "story")
        l_sub = sum(torch.mean((s_out[k] - t_out[k]) ** 2) for k in sub_keys) / len(sub_keys)
        l_total = torch.mean((s_out["total"] - t_out["total"]) ** 2)
        loss = KD_REG_WEIGHT * l_reg \
            + KD_T_MSE_WEIGHT * l_sub \
            + KD_TOTAL_MSE_WEIGHT * l_total
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if not tcli._record(losses, float(loss.detach())):
            raise SystemExit("KD fine-tune aborted: non-finite loss")
        if step % report_every == 0:
            _log(f"kd step {step}/{steps} loss={losses[-1]:.6f} "
                 f"reg={float(l_reg):.4f} sub_mse={float(l_sub):.4f} total_mse={float(l_total):.4f}")
        _maybe_eval(step, force=False)

    _maybe_eval(steps, force=True)
    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        tcli._save_atomic(out_dir / "best.pt",
                          tcli._bundle(model, optimizer, 3, steps, config, {}, best_state,
                                       meets_criteria=None, criteria_detail={
                                           "stage": 3, "eval_split": "val",
                                           "meets_criteria": None,
                                           "source": "val split unavailable"}))
    tcli._save_atomic(out_dir / f"stage3_step{steps:06d}.pt",
                      tcli._bundle(model, optimizer, 3, steps, config, best_metrics, None,
                                   meets_criteria=best_meets, criteria_detail=best_criteria))
    _log(f"kd done: best val={best_metrics or 'n/a'}")
    return {"val_metrics": best_metrics, "checkpoint": str(out_dir / "best.pt"),
            "config": config}


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_distill(
    source: Path,
    *,
    steps_scale: float = 1.0,
    seed: int = 42,
    tau: float = 10.0,
    alpha: float = tcli.ALPHA,
) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[2]
    ckpt_root = repo / "checkpoints" / "distill"
    teacher_dir = ckpt_root / "teacher"
    student_root = ckpt_root / "student"
    artifacts_dir = repo / "artifacts"
    models_dir = repo / "models"
    reports_dir = repo / "reports"
    for d in (teacher_dir, student_root, artifacts_dir, models_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    train_ds = tcli._load_real(source, split="train")
    val_ds = tcli._load_real(source, split="val")
    _log(f"data: train={len(train_ds)} val={len(val_ds)}")

    # -- stage 0: teacher ----------------------------------------------------
    teacher_steps = max(500, int(6000 * steps_scale))
    teacher_info = train_teacher(
        train_ds, val_ds, teacher_dir,
        steps=teacher_steps, seed=seed, tau=tau, alpha=alpha,
    )

    # -- stage 1: student BT pretrain ---------------------------------------
    s1_dir = student_root / "stage1"
    s1_dir.mkdir(parents=True, exist_ok=True)
    s1_steps = max(500, int(5000 * steps_scale))
    s1_args = _stage_args(source, s1_dir, stage=1, steps=s1_steps, seed=seed,
                          tau=tau, alpha=alpha, steps_scale=steps_scale)
    tcli.run_stage(train_ds, 1, s1_steps, seed, s1_args, val_ds=val_ds)
    s1_best = tcli._load_bundle(s1_dir / "best.pt")
    s1_metrics = s1_best.get("val_metrics", {})

    # -- stage 2: student reg + joint ---------------------------------------
    s2_dir = student_root / "stage2"
    s2_dir.mkdir(parents=True, exist_ok=True)
    s2_steps = max(500, int(6000 * steps_scale))
    s2_args = _stage_args(source, s2_dir, stage=2, steps=s2_steps, seed=seed,
                          tau=tau, alpha=alpha, steps_scale=steps_scale)
    # stage-2 init-from stage-1 best
    s2_args.init_from = str(s1_dir / "best.pt")
    tcli.run_stage(train_ds, 2, s2_steps, seed, s2_args, val_ds=val_ds)
    s2_best = tcli._load_bundle(s2_dir / "best.pt")
    s2_metrics = s2_best.get("val_metrics", {})

    # -- stage 3: KD fine-tune ----------------------------------------------
    s3_dir = student_root / "stage3"
    s3_dir.mkdir(parents=True, exist_ok=True)
    kd_steps = max(500, int(KD_STEPS_DEFAULT * steps_scale))
    kd_info = kd_finetune(
        train_ds, val_ds, Path(teacher_info["checkpoint"]), s3_dir,
        init_ckpt=s2_dir / "best.pt",
        steps=kd_steps, seed=seed, tau=tau, alpha=alpha, source=str(source),
    )
    s3_metrics = kd_info["val_metrics"]

    # -- params + budgets ----------------------------------------------------
    t_model = teacher()
    t_model.load_state_dict(tcli._load_bundle(Path(teacher_info["checkpoint"]))["model"],
                            strict=True)
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
    if student_params >= STUDENT_BUDGET:
        raise SystemExit(
            f"student params {student_params} violates hard budget < {STUDENT_BUDGET}"
        )
    _log(f"params: teacher={teacher_params} student={student_params} (<{STUDENT_BUDGET} ok)")

    # -- ONNX export (both graphs share C-EXPORT-01) -------------------------
    student_onnx = artifacts_dir / "student.onnx"
    teacher_onnx = models_dir / "hapnet_teacher.onnx"
    meta_s = export_onnx(s_model, student_onnx)
    meta_t = export_onnx(t_model, teacher_onnx)
    _log(f"exported {student_onnx} + {teacher_onnx}")

    report = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": str(source),
        "seed": seed,
        "steps_scale": steps_scale,
        "data": {"train_n": len(train_ds), "val_n": len(val_ds)},
        "teacher": {
            "params": teacher_params,
            "budget": TEACHER_BUDGET,
            "best_step": teacher_info.get("best_step"),
            "val_metrics": teacher_info.get("val_metrics", {}),
            "checkpoint": teacher_info["checkpoint"],
            "onnx": str(teacher_onnx),
            "onnx_meta": meta_t,
        },
        "student": {
            "params": student_params,
            "budget": STUDENT_BUDGET,
            "within_budget": student_params < STUDENT_BUDGET,
            "stages": {
                "stage1_pairwise": s1_metrics,
                "stage2_regression_joint": s2_metrics,
                "stage3_kd_finetune": s3_metrics,
            },
            "checkpoint": str(s3_dir / "best.pt"),
            "onnx": str(student_onnx),
            "onnx_meta": meta_s,
        },
        "kd_config": {"t_mse_weight": KD_T_MSE_WEIGHT,
                      "total_mse_weight": KD_TOTAL_MSE_WEIGHT,
                      "reg_weight": KD_REG_WEIGHT,
                      "steps": kd_steps},
        "duration_seconds": round(time.time() - t0, 1),
    }
    report_path = reports_dir / "distill_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _log(f"report -> {report_path}")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="HapNet teacher->student distill pipeline")
    p.add_argument("--source", required=True, help="path to dataset index.json")
    p.add_argument("--steps-scale", type=float, default=1.0,
                   help="scale factor on all stage step counts (smoke: 0.02)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tau", type=float, default=10.0)
    p.add_argument("--alpha", type=float, default=tcli.ALPHA)
    args = p.parse_args(argv)
    report = run_distill(
        Path(args.source),
        steps_scale=args.steps_scale,
        seed=args.seed,
        tau=args.tau,
        alpha=args.alpha,
    )
    s = report["student"]
    _log(f"final: student_params={s['params']} "
         f"stage3_val={s['stages']['stage3_kd_finetune']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
