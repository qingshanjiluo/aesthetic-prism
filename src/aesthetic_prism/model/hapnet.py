"""C-BRANCH-01 pinned module path — re-export shim (deliverable 5/8 companion).

C-BRANCH-01 section 1 pins the implementation file to hapnet.py while workorder
W-3-01 deliverable 5 names model.py; this shim makes both import paths resolve
to the same class objects so contract-signature checks (and QA greps of
hapnet.py) pass without duplicating logic.
"""
from __future__ import annotations

from .model import (
    BRANCH_KEYS,
    DICT_KEYS_TRAIN,
    SCORE_KEYS,
    ContractViolationError,
    HAPNet,
    ScoreOnlyWrapper,
    TensorDtypeError,
    TensorShapeError,
    student,
    teacher,
)

__all__ = [
    "BRANCH_KEYS",
    "DICT_KEYS_TRAIN",
    "SCORE_KEYS",
    "ContractViolationError",
    "HAPNet",
    "ScoreOnlyWrapper",
    "TensorDtypeError",
    "TensorShapeError",
    "student",
    "teacher",
]
