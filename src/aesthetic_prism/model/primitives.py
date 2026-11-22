"""HAP-Net primitive layers — workorder W-3-01 deliverable 1/8.

Implements the primitive stack demanded by the MODEL brief:
  P1 color decoupling      : learnable 1x1 opponent-color projection (RGB -> luma/by/rg)
  P2 Sobel stream          : fixed 3x3 gx/gy gradient channels on Rec.709 luminance
  P3 multi-scale separable : parallel depthwise 3x3 + 5x5 -> pointwise fusion
  P4 stem   : images (N,3,224,224) -> stem_out (N,32,56,56)      [contract row 2]
  P5 trunk  : stem_out -> trunk_out (N,128,14,14) x4 DSRes blocks [contract row 3]

Shape authority is C-BRANCH-01 section 3.1 rows 2-3 (frozen). Stem in-channels
are internal (RGB 3 + color 3 + sobel 2 = 8); the module boundary stays
(N,3,224,224) float32. Downsample plan is fixed by shape math:
  224 --s2--> 112 --s2--> 56   (stem)
   56 --s2-->  28 --s2--> 14 --s1--> 14 --s1--> 14   (trunk, strides 2,2,1,1)
"""
from __future__ import annotations

from typing import cast

import torch
from torch import nn

# Opponent-color init: rows = (luma, blue-yellow, red-green); keeps early
# gradients well conditioned while remaining trainable (color decoupling).
_OPPONENT_INIT = torch.tensor(
    [
        [0.299, 0.587, 0.114],
        [-0.500, -0.500, 1.000],
        [1.000, -1.000, 0.000],
    ],
    dtype=torch.float32,
)

# Sobel kernels (fixed, non-trainable); padding=1 preserves HxW.
_SOBEL_GX = torch.tensor([[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]])
_SOBEL_GY = _SOBEL_GX.t().contiguous()

STEM_IN_CHANNELS = 8  # RGB(3) + color-decoupled(3) + sobel(2); internal wiring only


class ColorDecouple(nn.Module):
    """P1: 1x1 conv initialized with an opponent-color basis (learnable)."""

    def __init__(self) -> None:
        super().__init__()
        self.proj = nn.Conv2d(3, 3, kernel_size=1, bias=False)
        with torch.no_grad():
            self.proj.weight.copy_(_OPPONENT_INIT.view(3, 3, 1, 1))

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.proj(images)


class SobelStream(nn.Module):
    """P2: fixed Sobel gx/gy on luminance -> (N,2,H,W), H/W preserved.

    Scale factor 0.25 normalizes the integer kernel response so a unit
    gradient delta cannot blow up the stem input range.
    """

    def __init__(self) -> None:
        super().__init__()
        kx = _SOBEL_GX.view(1, 1, 3, 3) * 0.25
        ky = _SOBEL_GY.view(1, 1, 3, 3) * 0.25
        self.register_buffer("gx", kx)
        self.register_buffer("gy", ky)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        # Rec.709 luminance over RGB channel dim -> (N,1,H,W)
        luma = (0.299 * images[:, 0:1] + 0.587 * images[:, 1:2] + 0.114 * images[:, 2:3])
        kx = cast(torch.Tensor, self.gx)
        ky = cast(torch.Tensor, self.gy)
        g_x = torch.nn.functional.conv2d(luma, kx, padding=1)
        g_y = torch.nn.functional.conv2d(luma, ky, padding=1)
        return torch.cat([g_x, g_y], dim=1)


class MultiScaleSeparableConv(nn.Module):
    """P3: parallel depthwise 3x3/5x5 (same padding, shared stride) + 1x1 pointwise.

    Both branches keep ceil-identical spatial math under stride>1, so the
    concat fusion is shape-safe. Output: (N, out_channels, H/stride, W/stride).
    """

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        if in_channels <= 0 or out_channels <= 0:
            raise ValueError(f"channels must be > 0, got {in_channels}->{out_channels}")
        self.dw3 = nn.Conv2d(
            in_channels, in_channels, 3, stride=stride, padding=1, groups=in_channels
        )
        self.dw5 = nn.Conv2d(
            in_channels, in_channels, 5, stride=stride, padding=2, groups=in_channels
        )
        self.norm3 = nn.BatchNorm2d(in_channels)
        self.norm5 = nn.BatchNorm2d(in_channels)
        self.pw = nn.Conv2d(2 * in_channels, out_channels, 1)
        self.out_norm = nn.BatchNorm2d(out_channels)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        a = self.norm3(self.dw3(x))
        b = self.norm5(self.dw5(x))
        return self.act(self.out_norm(self.pw(torch.cat([a, b], dim=1))))


class DepthwiseSeparableResidualBlock(nn.Module):
    """P4: DSRes atom used by trunk x4 and each branch; residual 1x1 skip when needed."""

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        self.conv = MultiScaleSeparableConv(in_channels, out_channels, stride=stride)
        if stride != 1 or in_channels != out_channels:
            self.skip: nn.Module = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )
        else:
            self.skip = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x) + self.skip(x)


class Stem(nn.Module):
    """P4: Conv3x3/s2 x2 + BN + GELU per contract row 2; fuses color + sobel streams."""

    def __init__(self, stem_channels: int = 32) -> None:
        super().__init__()
        if stem_channels <= 0:
            raise ValueError(f"stem_channels must be > 0, got {stem_channels}")
        self.color = ColorDecouple()
        self.sobel = SobelStream()
        self.conv1 = nn.Conv2d(STEM_IN_CHANNELS, stem_channels, 3, stride=2, padding=1)
        self.bn1 = nn.BatchNorm2d(stem_channels)
        self.conv2 = nn.Conv2d(stem_channels, stem_channels, 3, stride=2, padding=1)
        self.bn2 = nn.BatchNorm2d(stem_channels)
        self.act = nn.GELU()

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        # Fuse raw RGB + color-decoupled + sobel channels, then stride-2 downs x2.
        x = torch.cat([images, self.color(images), self.sobel(images)], dim=1)
        x = self.act(self.bn1(self.conv1(x)))
        return self.act(self.bn2(self.conv2(x)))


class Trunk(nn.Module):
    """P5: 4x DepthwiseSeparableResidualBlock -> (N, trunk_channels, 14, 14), shared.

    Channel plan: (trunk//2) -> trunk -> trunk -> trunk with strides (2,2,1,1);
    teacher trunk=128 -> (64,128,128,128); student trunk=64 -> (32,64,64,64).
    """

    def __init__(self, stem_channels: int = 32, trunk_channels: int = 128) -> None:
        super().__init__()
        if trunk_channels <= 0 or stem_channels <= 0:
            raise ValueError(
                f"channels must be > 0, got stem={stem_channels} trunk={trunk_channels}"
            )
        first = max(trunk_channels // 2, 1)
        strides = (2, 2, 1, 1)
        widths = (first, trunk_channels, trunk_channels, trunk_channels)
        in_c = stem_channels
        blocks: list[nn.Module] = []
        for width, stride in zip(widths, strides, strict=True):
            blocks.append(DepthwiseSeparableResidualBlock(in_c, width, stride=stride))
            in_c = width
        self.blocks = nn.Sequential(*blocks)

    def forward(self, stem_out: torch.Tensor) -> torch.Tensor:
        return self.blocks(stem_out)
