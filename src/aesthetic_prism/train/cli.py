"""Three-stage training CLI + S3-03 smoke recipe (W-3-01 deliverable 7/8).

Stage map follows docs/03_TRAINING.md (frozen; verdicts E/G):
  --stage 1  Bradley-Terry ranking pretrain, loss L_BT, tau=10.0        (segment 3)
  --stage 2  score regression + joint fine-tune, L_reg / L_joint,
             alpha=0.3, joint_from=4500                                  (segment 3 end -> 4)
  --stage 3  distill + channel prune + INT8 -> SEGMENT-6 SCOPE.
             EXPLICIT STUB: exits 2 with a clear message, never fakes a run.
  (no --stage)  S3-03 20-step smoke per 03_TRAINING section 9 verbatim:
             loss = L_reg, first 8 labeled train samples (sample_id asc),
             batch_size=4, Adam lr=1e-3, model.train(), no checkpoint load.

Verbatim gate command (08 S3-03; must keep working from project root):
    python -m src.train --steps 20 --loss-log <path>
Loss acceptance (08 S3-03): len(L) >= 20 and mean(L[-5:]) < mean(L[:5]).
The loss log is a BARE JSON array of per-step floats (QA asserts st.mean on it).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
import torch.nn.functional as F

from aesthetic_prism.data.dataset import AestheticDataset
from aesthetic_prism.model import BRANCH_KEYS, HAPNet

# Hyperparameters, verbatim from docs/03_TRAINING.md (frozen):
TAU = 10.0                     # 03 section 4.1 Bradley-Terry temperature
ALPHA = 0.3                    # 03 section 5.1 joint-loss weight
JOINT_FROM_DEFAULT = 4500      # 03 section 5.2
MAX_PAIRS_DEFAULT = 20_000     # 03 section 4.2 (per-epoch pair cap)
SAVE_INTERVAL_DEFAULT = 200    # 03 section 8.2
LR_DEFAULT = {1: 1e-4, 2: 3e-4, 3: 1e-4}
BATCH_DEFAULT = {1: 64, 2: 32, 3: 32}
EVAL_INTERVAL_DEFAULT = {1: 200, 2: 500, 3: 250}
LR_FINAL_DEFAULT = {1: 1e-4, 2: 3e-5, 3: 1e-5}   # 03 section 5.2 cosine floor
WARMUP_STEPS = 100             # 03 section 4.2
SMOKE_SAMPLES = 8               # 03 section 9 recipe
SMOKE_BATCH = 4
SMOKE_LR = 1e-3

STUB_STAGE3_MSG = (
    "stage 3 (distill + channel prune + INT8) is SEGMENT-6 scope; "
    "explicit stub per workorder W-3-01 - refusing to fake a run (exit 2)"
)


# --------------------------------------------------------------------------- #
# data helpers
# --------------------------------------------------------------------------- #
def _load_real(
    source: Path, split: Literal["train", "val", "test"] = "train"
) -> AestheticDataset:
    """Labeled-only, sample_id-ascending train dataset (labels=null skipped)."""
    ds = AestheticDataset(str(source), split=split)
    keep = [s for s in ds.samples if s.get("labels") is not None]
    keep.sort(key=lambda s: s["id"])
    ds.samples = keep
    return ds


def _fixture_items(n: int, seed: int) -> list[dict[str, Any]]:
    """Deterministic in-memory fixture (opt-in via --fixture); no disk reads."""
    g = torch.Generator().manual_seed(seed)
    imgs = torch.randn(n, 3, 224, 224, generator=g)
    subs = torch.rand(n, 4, generator=g) * 70.0 + 15.0
    totals = (subs * torch.tensor([0.3, 0.3, 0.2, 0.2])).sum(1, keepdim=True)
    return [
        {"image": imgs[i], "labels": subs[i], "total": totals[i], "id": f"fix_{i:06d}"}
        for i in range(n)
    ]


def _totals(ds: Any) -> list[float]:
    if isinstance(ds, list):
        return [float(x["total"]) for x in ds]
    return [float(s["labels"]["total"]) for s in ds.samples]


def _gather(ds: Any, idxs: Sequence[int]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """indices -> (images (B,3,224,224), subs (B,4), totals (B,1))."""
    imgs, subs, tots = [], [], []
    for i in idxs:
        it = ds[i]
        imgs.append(it["image"])
        subs.append(it["labels"])
        tots.append(it["total"].reshape(1))
    return torch.stack(imgs), torch.stack(subs), torch.cat(tots).unsqueeze(1)


def _gather_pairs(
    ds: Any, pairs: Sequence[tuple[int, int]]
) -> tuple[torch.Tensor, torch.Tensor]:
    """pair list -> (images (2B,3,224,224), totals (2B,1)), decoding each image once."""
    ordered: list[int] = []
    for a, b in pairs:
        ordered.append(a)
        ordered.append(b)
    cache = {i: ds[i] for i in dict.fromkeys(ordered)}
    imgs = [cache[i]["image"] for i in ordered]
    tots = [cache[i]["total"].reshape(1) for i in ordered]
    return torch.stack(imgs), torch.cat(tots).unsqueeze(1)


# --------------------------------------------------------------------------- #
# losses (03_TRAINING formulas, verbatim)
# --------------------------------------------------------------------------- #
def bradley_terry_loss(
    ranking_logit: torch.Tensor, totals: torch.Tensor, tau: float = TAU
) -> torch.Tensor:
    """L_BT = mean softplus(-sign(y_a-y_b) * (r_a - r_b) / tau); even rows = a."""
    r_a, r_b = ranking_logit[0::2], ranking_logit[1::2]
    y_a, y_b = totals[0::2], totals[1::2]
    sign = torch.where(y_a > y_b, torch.ones_like(y_a), -torch.ones_like(y_a))
    return F.softplus(-sign * (r_a - r_b) / tau).mean()


def regression_loss(
    out: dict[str, torch.Tensor], totals: torch.Tensor, subs: torch.Tensor
) -> torch.Tensor:
    """L_reg = (ŝ_total − y_total)² + (1/4)·Σ_k (ŝ_k − y_k)²  (03 section 5.1, FROZEN).

    Per-sample assembly first (total squared error + one quarter of the
    FOUR-DIMENSIONAL SUM), batch reduction (mean) last. A `.mean()` over the
    (B,4) error matrix would divide the sub-term by an extra 4 and dilute the
    score-head gradient 4x (W-3-02 S3-P1); tests/test_train_loss.py locks the
    exact 1/4 weight against the literal formula.
    """
    pred_sub = torch.cat([out[k] for k in BRANCH_KEYS], dim=-1)
    total_se = (out["total"].reshape(-1) - totals.reshape(-1)).pow(2)   # (B,)
    sub_se = 0.25 * (pred_sub - subs).pow(2).sum(dim=-1)                # (B,) per-sample ¼Σ_k e²
    return total_se.mean() + sub_se.mean()


def _lr_at(step: int, total_steps: int, base: float, final: float, warmup: bool) -> float:
    """Linear warmup (stage 1) or cosine decay base->final (stage 2)."""
    if warmup:
        return base * min(1.0, max(step, 1) / WARMUP_STEPS)
    progress = step / max(total_steps, 1)
    return final + 0.5 * (base - final) * (1.0 + math.cos(math.pi * progress))


def _set_lr(optimizer: torch.optim.Optimizer, lr: float) -> None:
    for group in optimizer.param_groups:
        group["lr"] = lr


def _optimizer(model: HAPNet) -> torch.optim.AdamW:
    """backbone wd=0.01 / heads wd=0 (03 section 4.2 optimizer row)."""
    backbone = (
        list(model.stem.parameters())
        + list(model.trunk.parameters())
        + list(model.branches.parameters())
    )
    heads = (
        list(model.gate.parameters())
        + list(model.score_head.parameters())
        + list(model.ranking_head.parameters())
    )
    return torch.optim.AdamW(
        [
            {"params": backbone, "weight_decay": 0.01},
            {"params": heads, "weight_decay": 0.0},
        ],
        betas=(0.9, 0.999),
    )


# --------------------------------------------------------------------------- #
# metrics (03 section 7) + checkpoint IO (03 section 8)
# --------------------------------------------------------------------------- #
def pairwise_accuracy(scores: torch.Tensor, labels: torch.Tensor) -> float:
    """03 section 7.1: label ties excluded, prediction tie counts 0.5."""
    s, y = scores.view(-1), labels.view(-1)
    n = int(s.numel())
    hits = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            dy = float(y[i] - y[j])
            if dy == 0.0:
                continue
            count += 1
            ds_ = float(s[i] - s[j])
            if ds_ == 0.0:
                hits += 0.5
            elif ds_ * dy > 0:
                hits += 1.0
    return hits / count if count else float("nan")


# 03_TRAINING section 7.5 thresholds (frozen; verdict G: val and test same line).
STAGE1_PA_RANK_MIN = 0.65    # 03 section 4.3 stage-1 switch criterion (val PAcc_rank)
STAGE2_MAE4_MAX = 5.0        # 03 section 5.3 item 1 (00_PRD AC3/G3)
STAGE2_PAIRWISE_MIN = 0.68   # 03 section 5.3 item 2 (00_PRD AC3)


@torch.no_grad()
def evaluate(model: HAPNet, ds: Any) -> dict[str, float]:
    """Metrics on the PROVIDED split — caller must pass the VAL split (W-3-02 S3-P2).

    Returns pairwise_accuracy (total, 03 7.1), pairwise_rank (ranking_logit,
    03 7.1 'PAcc_rank' — stage-1 criterion uses r not ŷ), mae4 (03 7.3) and
    n_eval. Never silently reads train: an empty/absent ds must be handled by
    the caller (run_stage logs meets_criteria=null instead of faking val).
    """
    was_training = model.training
    model.eval()
    n = len(ds)
    preds_total, labels_total, preds_sub, labels_sub, ranks = [], [], [], [], []
    for start in range(0, n, 16):
        idxs = list(range(start, min(start + 16, n)))
        imgs, subs, totals = _gather(ds, idxs)
        out = model(imgs, return_ranking=True)
        preds_total.append(out["total"].view(-1))
        labels_total.append(totals.view(-1))
        preds_sub.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
        labels_sub.append(subs)
        ranks.append(out["ranking_logit"].view(-1))
    if was_training:
        model.train()
    pt = torch.cat(preds_total)
    lt = torch.cat(labels_total)
    ps = torch.cat(preds_sub)
    ls = torch.cat(labels_sub)
    rr = torch.cat(ranks)
    mae_dims = (ps - ls).abs().mean(dim=0)
    return {
        "pairwise_accuracy": pairwise_accuracy(pt, lt),
        "pairwise_rank": pairwise_accuracy(rr, lt),
        "mae4": float(mae_dims.mean()),
        "n_eval": float(n),
    }


def stage_criteria(stage: int, metrics: dict[str, float]) -> tuple[bool | None, dict[str, Any]]:
    """(meets_criteria, criteria_detail) from VAL metrics per 03 switch criteria.

    Stage 1 = 03 section 4.3: val PAcc_rank >= 0.65.
    Stage 2 = 03 section 5.3: val mae4 <= 5.0 AND val pairwise_accuracy >= 0.68.
    None = undecidable (metric missing/NaN, e.g. val split unavailable); never
    coerce to True (no fake green) or False (would hide real failures).
    """
    detail: dict[str, Any] = {
        "stage": stage,
        "eval_split": "val",
        "values": dict(metrics),
    }
    if stage == 1:
        detail["source"] = "03 section 4.3"
        detail["thresholds"] = {"pairwise_rank_min": STAGE1_PA_RANK_MIN}
        pa = metrics.get("pairwise_rank", float("nan"))
        meets: bool | None = None if math.isnan(pa) else pa >= STAGE1_PA_RANK_MIN
    else:
        detail["source"] = "03 section 5.3"
        detail["thresholds"] = {
            "mae4_max": STAGE2_MAE4_MAX,
            "pairwise_accuracy_min": STAGE2_PAIRWISE_MIN,
        }
        mae = metrics.get("mae4", float("nan"))
        pa_t = metrics.get("pairwise_accuracy", float("nan"))
        meets = (
            None
            if math.isnan(mae) or math.isnan(pa_t)
            else (mae <= STAGE2_MAE4_MAX and pa_t >= STAGE2_PAIRWISE_MIN)
        )
    detail["meets_criteria"] = meets
    return meets, detail


def _bundle(
    model: HAPNet,
    optimizer: torch.optim.Optimizer | None,
    stage: int,
    step: int,
    config: dict[str, Any],
    metrics: dict[str, float],
    state: dict[str, torch.Tensor] | None = None,
    meets_criteria: bool | None = None,
    criteria_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """03 section 8.1 bundle fields, verbatim + meets_criteria flag (W-3-02 S3-P3).

    meets_criteria: None until evaluated on val, True/False per stage_criteria;
    criteria_detail records source/thresholds/values so segment 6 entry (03 6.3)
    has a machine-readable switch-criterion record to read.
    """
    model_state = (
        state if state is not None
        else {k: v.detach().cpu() for k, v in model.state_dict().items()}
    )
    return {
        "schema_version": 1,
        "stage": stage,
        "step": step,
        "model": model_state,
        "optimizer": optimizer.state_dict() if optimizer is not None else None,
        "rng": {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch": torch.random.get_rng_state(),
            "torch_cuda": None,
        },
        "config": config,
        "val_metrics": metrics,
        "meets_criteria": meets_criteria,
        "criteria": criteria_detail,
    }


def _save_atomic(path: Path, bundle: dict[str, Any]) -> None:
    """03 section 8.2: write *.tmp then os.replace; no half-written files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    torch.save(bundle, tmp)
    os.replace(tmp, path)


