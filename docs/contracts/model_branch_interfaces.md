# 契约 C-BRANCH-01：HAPNet 四分支 / 融合门控 / 双头 forward 接口与张量形状

| 项 | 值 |
|---|---|
| 契约 ID | C-BRANCH-01 |
| 归属 | ARCH 定义；MODEL 实现（段3）；QA 验证（08 S3-02/S3-05） |
| 批准状态 | 已冻结 @2026-11-08 04:05（lead 批准，回改须 lead 批准） |
| 已并入裁决 | 裁决 A：五键全链路同名 `total`/`composition`/`light`/`creativity`/`story`；裁决 B：`ranking_logit` 训练专用、不进 ONNX 图 |
| 与 01_ARCH §3 关系 | 数据流图逐形状一致；发现不一致以**本契约为准**并回报 lead 修订 01_ARCH |
| 四要素索引 | ① 函数签名=§2 ② 张量形状=§3 ③ 错误语义=§4 ④ 最小示例=§5 |

## 1. 用途与适用范围

- MODEL 段3 实现依据：基元层 + 四分支（composition/light/creativity/story）+ 融合门控 + 双头（score 四维子分 + ranking Bradley-Terry）的类结构、`forward` 签名、内部张量形状、错误语义。
- 训练态与导出态由同一 `forward` 产出：训练态 dict 六键（5 分数键 + `ranking_logit`）；导出态经 score-only 包装产出五键（C-EXPORT-01 裁决 B，ranking 头不进图）。
- 输入预处理、归一化、ONNX IO、HTTP 响应以各自契约为准，本契约只管 PyTorch 层。
- 实现文件：`src/aesthetic_prism/model/hapnet.py`（签名与键序不得改动；内部层名/优化可改）。

## 2. ① 函数签名（参数名 / 类型 / 返回类型 / 异常类型）

```python
from __future__ import annotations
from typing import Literal
import torch
from torch import nn

class TensorShapeError(ValueError):
    """张量秩/通道/空间尺寸违反契约。args[0] 为 str，格式 '<field>: <reason>'。"""

class TensorDtypeError(TypeError):
    """dtype 违反契约（仅允许 float32）。args[0] 同上。"""

class ContractViolationError(RuntimeError):
    """前向产出违反契约（缺键/值域/门控行和）。args[0] 同上。"""

BRANCH_KEYS: tuple[str, str, str, str] = ("composition", "light", "creativity", "story")
SCORE_KEYS: tuple[str, str, str, str, str] = ("total", "composition", "light", "creativity", "story")
DICT_KEYS_TRAIN: tuple[str, ...] = ("total", "composition", "light", "creativity",
                                    "story", "ranking_logit")   # 训练态六键（键序固定）

class HAPNet(nn.Module):
    """教师/学生共构（宽度参数区分），四分支 + 融合门控 + 双头。"""

    def __init__(self, stem_channels: int = 32, trunk_channels: int = 128,
                 branch_feat_dim: int = 64, gate_hidden: int = 128,
                 ranking_hidden: int = 128, num_branches: int = 4) -> None: ...

    def forward(self, images: torch.Tensor, *,
                return_ranking: bool = True) -> dict[str, torch.Tensor]:
        """训练态（default）返回六键；return_ranking=False 时不含 ranking_logit。"""

class Branch(nn.Module):
    """单分支：trunk 特征 → GAP → 线性 → 分支特征。四分支结构同构、参数不共享。"""
    def forward(self, trunk_feat: torch.Tensor) -> torch.Tensor: ...

class FusionGate(nn.Module):
    """融合门控：4 个分支特征 → MLP → 4 个门控 logit → 行向 softmax。"""
    def forward(self, branch_feats: torch.Tensor) -> torch.Tensor: ...

class ScoreHead(nn.Module):
    """score 头：门控加权四子分 + 总分。"""
    def forward(self, fused_feat: torch.Tensor,
                gate: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]: ...

class RankingHead(nn.Module):
    """ranking 头（Bradley-Terry 打分器）；训练专用，导出图不含此模块。"""
    def forward(self, fused_feat: torch.Tensor) -> torch.Tensor: ...

class ScoreOnlyWrapper(nn.Module):
    """导出包装：eval 态调用 HAPNet 并剥离 ranking_logit，键集=SCORE_KEYS（C-EXPORT-01）。"""
    def forward(self, images: torch.Tensor) -> dict[str, torch.Tensor]: ...
```

