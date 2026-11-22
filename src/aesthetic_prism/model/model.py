"""HAPNet assembly — workorder W-3-01 deliverable 5/8.

C-BRANCH-01 section 2/3: stem -> trunk -> 4 branches -> fusion gate ->
score head + ranking head; forward returns the six-key train dict (verdict A
five score keys + training-only ranking_logit).

Contract path note: C-BRANCH-01 section 1 pins the implementation file to
src/aesthetic_prism/model/hapnet.py; workorder W-3-01 deliverable 5 names
model.py. Both are satisfied: model.py holds the implementation, hapnet.py is
a same-signature re-export shim (class/keys/signature unchanged either way).

Input validation (E1-E5, E11) runs BEFORE the compute graph is built; output
validation (E7 gate row-sum, E8 range, E9 key set/order) runs right after.
Errors are raised, never swallowed (contract section 4 general rule).
"""
from __future__ import annotations

import torch
from torch import nn

from .branches import BRANCH_KEYS, BranchTower
from .fusion import ContractViolationError, FusionGate, validate_gate_row_sum
from .heads import SCORE_KEYS, RankingHead, ScoreHead, ScoreOnlyWrapper
from .primitives import Stem, Trunk

# Canonical exception objects (single class identity for all model errors).
__all__ = [
    "BRANCH_KEYS",
    "DICT_KEYS_TRAIN",
    "SCORE_KEYS",
    "ContractViolationError",
    "HAPNet",
    "ScoreOnlyWrapper",
    "TensorDtypeError",
    "TensorShapeError",
]


class TensorShapeError(ValueError):
    """images tensor rank/channel/spatial/batch violates contract (E1/E2/E3/E5).

    args[0] is '<field>: <reason>', e.g. 'images: expected rank 4 (N,C,H,W), got 3'.
    """


class TensorDtypeError(TypeError):
    """dtype is not float32 (E4). args[0] format matches TensorShapeError."""


# Re-export so callers can import exceptions from either module path
# (ContractViolationError lives in fusion.py; re-exported via __all__ below).

DICT_KEYS_TRAIN: tuple[str, str, str, str, str, str] = (
    "total",
    "composition",
    "light",
    "creativity",
    "story",
    "ranking_logit",
)

# Fixed input geometry (C-BRANCH-01 section 3.1 row 1; resize is preproc duty).
_INPUT_CHANNELS = 3
_INPUT_HEIGHT = 224
_INPUT_WIDTH = 224


def _validate_images(images: torch.Tensor) -> None:
    """E1-E5 + E11: raise before any compute graph is built; never swallowed."""
    if not isinstance(images, torch.Tensor):  # programming error, contract shape
        raise TensorShapeError(f"images: expected torch.Tensor, got {type(images).__name__}")
    if images.dim() != 4:
        raise TensorShapeError(
            f"images: expected rank 4 (N,C,H,W), got {images.dim()}"
        )
    if images.shape[1] != _INPUT_CHANNELS:
        raise TensorShapeError(
            f"images: expected {_INPUT_CHANNELS} channels RGB, got {images.shape[1]}"
        )
    h, w = images.shape[2], images.shape[3]
    if h != _INPUT_HEIGHT or w != _INPUT_WIDTH:
        raise TensorShapeError(
            f"images: spatial must be {_INPUT_HEIGHT}x{_INPUT_WIDTH}, got {h}x{w}"
        )
    if images.shape[0] < 1:
        raise TensorShapeError(f"images: batch dim must be >= 1, got {images.shape[0]}")
    if images.dtype != torch.float32:
        raise TensorDtypeError(f"images: expected float32, got {images.dtype}")
    if not torch.isfinite(images).all():
        # Contract E11: locate first offending element for the message.
        bad = (~torch.isfinite(images)).nonzero()[0].tolist()
        idx = ",".join(str(v) for v in bad)
        raise ContractViolationError(f"images: NaN/Inf detected at [{idx}]")


