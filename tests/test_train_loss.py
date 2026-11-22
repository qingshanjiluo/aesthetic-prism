"""W-3-02 rework locks: S3-P1 frozen L_reg weight + S3-P3 stage criteria.

Three problems from QA whitebox_S3.md, regression-proofed here without touching
the locked gate file tests/test_model.py (its three node ids stay verbatim):
  S3-P1  regression_loss must match 03_TRAINING section 5.1 literally:
         L = (t̂-y)² + ¼·Σ_k e_k² assembled PER SAMPLE — a `.mean()` over the
         (B,4) matrix would dilute the score-head gradient 4x.
  S3-P3  stage_criteria encodes the frozen switch thresholds
         (stage1: val PAcc_rank >= 0.65 / stage2: val mae4 <= 5.0 AND
         pairwise_accuracy >= 0.68) and returns None when undecidable.

S3-P2 (real val split loading) is verified by run logs in the rework receipt
(`eval step N (val split n=...)` lines) — it needs real data IO, covered by QA
blackbox, not asserted against data/ here (DATA regenerates data/ in parallel).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import torch

# sys.path injection mirrors tests/conftest.py so bare `pytest` also works.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aesthetic_prism.model import BRANCH_KEYS
from aesthetic_prism.train import (
    STAGE1_PA_RANK_MIN,
    STAGE2_MAE4_MAX,
    STAGE2_PAIRWISE_MIN,
    regression_loss,
    stage_criteria,
)


def _out(sub4: torch.Tensor, total: torch.Tensor) -> dict[str, torch.Tensor]:
    """Assemble a one-key-per-branch output dict (contract key order)."""
    out = {k: sub4[:, i : i + 1] for i, k in enumerate(BRANCH_KEYS)}
    out["total"] = total
    return out


def test_regression_loss_matches_frozen_formula_03_s5_1() -> None:
    """S3-P1: loss equals the literal per-sample 03 section 5.1 formula."""
    sub = torch.tensor([[78.4, 71.2, 65.9, 74.6]], dtype=torch.float32)
    y_sub = torch.tensor([[76.0, 70.0, 68.0, 71.0]], dtype=torch.float32)
    total = torch.tensor([[72.98]], dtype=torch.float32)
    y_total = torch.tensor([[73.0]], dtype=torch.float32)

    # Literal python computation of (t̂-y)² + ¼·Σ_k e_k² (single sample).
    e_total = 72.98 - 73.0
    subs_pred = (78.4, 71.2, 65.9, 74.6)
    subs_true = (76.0, 70.0, 68.0, 71.0)
    literal = e_total * e_total + 0.25 * sum(
        (p - t) ** 2 for p, t in zip(subs_pred, subs_true, strict=True)
    )
    got = float(regression_loss(_out(sub, total), y_total, y_sub))
    assert math.isclose(got, literal, rel_tol=1e-5, abs_tol=1e-4), (got, literal)


def test_regression_loss_subterm_weight_is_quarter_not_sixteenth() -> None:
    """S3-P1 weight lock: pure sub error e gives 0.25·e², NOT the diluted 0.0625·e²."""
    e = 40.0
    sub = torch.tensor([[e, 0.0, 0.0, 0.0]], dtype=torch.float32)
    y_sub = torch.zeros(1, 4)
    total = torch.zeros(1, 1)
    y_total = torch.zeros(1, 1)

    got = float(regression_loss(_out(sub, total), y_total, y_sub))
    frozen = 0.25 * e * e          # 400.0 (per-sample ¼Σ_k e_k², batch=1)
    diluted = 0.0625 * e * e       # 100.0 (old .mean()-over-(B,4) bug, 4x too small)
    assert math.isclose(got, frozen, rel_tol=1e-5), (got, frozen)
    assert not math.isclose(got, diluted, rel_tol=1e-3), f"still diluted 4x: {got}"

    # Gradient lock: d/de [0.25 e²] = 0.5 e = 20.0 (B=1, no batch dilution).
    sub_g = sub.clone().requires_grad_(True)
    loss = regression_loss(_out(sub_g, total), y_total, y_sub)
    loss.backward()
    grad = float(sub_g.grad[0, 0])
    assert math.isclose(grad, 0.5 * e, rel_tol=1e-4), grad


def test_stage_criteria_stage1_uses_pacc_rank_threshold() -> None:
    """S3-P3: stage1 criterion = val PAcc_rank >= 0.65 (03 section 4.3)."""
    meets, detail = stage_criteria(1, {"pairwise_rank": 0.66})
    assert meets is True
    assert detail["thresholds"]["pairwise_rank_min"] == STAGE1_PA_RANK_MIN == 0.65
    assert detail["source"] == "03 section 4.3"
    assert detail["eval_split"] == "val"

    meets_low, _ = stage_criteria(1, {"pairwise_rank": 0.649})
    assert meets_low is False

    meets_undecidable, detail_none = stage_criteria(1, {"pairwise_rank": float("nan")})
    assert meets_undecidable is None and detail_none["meets_criteria"] is None


def test_stage_criteria_stage2_requires_both_mae_and_pairwise() -> None:
    """S3-P3: stage2 = val mae4<=5.0 AND pairwise>=0.68 (03 section 5.3)."""
    meets, detail = stage_criteria(2, {"mae4": 4.9, "pairwise_accuracy": 0.68})
    assert meets is True
    assert detail["thresholds"] == {
        "mae4_max": STAGE2_MAE4_MAX,
        "pairwise_accuracy_min": STAGE2_PAIRWISE_MIN,
    }
    assert STAGE2_MAE4_MAX == 5.0 and STAGE2_PAIRWISE_MIN == 0.68
    assert detail["source"] == "03 section 5.3"

    assert stage_criteria(2, {"mae4": 5.01, "pairwise_accuracy": 0.70})[0] is False
    assert stage_criteria(2, {"mae4": 4.0, "pairwise_accuracy": 0.679})[0] is False
    # Missing val metrics => undecidable, never coerced to True/False.
    assert stage_criteria(2, {})[0] is None