### 2.1 参数与返回明细

| 函数 | 参数名 | 参数类型 | 返回类型 | 抛出异常类型 |
|---|---|---|---|---|
| `HAPNet.__init__` | `stem_channels` / `trunk_channels` / `branch_feat_dim` / `gate_hidden` / `ranking_hidden` | `int`（>0；学生配置 16/64/48/64/64） | `HAPNet` | `ValueError`（≤0，编程错误） |
| `HAPNet.__init__` | `num_branches` | `int`，恒 4 | 同上 | `ValueError`（≠4，四维为契约常量） |
| `HAPNet.forward` | `images` | `torch.Tensor`，`(N,3,224,224)` float32 | `dict[str, torch.Tensor]`（键序=DICT_KEYS_TRAIN 或去 ranking 后五键） | `TensorShapeError`, `TensorDtypeError`, `ContractViolationError` |
| `HAPNet.forward` | `return_ranking` | `bool`（keyword-only，默认 True） | 同上 | 同上 |
| `Branch.forward` | `trunk_feat` | `torch.Tensor`，`(N,C_t,14,14)` | `(N, branch_feat_dim)` float32 | `TensorShapeError`, `TensorDtypeError` |
| `FusionGate.forward` | `branch_feats` | `torch.Tensor`，`(N,4,D)`（stack 自四分支 `(N,D)`） | `(N,4)` float32，行和=1 | `TensorShapeError`, `ContractViolationError`（行和偏差 >1e-4） |
| `ScoreHead.forward` | `fused_feat` | `torch.Tensor`，`(N,4*D)` | `tuple[(N,4), (N,1)]` = (四子分, 总分) | `TensorShapeError`, `ContractViolationError`（子分越界） |
| `ScoreHead.forward` | `gate` | `torch.Tensor`，`(N,4)` | 同上 | `TensorShapeError` |
| `RankingHead.forward` | `fused_feat` | `torch.Tensor`，`(N,4*D)` | `(N,1)` float32，ℝ 无界 | `TensorShapeError` |
| `ScoreOnlyWrapper.forward` | `images` | 同 HAPNet.forward | 五键 dict（SCORE_KEYS 键序） | 同 HAPNet.forward |

键序保证：dict 构造按 `DICT_KEYS_TRAIN`/`SCORE_KEYS` 顺序插入（Python 3.7+ 语义），ONNX 导出输出序即 C-EXPORT-01 §3.2 序。
学生/教师差异只在 `__init__` 宽度参数（01_ARCH §4 预算），`forward` 签名与形状规则两者**完全相同**（分支维度 D 分别为 64/48，由参数携带，不改键与秩）。

## 3. ② 张量形状（字段名 / dtype / shape / 取值范围）

### 3.1 逐形状表（与 01_ARCH §3 数据流图逐形状一致；不一致以本契约为准并回报 lead）