class HAPNet(nn.Module):
    """Teacher/student shared-structure net (width args differ), four branches.

    __init__ raises ValueError (E6) on non-positive channel args or num_branches != 4.
    forward(images, return_ranking=True) -> dict keyed by DICT_KEYS_TRAIN (train mode)
    or the five SCORE_KEYS when return_ranking=False.
    """

    def __init__(
        self,
        stem_channels: int = 32,
        trunk_channels: int = 128,
        branch_feat_dim: int = 64,
        gate_hidden: int = 128,
        ranking_hidden: int = 128,
        num_branches: int = 4,
    ) -> None:
        super().__init__()
        if num_branches != 4:
            raise ValueError(f"num_branches must be 4, got {num_branches}")
        for name, value in (
            ("stem_channels", stem_channels),
            ("trunk_channels", trunk_channels),
            ("branch_feat_dim", branch_feat_dim),
            ("gate_hidden", gate_hidden),
            ("ranking_hidden", ranking_hidden),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")

        self.stem_channels = stem_channels
        self.trunk_channels = trunk_channels
        self.branch_feat_dim = branch_feat_dim
        self.gate_hidden = gate_hidden
        self.ranking_hidden = ranking_hidden
        self.num_branches = num_branches

        self.stem = Stem(stem_channels)
        self.trunk = Trunk(stem_channels, trunk_channels)
        self.branches = BranchTower(trunk_channels, branch_feat_dim, num_branches)
        fused_dim = branch_feat_dim * num_branches
        self.gate = FusionGate(fused_dim, gate_hidden, num_branches)
        self.score_head = ScoreHead(branch_feat_dim, num_branches)
        self.ranking_head = RankingHead(fused_dim, ranking_hidden)

    @property
    def fused_dim(self) -> int:
        """4*D (teacher 256 / student 192)."""
        return self.branch_feat_dim * self.num_branches

    def forward(
        self, images: torch.Tensor, *, return_ranking: bool = True
    ) -> dict[str, torch.Tensor]:
        """Train-mode dict, key order = DICT_KEYS_TRAIN (or five SCORE_KEYS if no ranking)."""
        _validate_images(images)

        stem_out = self.stem(images)              # (N, stem, 56, 56)
        trunk_out = self.trunk(stem_out)          # (N, trunk, 14, 14)
        branch_feats = self.branches(trunk_out)   # (N, 4, D), row order = BRANCH_KEYS
        fused_feat = branch_feats.flatten(1)      # (N, 4*D) = contract row 6

        gate = self.gate(fused_feat)              # (N, 4), row-sum validated below
        sub, total = self.score_head(fused_feat, gate)  # (N,4), (N,1)

        # E7: gate row-sum deviation > 1e-4 raises before returning.
        validate_gate_row_sum(gate)

        if return_ranking:
            ranking_logit = self.ranking_head(fused_feat)  # (N, 1)
            out: dict[str, torch.Tensor] = {
                "total": total,
                "composition": sub[:, 0:1],
                "light": sub[:, 1:2],
                "creativity": sub[:, 2:3],
                "story": sub[:, 3:4],
                "ranking_logit": ranking_logit,
            }
            expected: tuple[str, ...] = DICT_KEYS_TRAIN
        else:
            out = {
                "total": total,
                "composition": sub[:, 0:1],
                "light": sub[:, 1:2],
                "creativity": sub[:, 2:3],
                "story": sub[:, 3:4],
            }
            expected = SCORE_KEYS

        # E9: key set + insertion order must match the contract exactly.
        if tuple(out.keys()) != expected:
            raise ContractViolationError(f"output keys {tuple(out.keys())} != {expected}")
        for key, value in out.items():
            if key != "ranking_logit":
                detached = value.detach()
                _range = (float(detached.min()), float(detached.max()))
                if _range[0] < 0.0 or _range[1] > 100.0:
                    raise ContractViolationError(
                        f"{key}: value {_range[0] if _range[0] < 0 else _range[1]} outside [0,100]"
                    )
        return out

    @torch.no_grad()
    def debug_shapes(self, images: torch.Tensor) -> dict[str, tuple[int, ...]]:
        """Non-contract helper: print intermediate shapes (contract section 5.1)."""
        stem_out = self.stem(images)
        trunk_out = self.trunk(stem_out)
        branch_feats = self.branches(trunk_out)
        fused_feat = branch_feats.flatten(1)
        gate = self.gate(fused_feat)
        sub, total = self.score_head(fused_feat, gate)
        shapes = {
            "stem_out": tuple(stem_out.shape),
            "trunk_out": tuple(trunk_out.shape),
            "branch_feats": tuple(branch_feats.shape),
            "fused_feat": tuple(fused_feat.shape),
            "gate": tuple(gate.shape),
            "sub": tuple(sub.shape),
            "total": tuple(total.shape),
        }
        for name, shape in shapes.items():
            print(f"{name:<11} {shape}")
        return shapes


def teacher() -> HAPNet:
    """Teacher config per 01_ARCH section 4 (D=64, trunk=128); <=25M params."""
    return HAPNet(stem_channels=32, trunk_channels=128, branch_feat_dim=64)


def student() -> HAPNet:
    """Student config (D=48, trunk=64) per C-BRANCH-01 section 2.1; <10M after prune."""
    return HAPNet(stem_channels=16, trunk_channels=64, branch_feat_dim=48, gate_hidden=64, ranking_hidden=64)