def _load_bundle(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    return torch.load(path, map_location="cpu", weights_only=False)


def _restore_rng(rng: dict[str, Any]) -> None:
    random.setstate(rng["python"])
    np.random.set_state(rng["numpy"])
    torch.set_rng_state(torch.as_tensor(rng["torch"], dtype=torch.uint8).cpu())


# --------------------------------------------------------------------------- #
# pair pool (03 section 1.1: distinct-total pairs, FY shuffle, epoch cap)
# --------------------------------------------------------------------------- #
def _pair_pool(totals: list[float]) -> list[tuple[int, int]]:
    pairs = [
        (i, j)
        for i in range(len(totals))
        for j in range(i + 1, len(totals))
        if totals[i] != totals[j]
    ]
    return pairs


class _PairCursor:
    """Fisher-Yates shuffled pair pool with max_pairs epoch cap and cycling."""

    def __init__(self, totals: list[float], seed: int, cap: int) -> None:
        self._pool = _pair_pool(totals)
        if not self._pool:
            raise SystemExit(
                "enter stage 1 failed (03 section 4.3): no non-tied total pairs in split"
            )
        self._seed = seed
        self._cap = cap
        self._epoch = 0
        self._order: list[tuple[int, int]] = []
        self._cursor = 0
        self._reshuffle()

    @property
    def pool_size(self) -> int:
        return len(self._pool)

    def _reshuffle(self) -> None:
        rng = random.Random(self._seed + self._epoch)  # deterministic Fisher-Yates
        order = list(self._pool)
        rng.shuffle(order)
        self._order = order[: self._cap]
        self._cursor = 0
        self._epoch += 1

    def next_batch(self, batch_pairs: int) -> list[tuple[int, int]]:
        if self._cursor + batch_pairs > len(self._order):
            self._reshuffle()
        batch = self._order[self._cursor : self._cursor + batch_pairs]
        self._cursor += batch_pairs
        return batch


class _IndexCursor:
    """Deterministic shuffled index cycling for stage-2 batches."""

    def __init__(self, n: int, seed: int) -> None:
        self._n = n
        self._rng = random.Random(seed)
        self._order = list(range(n))
        self._rng.shuffle(self._order)
        self._cursor = 0

    def next_batch(self, batch_size: int) -> list[int]:
        if self._cursor >= self._n:
            self._rng.shuffle(self._order)
            self._cursor = 0
        if batch_size > self._n:
            batch = [self._order[i % self._n] for i in range(batch_size)]
            self._cursor = self._n
            return batch
        end = self._cursor + batch_size
        if end > self._n:
            self._rng.shuffle(self._order)
            self._cursor = 0
            end = batch_size
        batch = self._order[self._cursor : end]
        self._cursor = end
        return batch


# --------------------------------------------------------------------------- #
# runners
# --------------------------------------------------------------------------- #
def _log(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _record(losses: list[float], value: float) -> bool:
    """03 T3: record the step first, then abort (non-zero exit, no latest.pt)."""
    losses.append(value)
    if not math.isfinite(value):
        _log(f"[T3] non-finite loss at step {len(losses)}: {value}; aborting without checkpoint")
        return False
    return True


def _write_loss_log(path: str | None, losses: list[float]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(losses), encoding="utf-8")


def run_smoke(
    ds: Any, steps: int, seed: int, args: argparse.Namespace
) -> list[float]:
    """03 section 9 recipe: L_reg, 8 samples, bs=4, Adam 1e-3, no checkpoint."""
    if len(ds) < SMOKE_SAMPLES:
        raise SystemExit(
            f"smoke needs >= {SMOKE_SAMPLES} labeled train samples, got {len(ds)}"
        )
    torch.manual_seed(seed)
    rng = random.Random(seed)
    model = HAPNet()
    model.train()  # 03 section 9: no checkpoint load, train mode
    optimizer = torch.optim.Adam(model.parameters(), lr=SMOKE_LR)
    order = list(range(SMOKE_SAMPLES))
    rng.shuffle(order)
    losses: list[float] = []
    cursor = 0
    for step in range(1, steps + 1):
        if cursor + SMOKE_BATCH > SMOKE_BATCH * 2:
            rng.shuffle(order)
            cursor = 0
        idxs = order[cursor : cursor + SMOKE_BATCH]
        cursor += SMOKE_BATCH
        if len(idxs) < SMOKE_BATCH:
            rng.shuffle(order)
            idxs = order[:SMOKE_BATCH]
            cursor = SMOKE_BATCH
        imgs, subs, totals = _gather(ds, idxs)
        out = model(imgs)
        loss = regression_loss(out, totals, subs)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if not _record(losses, float(loss.detach())):
            break
        if steps <= 50 or step % max(1, steps // 10) == 0:
            _log(f"[smoke] step {step}/{steps} loss={losses[-1]:.6f}")
    _log(
        f"[smoke] done steps={len(losses)} head5_mean={sum(losses[:5]) / max(len(losses[:5]), 1):.6f} "
        f"tail5_mean={sum(losses[-5:]) / max(len(losses[-5:]), 1):.6f}"
    )
    return losses


def run_stage(
    ds: Any,
    stage: int,
    steps: int,
    seed: int,
    args: argparse.Namespace,
    *,
    val_ds: Any | None = None,
) -> list[float]:
    """Stage 1 (BT) / stage 2 (reg + joint); stage 3 handled before dispatch.

    val_ds: the VALIDATION split (03 section 1.1 — eval/best.pt/criteria read
    val ONLY; W-3-02 S3-P2). None/empty => meets_criteria stays null and a
    warning is logged instead of substituting train metrics.
    """
    n = len(ds)
    batch = args.batch_size or BATCH_DEFAULT[stage]
    base_lr = args.lr if args.lr is not None else LR_DEFAULT[stage]
    eval_interval = args.eval_interval or EVAL_INTERVAL_DEFAULT[stage]
    warmup = stage == 1
    final_lr = LR_FINAL_DEFAULT[stage]
    is_pair_stage = stage == 1

    # -- enter checks (03 sections 4.3 / 5.3) -------------------------------
    start_step = 0
    init_from = args.init_from
    if args.resume:
        bundle = _load_bundle(Path(args.resume))
        cfg = bundle.get("config", {})
        if cfg.get("stage") not in (None, stage):
            raise SystemExit(f"resume config stage {cfg.get('stage')} != --stage {stage}")
        if args.lr is not None and "lr" in cfg and not math.isclose(float(cfg["lr"]), base_lr):
            raise SystemExit(f"resume config lr {cfg['lr']} != --lr {args.lr} (03 section 8.3)")
        init_from = None
        args_init = bundle
    else:
        args_init = None
    if stage == 1:
        if n < 64:
            raise SystemExit(f"enter stage 1 failed (03 section 4.3): train samples {n} < 64")
        cursor_pool = _PairCursor(_totals(ds), seed, args.max_pairs or MAX_PAIRS_DEFAULT)
        if cursor_pool.pool_size < 100:
            raise SystemExit(
                f"enter stage 1 failed (03 section 4.3): non-tied pairs {cursor_pool.pool_size} < 100"
            )
        cursor_index = None
    else:
        cursor_pool = None
        cursor_index = _IndexCursor(n, seed)
        if args_init is None and init_from is None and args_init is None:
            auto = Path(args.out) / "best.pt" if args.out else None
            if auto is not None and auto.exists():
                init_from = str(auto)
            else:
                raise SystemExit(
                    "enter stage 2 failed (03 section 5.3): need stage-1 best.pt "
                    "(pass --init-from or run with --out pointing at stage-1 output)"
                )

    # -- model / optimizer ---------------------------------------------------
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    model = HAPNet()
    model.train()
    if args_init is not None:
        model.load_state_dict(args_init["model"], strict=True)
    elif init_from:
        bundle = _load_bundle(Path(init_from))
        model.load_state_dict(bundle["model"], strict=True)
        start_step = int(bundle.get("step", 0)) if args.resume else 0
        if args.resume:
            args_init = bundle
    optimizer = _optimizer(model)
    if args_init is not None and args.resume:
        optimizer.load_state_dict(args_init["optimizer"])
        _restore_rng(args_init["rng"])
        start_step = int(args_init["step"])

    config = {
        "stage": stage,
        "steps": steps,
        "lr": base_lr,
        "batch_size": batch,
        "seed": seed,
        "tau": args.tau,
        "alpha": args.alpha,
        "joint_from": args.joint_from,
        "source": str(args.source),
        "fixture": bool(args.fixture),
    }

    # -- tracking state (03 section 8.2 best semantics + W-3-02 S3-P3 flag) ----
    key = "pairwise_accuracy" if stage == 1 else "mae4"
    best_metrics: dict[str, float] = {}
    best_state: dict[str, torch.Tensor] | None = None
    best_meets: bool | None = None
    best_criteria: dict[str, Any] | None = None

    def _improved(m: dict[str, float]) -> bool:
        value = m.get(key, float("nan"))
        if math.isnan(value):
            return False
        if not best_metrics:
            return True
        current = best_metrics.get(key, float("nan"))
        if math.isnan(current):
            return True
        return value > current if stage == 1 else value < current

    def _maybe_eval_and_save(step: int, force: bool) -> None:
        nonlocal best_metrics, best_state, best_meets, best_criteria
        if not force and (eval_interval <= 0 or step % eval_interval != 0):
            return
        # W-3-02 S3-P2: evaluate on the VAL split only; train ds is never read here.
        if val_ds is None or len(val_ds) == 0:
            metrics: dict[str, float] = {}
        else:
            metrics = evaluate(model, val_ds)
        if metrics:
            meets, detail = stage_criteria(stage, metrics)
            _log(
                f"[stage{stage}] eval step {step} (val split n={int(metrics['n_eval'])}): "
                f"pairwise={metrics['pairwise_accuracy']:.4f} pa_rank={metrics['pairwise_rank']:.4f} "
                f"mae4={metrics['mae4']:.4f} meets_criteria={meets}"
            )
            if _improved(metrics):
                best_metrics = dict(metrics)
                best_meets, best_criteria = meets, detail
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                if args.out:
                    _save_atomic(
                        Path(args.out) / "best.pt",
                        _bundle(
                            model, optimizer, stage, step, config, metrics, best_state,
                            meets_criteria=meets, criteria_detail=detail,
                        ),
                    )
        elif force:
            # No val split: keep best = current weights but meets_criteria stays
            # null (W-3-02 S3-P3: never report a criterion result we did not measure).
            _log(
                f"[criteria] val split unavailable (n={len(val_ds) if val_ds else 0}); "
                f"meets_criteria=null (03 section {'4.3' if stage == 1 else '5.3'} requires val)"
            )
            if args.out and best_state is None:
                best_metrics = {}
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                best_meets = None
                best_criteria = {
                    "stage": stage,
                    "eval_split": "val",
                    "meets_criteria": None,
                    "source": "val split unavailable",
                }

    # -- training loop --------------------------------------------------------
    losses: list[float] = []
    report_every = 1 if steps <= 50 else max(1, steps // 10)
    pair_cursor = _PairCursor(_totals(ds), seed, args.max_pairs or MAX_PAIRS_DEFAULT) if is_pair_stage else None
    del cursor_pool
    idx_cursor = cursor_index
    for step in range(start_step + 1, steps + 1):
        lr = _lr_at(step, steps, base_lr, final_lr, warmup)
        _set_lr(optimizer, lr)
        if is_pair_stage:
            assert pair_cursor is not None
            pairs = pair_cursor.next_batch(batch)
            imgs, totals = _gather_pairs(ds, pairs)
            out = model(imgs)
            loss = bradley_terry_loss(out["ranking_logit"], totals, tau=args.tau)
        else:
            assert idx_cursor is not None
            idxs = idx_cursor.next_batch(batch)
            imgs, subs, totals = _gather(ds, idxs)
            out = model(imgs)
            if step >= args.joint_from:
                l_bt = bradley_terry_loss(out["ranking_logit"], totals, tau=args.tau)
                loss = args.alpha * l_bt + (1.0 - args.alpha) * regression_loss(
                    out, totals, subs
                )
            else:
                loss = regression_loss(out, totals, subs)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if not _record(losses, float(loss.detach())):
            return losses
        if step % report_every == 0:
            _log(f"[stage{stage}] step {step}/{steps} loss={losses[-1]:.6f} lr={lr:.3g}")
        if args.out and args.save_interval > 0 and step % args.save_interval == 0:
            _save_atomic(
                Path(args.out) / "latest.pt",
                _bundle(model, optimizer, stage, step, config, {}, None),
            )
        _maybe_eval_and_save(step, force=False)

    # stage end: eval (best refresh), stage file + best.pt (03 section 8.2)
    _maybe_eval_and_save(steps, force=True)
    if args.out:
        _save_atomic(
            Path(args.out) / f"stage{stage}_step{steps:06d}.pt",
            _bundle(
                model, optimizer, stage, steps, config, best_metrics, None,
                meets_criteria=best_meets, criteria_detail=best_criteria,
            ),
        )
        if best_state is None:
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        _save_atomic(
            Path(args.out) / "best.pt",
            _bundle(
                model, optimizer, stage, steps, config, best_metrics, best_state,
                meets_criteria=best_meets, criteria_detail=best_criteria,
            ),
        )
        _log(f"[stage{stage}] checkpoints written under {args.out}")
    # W-3-02 S3-P3: stage-completion verdict record (03 4.3 / 5.3).
    _log(
        f"[stage{stage}] completion (03 section {'4.3' if stage == 1 else '5.3'}): "
        f"meets_criteria={best_meets} values={(best_criteria or {}).get('values', {})}"
    )
    return losses


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.train",
        description="HAP-Net three-stage trainer (docs/03_TRAINING.md) + S3-03 smoke.",
    )
    parser.add_argument("--stage", type=int, choices=(1, 2, 3), default=None)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--loss-log", dest="loss_log", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lr", type=float, default=None, help="default per stage (03 tables)")
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=None)
    parser.add_argument("--tau", type=float, default=TAU)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    parser.add_argument("--joint-from", dest="joint_from", type=int, default=JOINT_FROM_DEFAULT)
    parser.add_argument("--max-pairs", dest="max_pairs", type=int, default=None)
    parser.add_argument("--eval-interval", dest="eval_interval", type=int, default=None)
    parser.add_argument("--save-interval", dest="save_interval", type=int, default=SAVE_INTERVAL_DEFAULT)
    parser.add_argument("--out", default=None, help="checkpoint dir (omit = no checkpoint IO)")
    parser.add_argument("--resume", default=None, help="resume bundle (model+optimizer+rng, 03 8.3)")
    parser.add_argument("--init-from", dest="init_from", default=None, help="weights-only init")
    parser.add_argument(
        "--source",
        default="data/synthetic/index.json",
        help="DatasetSample source (index.json or .jsonl)",
    )
    parser.add_argument(
        "--fixture",
        type=int,
        default=0,
        metavar="N",
        help="use N deterministic in-memory samples instead of --source (self-check only)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.stage == 3:
        # Verdict/workorder: segment-6 scope. Explicit stub, non-zero exit, no fake green.
        _log(f"[stub] {STUB_STAGE3_MSG}")
        return 2

    # ---- data source (real by default; --fixture is explicit opt-in) --------
    # W-3-02 S3-P2: BOTH splits loaded here — train feeds optimization, val feeds
    # evaluate()/best.pt/criteria; they are never the same object.
    if args.fixture:
        if args.fixture < 8:
            raise SystemExit(f"--fixture N must be >= 8, got {args.fixture}")
        items: list[dict[str, Any]] = _fixture_items(args.fixture, args.seed)
        cut = max(1, int(len(items) * 0.8))
        if len(items) >= 2 and cut >= len(items):
            cut = len(items) - 1
        ds: Any = items[:cut]
        ds_val: Any = items[cut:]
        source_desc = (
            f"in-memory fixture n={args.fixture} train={len(ds)} "
            f"val={len(ds_val)} seed={args.seed} (self-check only)"
        )
    else:
        source_path = Path(args.source)
        if not source_path.exists():
            raise SystemExit(
                f"data source not found: {source_path} (run DATA first, or pass --fixture N)"
            )
        ds = _load_real(source_path, split="train")
        ds_val = _load_real(source_path, split="val")
        source_desc = (
            f"real {args.source} split=train labeled={len(ds)} "
            f"split=val labeled={len(ds_val)}"
        )
    _log(f"[data] {source_desc}")

    # ---- dispatch ----------------------------------------------------------
    if args.stage is None:
        # S3-03 smoke path (03 section 9 recipe; smoke = train split only).
        losses = run_smoke(ds, args.steps, args.seed, args)
    else:
        losses = run_stage(ds, args.stage, args.steps, args.seed, args, val_ds=ds_val)

    _write_loss_log(args.loss_log, losses)
    if args.loss_log:
        _log(f"[loss-log] {len(losses)} steps -> {args.loss_log}")
    if not losses or not math.isfinite(sum(losses)):
        return 3
    head = losses[:5]
    tail = losses[-5:]
    if len(losses) >= 20 and sum(tail) / len(tail) >= sum(head) / len(head):
        _log(
            f"[warn] S3-03 criterion not met: mean(head5)={sum(head)/len(head):.6f} "
            f">= mean(tail5)={sum(tail)/len(tail):.6f}"
        )
    return 0


__all__ = [
    "ALPHA",
    "STAGE1_PA_RANK_MIN",
    "STAGE2_MAE4_MAX",
    "STAGE2_PAIRWISE_MIN",
    "TAU",
    "bradley_terry_loss",
    "build_parser",
    "evaluate",
    "main",
    "pairwise_accuracy",
    "regression_loss",
    "run_smoke",
    "run_stage",
    "stage_criteria",
]