| # | 张量 | dtype | shape | 取值范围 | 语义 / 约束 |
|---|---|---|---|---|---|
| 1 | `images`（输入） | float32 | `(N, 3, 224, 224)` | [-2.1179, 2.6400] | ImageNet 归一化（C-EXPORT-01 §3.1），N ≥ 1 |
| 2 | `stem_out` | float32 | `(N, 32, 56, 56)` | ℝ（无界） | Conv3×3/s2 ×2 + BN + GELU |
| 3 | `trunk_out` | float32 | `(N, 128, 14, 14)` | ℝ（无界） | 深度可分离残差块 ×4，四分支共享主干 |
| 4 | `feat_b`（b=0..3） | float32 | `(N, D)`，D=64 教师 / 48 学生 | ℝ（无界） | 分支 = 深度可分离块 → GAP → Linear(128→D)；行序 = `BRANCH_KEYS` |
| 5 | `branch_feats` | float32 | `(N, 4, D)` | ℝ（无界） | `torch.stack([feat_0..feat_3])`，**行=分支且序=`BRANCH_KEYS`** |
| 6 | `fused_feat` | float32 | `(N, 4·D)` = 教师 `(N,256)` / 学生 `(N,192)` | ℝ（无界） | 四 `feat_b` concat；双头共享输入 |
| 7 | `z`（四子分 logits） | float32 | `(N, 4)` | ℝ（无界） | 每分支 Linear(D→1) 后 stack，序=`BRANCH_KEYS` |
| 8 | `sub`（四子分） | float32 | `(N, 4)` | **[0, 100]** | `sub = 100·sigmoid(z)`；损失/指标用整体视图 |
| 9 | `gate_logits` | float32 | `(N, 4)` | ℝ（无界） | GateMLP：`Linear(4·D→128) → GELU → Linear(128→4)`，输入=`fused_feat` |
| 10 | `gate`（g） | float32 | `(N, 4)` | **（0, 1），每行和 = 1** | `softmax(gate_logits, dim=-1)`，fp32 下行和偏差 atol ≤ 1e-4 |
| 11 | `total` | float32 | `(N, 1)` | **[0, 100]** | `clamp(Σᵢ gate[i]·sub[i], 0, 100)`（张量内逐行点积） |
| 12 | `ranking_logit` | float32 | `(N, 1)` | ℝ（无界） | BT 打分器 `Linear(4·D→128) → GELU → Linear(128→1)`；**仅训练态**，`ScoreOnlyWrapper` 剥离，不进 ONNX（裁决 B） |

### 3.2 训练态输出 dict（六键，键序 = `DICT_KEYS_TRAIN`）

| 键 | dtype | shape | 范围 | 训练 | eval | 进 ONNX |
|---|---|---|---|---|---|---|
| `total` | float32 | `(N, 1)` | [0,100] | ✓ | ✓ | ✓ |
| `composition` | float32 | `(N, 1)` | [0,100] | ✓ | ✓ | ✓ |
| `light` | float32 | `(N, 1)` | [0,100] | ✓ | ✓ | ✓ |
| `creativity` | float32 | `(N, 1)` | [0,100] | ✓ | ✓ | ✓ |
| `story` | float32 | `(N, 1)` | [0,100] | ✓ | ✓ | ✓ |
| `ranking_logit` | float32 | `(N, 1)` | ℝ | ✓ | ✓ | **✗（导出剥离）** |

键↔张量映射：第 i 个分支键 = `sub[:, i:i+1]`（i 序 = `BRANCH_KEYS`），故 **dict 逐键 (N,1)、批量视图 (N,4)**——两者并存不矛盾，AC2 的 `(N,4)` 断言指 §3.1 #7/#8/#10 批量张量与 dict 拼接形状。
`ScoreOnlyWrapper` 输出 = 去 `ranking_logit` 后五键，键序 = `SCORE_KEYS` = C-EXPORT-01 §3.2 输出序（08 S4-02 误差比对按同序 zip）。
门控权重语义：`gate` 即 01_ARCH §3 `g`；`w=(0.3,0.3,0.2,0.2)` 为训练后期**期望**收敛值（示例见 §5），契约不锁死权重数值，只锁 softmax 与行和。

## 4. ③ 错误语义（什么情况抛什么错 / 调用方如何处理）

