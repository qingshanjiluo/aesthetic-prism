"""aesthetic_prism.train — three-stage HAP-Net trainer (W-3-01 deliverable 7/8,
reworked by W-3-02: frozen L_reg weight, real val split, meets_criteria flag).

Public entry: main(argv) -> int. Stage 3 is an explicit stub (segment-6 scope).
Hyperparameter constants (TAU/ALPHA/...) mirror docs/03_TRAINING.md verbatim.
"""
from __future__ import annotations

from .cli import (
    ALPHA,
    STAGE1_PA_RANK_MIN,
    STAGE2_MAE4_MAX,
    STAGE2_PAIRWISE_MIN,
    TAU,
    bradley_terry_loss,
    build_parser,
    evaluate,
    main,
    pairwise_accuracy,
    regression_loss,
    run_smoke,
    run_stage,
    stage_criteria,
)

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
