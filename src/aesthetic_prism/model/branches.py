"""HAP-Net branches — workorder W-3-01 deliverable 2/8.

One branch per aesthetic dimension (C-BRANCH-01 section 3.1 row 4):
  trunk_out (N, C_t, 14, 14) -> DepthwiseSeparableResidualBlock -> GAP
    -> Linear(C_t -> D) -> feat_b (N, D)

Contract constraints honored here:
  * Four branches are structurally identical but have SEPARATE parameters
    (no weight sharing across composition/light/creativity/story).
  * Row order of stacked branch features MUST equal BRANCH_KEYS order;
    HAPNet (model.py) performs the torch.stack, this module only builds one.
  * D = branch_feat_dim (64 teacher / 48 student); D <= 0 raises ValueError.
"""
from __future__ import annotations

from typing import cast

import torch
from torch import nn

from .primitives import DepthwiseSeparableResidualBlock

# C-BRANCH-01 frozen branch order; re-exported so downstream code has one source.
BRANCH_KEYS: tuple[str, str, str, str] = ("composition", "light", "creativity", "story")


class Branch(nn.Module):
    """Single branch: trunk_feat -> DSRes -> GAP -> Linear(trunk_channels -> D).

    forward(trunk_feat) with trunk_feat (N, C_t, 14, 14) float32 returns
    (N, branch_feat_dim) float32 (unbounded real), per contract section 2.1.
    """

    def __init__(self, trunk_channels: int, branch_feat_dim: int) -> None:
        super().__init__()
        if trunk_channels <= 0 or branch_feat_dim <= 0:
            raise ValueError(
                "branch channels must be > 0, "
                f"got trunk={trunk_channels} feat={branch_feat_dim}"
            )
        # One DSRes refinement keeps 14x14 receptive field before pooling.
        self.block = DepthwiseSeparableResidualBlock(trunk_channels, trunk_channels, stride=1)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(trunk_channels, branch_feat_dim)

    @property
    def feat_dim(self) -> int:
        """D used by this branch instance (carried by the module, not a global)."""
        return self.proj.out_features

    def forward(self, trunk_feat: torch.Tensor) -> torch.Tensor:
        # (N, C_t, 14, 14) -> (N, C_t, 1, 1) -> (N, C_t) -> (N, D)
        x = self.block(trunk_feat)
        x = self.pool(x).flatten(1)
        return self.proj(x)


class BranchTower(nn.Module):
    """Four independent Branch modules; forward returns (N, 4, D) stack.

    This is a convenience container used by HAPNet. Stack row i corresponds to
    BRANCH_KEYS[i]; the container itself does not sort or deduplicate.
    """

    def __init__(self, trunk_channels: int, branch_feat_dim: int, num_branches: int = 4) -> None:
        super().__init__()
        if num_branches != 4:
            raise ValueError(f"num_branches must be 4, got {num_branches}")
        self.branches = nn.ModuleList(
            Branch(trunk_channels, branch_feat_dim) for _ in range(num_branches)
        )

    @property
    def feat_dim(self) -> int:
        branch0 = cast(Branch, self.branches[0])
        return branch0.feat_dim

    def forward(self, trunk_feat: torch.Tensor) -> torch.Tensor:
        # Stack along dim=1 so result is (N, 4, D) with row order = BRANCH_KEYS.
        feats = [branch(trunk_feat) for branch in self.branches]
        return torch.stack(feats, dim=1)