| # | 触发条件 | 异常类型 | 消息示例 | 调用方处理 |
|---|---|---|---|---|
| E1 | `images.dim() != 4` | `TensorShapeError` | `images: expected rank 4 (N,C,H,W), got 3` | 编程错误（dataloader/预处理 bug），直接修复，**禁止 try/except 后继续训练** |
| E2 | `images.shape[1] != 3` | `TensorShapeError` | `images: expected 3 channels RGB, got 1` | 同 E1；灰度图应在数据层转 RGB（01_ARCH §2） |
| E3 | `H != 224 or W != 224` | `TensorShapeError` | `images: spatial must be 224x224, got 512x512` | 同 E1；resize 属预处理职责，模型层不隐式缩放 |
| E4 | `dtype != torch.float32` | `TensorDtypeError` | `images: expected float32, got torch.float16` | 调用方 `.float()` 或修管线；模型层不做隐式转换（保 ONNX 误差 <1e-3） |
| E5 | `N == 0` | `TensorShapeError` | `images: batch dim must be >= 1, got 0` | 同 E1（空 batch = 数据 bug） |
| E6 | `__init__` 收到 `num_branches != 4` 或通道 ≤0 | `ValueError` | `num_branches must be 4, got 3` | 编程错误直接修复；四维是契约常量不可配 |
| E7 | `gate` 行和偏差 > 1e-4 | `ContractViolationError` | `gate: row sum 0.9173 deviates from 1.0 (atol 1e-4)` | 实现 bug（未 softmax / 融合错误）；修实现，**不改本契约**；08 S3-02 门禁 FAIL |
| E8 | `sub`/`total` 越界（min<0 或 max>100） | `ContractViolationError` | `sub: value -0.04 outside [0,100]` | 实现 bug（缺 100·σ / 缺 clamp）；08 S3-05 门禁 FAIL |
| E9 | 输出 dict 键集或键序 ≠ 契约 | `ContractViolationError` | `output keys {'score'} != DICT_KEYS_TRAIN` | 实现 bug；导出前必须过 `ScoreOnlyWrapper` 断言（裁决 B） |
| E10 | `ScoreOnlyWrapper` 被调用时 `model.training == True` | `ContractViolationError` | `wrapper: model must be eval() before export` | 修调用顺序（先 `.eval()` 再导出，同 C-EXPORT-01 §4 E1） |
| E11 | `images` 含 NaN/Inf | `ContractViolationError` | `images: NaN/Inf detected at [0,0,57,3]` | 数据污染：丢弃该 batch 并记 warning（训练侧）；服务侧归一 400 `invalid_request`（C-SERVE-01 §4 E3） |

通用规则：三类异常均在 `forward` 进入计算图**之前或产出校验时**同步抛出，不吞不包装为占位输出；门禁（08 S3-02/S3-05）以异常是否触发判 FAIL；模型层异常不得直接外泄到 HTTP 层——服务层捕获后按 C-SERVE-01 §4 归一为 400/500。

## 5. ④ 最小示例（真实值，非伪代码）

输入资产 `docs/contracts/assets/example_input_224.npy`：`shape=(1,3,224,224) dtype=float32`，
文件 602240 字节，sha256 `6f990a288431abcf19735edcc29589d6c5fa66f5feaf1238c54e11729b39f93d`；
实测 `min=-1.351285 max=2.248908 mean=0.007190`（生成方式与逐通道统计见 C-EXPORT-01 §5）。

### 5.1 前向输入与中间形状（真实形状，可逐步打印核对）

```python
>>> import numpy as np, torch
>>> from aesthetic_prism.model.hapnet import HAPNet, DICT_KEYS_TRAIN, BRANCH_KEYS
>>> x = torch.from_numpy(np.load("docs/contracts/assets/example_input_224.npy"))
>>> x.shape, x.dtype
(torch.Size([1, 3, 224, 224]), torch.float32)
>>> model = HAPNet(stem_channels=32, trunk_channels=128, branch_feat_dim=64).eval()
>>> model.debug_shapes(x)   # 实现提供的逐步打印（可选辅助，非契约方法）
stem_out   (1, 32, 56, 56)
trunk_out  (1, 128, 14, 14)
feat       (1, 4, 64)      # branch_feats, 行序 = BRANCH_KEYS
fused_feat (1, 256)
z / sub    (1, 4) / (1, 4)
gate       (1, 4)          # softmax 行和 = 1
```

### 5.2 输出 dict（键集与形状断言；数值为代表性示例，标注 = 训练收敛后期代表值，不冒充实测）

```python
>>> out = model(x, return_ranking=True)
>>> list(out.keys()) == list(DICT_KEYS_TRAIN)
True
>>> {k: (tuple(v.shape), str(v.dtype)) for k, v in out.items()}
{'total': ((1, 1), 'torch.float32'), 'composition': ((1, 1), 'torch.float32'),
 'light': ((1, 1), 'torch.float32'), 'creativity': ((1, 1), 'torch.float32'),
 'story': ((1, 1), 'torch.float32'), 'ranking_logit': ((1, 1), 'torch.float32')}
>>> all(0.0 <= v.item() <= 100.0 for k, v in out.items() if k != 'ranking_logit')
True
```

代表性数值（示例：`gate=(0.3,0.3,0.2,0.2)`、四子分 = C-DATA-01 §5 标签）：

```text
z          = [1.289131, 0.905117, 0.658841, 1.077391]   # 100·σ(z) 的逆解 ln(p/(1-p))
sub (N,4)  = [78.4, 71.2, 65.9, 74.6]                    # composition/light/creativity/story
total      = clamp(0.3*78.4 + 0.3*71.2 + 0.2*65.9 + 0.2*74.6, 0, 100) = 72.98   # 图内值
ranking_logit = 1.2                                      # ℝ 无界；仅训练态
```

门控 softmax 行和真实例：`softmax([2.0,1.0,0.5,0.0]) = [0.5793, 0.2131, 0.1293, 0.0784]`
（四项相加 = 1.0001，四舍五入到 4 位的残差；fp32 实算偏差 atol ≤ 1e-4，见 §3.1 #10）。

Bradley-Terry 成对损失真实例（08 S6-03 pairwise 的最小单元）：

```python
>>> import math
>>> r_a, r_b = 1.2, 0.4
>>> p = 1 / (1 + math.exp(-(r_a - r_b))); p, -math.log(p)
(0.689974, 0.371101)    # σ(0.8)=0.689974；loss=-ln p≈0.371101
```

API 层对照（非本契约输出，链路一致性说明）：图内 `total=72.98` → 服务层 `round(x,1)` → 响应 `73.0`（C-SERVE-01 §1 / C-EXPORT-01 §5.1）。

## 6. 验收标准（可执行检查）

```bash
# 1) 四要素小节齐全（①②③④ 标题在位）+ 头部冻结行
sh -c "grep -q '## 2. ① 函数签名' docs/contracts/model_branch_interfaces.md && grep -q '## 3. ② 张量形状' docs/contracts/model_branch_interfaces.md && grep -q '## 4. ③ 错误语义' docs/contracts/model_branch_interfaces.md && grep -q '## 5. ④ 最小示例' docs/contracts/model_branch_interfaces.md && grep -q '已冻结 @2026-11-08' docs/contracts/model_branch_interfaces.md"

# 2) AC2 断言路径字面齐备：(N,64)/(N,4)/键集 + 裁决A五键 + ranking 不进 ONNX + 关键逐形状
sh -c "for k in '(N, 32, 56, 56)' '(N, 128, 14, 14)' '(N, 4, D)' 'composition' 'light' 'creativity' 'story' 'ranking_logit' '不进 ONNX'; do grep -qF \"$k\" docs/contracts/model_branch_interfaces.md || exit 1; done && grep -q 'DICT_KEYS_TRAIN' docs/contracts/model_branch_interfaces.md"

# 3) 与 01_ARCH §3 数据流图逐形状一致（两文件同含 stem/trunk 关键形状字面）
sh -c "for k in '(N,32,56,56)' '(N,128,14,14)'; do grep -qF \"$k\" docs/01_ARCH.md || exit 1; grep -qF \"${k/, /,}\" docs/contracts/model_branch_interfaces.md || grep -qF \"${k/(\(/(}\" docs/contracts/model_branch_interfaces.md || exit 1; done"

# 4) QA 唯一执行源回归（08 S3-02 + S3-05；段3 实现交付后生效）
sh -c "pytest -q tests/test_model.py::test_forward_backward_shapes"
```


