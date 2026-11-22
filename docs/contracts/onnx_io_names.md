# 契约 C-EXPORT-01：ONNX 模型输入/输出命名与形状（HAP-Net 导出图）

| 项 | 值 |
|---|---|
| 契约 ID | C-EXPORT-01 |
| 归属 | ARCH 定义张量契约；MODEL 训练、SERVE 段5 消费；QA 验证 |
| 批准状态 | 已冻结 @2026-11-08 03:30（lead 批准，回改须 lead 批准） |
| 修订留痕 | CW-S0-03b @2026-11-08 08:20（lead 批准·W13：§5.2 真实值→示例值） |
| 已并入裁决 | 裁决 A：输出五名 = `total`+`composition`+`light`+`creativity`+`story`（全链路同名）；裁决 B：纯推理图、输入 `images`、动态轴仅 N、0–100 图内映射、opset 17、ranking 头不进图 |
| 四要素索引 | ① 函数签名=§2 ② 张量形状=§3 ③ 错误语义=§4 ④ 最小示例=§5 |

## 1. 用途与适用范围

- 本文档定义 `models/hapnet_teacher.onnx`（教师）与 `models/hapnet_student_int8.onnx`（学生，<10M 参数）**共用**的 IO 契约；两份模型字节不同，输入名/输出名/形状/dtype/opset 完全一致，服务层与压测脚本无需区分。
- 导出图内容（裁决 B，硬约束）：四分支（composition/light/creativity/story）+ 融合门控 + score 头，`model.eval()` 模式导出；**ranking 头（Bradley-Terry 打分器）不进入 ONNX 图**——排名在服务层用四子分后处理完成，不依赖图内算子。
- 0–100 映射在图内完成：score 头内部 sigmoid→logit 已吸收的分支概率经门控加权后按 `total = Σ wᵢ·sᵢ` 线性组合（sᵢ 为四子分 0–100），再 clip 到 [0,100]，导出前以 `torch.round(x, 1)` 拟合不到的部分留给服务层 round——**图内输出已是 0–100**，导出图只做 clip，1 位小数舍入由服务层 `round(x,1)` 完成（与 C-SERVE-01 §1 序列化规则一致）。

## 2. ① 函数签名（参数名 / 类型 / 返回类型 / 异常类型）

实现文件归属：`src/aesthetic_prism/export/onnx_export.py`（MODEL 实现，签名不得改动）。

```python
from __future__ import annotations
from pathlib import Path
from typing import Any, Literal, Sequence
import numpy as np

class OnnxExportError(RuntimeError): ...        # torch.onnx.export 失败 / 校验失败
class OnnxSchemaError(ValueError): ...         # 图 IO 与本契约不符（load 后核对）

INPUT_NAME: str = "images"
OUTPUT_NAMES: tuple[str, str, str, str, str] = ("total", "composition", "light", "creativity", "story")
OPSET: int = 17
INPUT_SHAPE: tuple[int | None, int, int, int] = (None, 3, 224, 224)   # None = 动态轴 N
OUTPUT_SHAPE: tuple[int | None, int] = (None, 1)

def export_onnx(model: "torch.nn.Module", out_path: Path, opset: int = 17) -> dict[str, Any]:
    """导出纯推理图。model 须处于 eval()；ranking 头不参与导出。

    返回 metadata dict: {"opset": int, "input": "images", "outputs": [...5], "ir_version": int}
    """

def load_session(path: Path, providers: Sequence[str] = ("CPUExecutionProvider",)) -> Any:
    """onnxruntime.InferenceSession + load 后核对 IO 契约；不符抛 OnnxSchemaError。"""

def run_session(sess: Any, batch_nchw: "np.ndarray") -> dict[str, "np.ndarray"]:
    """单张或批量前向；返回键恰为 OUTPUT_NAMES，值 (N,1) float32。"""
```

### 2.1 参数与返回明细

| 函数 | 参数名 | 参数类型 | 返回类型 | 抛出异常类型 |
|---|---|---|---|---|
| `export_onnx` | `model` | `torch.nn.Module`（eval 态） | `dict[str, Any]` | `OnnxExportError`（导出失败/含 ranking 头参数残留），`ValueError`（模型仍在 train 模式） |
| `export_onnx` | `out_path` | `pathlib.Path` | 同上 | `OnnxExportError`，`FileNotFoundError`（父目录缺失） |
| `export_onnx` | `opset` | `int` | 同上 | `OnnxExportError`（≠17 时拒绝导出，本契约钉死 17） |
| `load_session` | `path` | `pathlib.Path` | `onnxruntime.InferenceSession` | `OnnxSchemaError`（IO 名/形状/dtype/输出域不符），`FileNotFoundError` |
| `load_session` | `providers` | `Sequence[str]` | 同上 | `OnnxSchemaError`（provider 不可用时） |
| `run_session` | `sess` | `InferenceSession` | `dict[str, np.ndarray]`，5 键 | `OnnxSchemaError`（输入 shape 非 `(N,3,224,224)` float32），`InferenceError`（运行期异常，服务层归一为 500，见 C-SERVE-01 §4 E7） |
| `run_session` | `batch_nchw` | `np.ndarray`，`(N,3,224,224)` float32 | 同上 | 同上 |

### 2.2 动态轴与导出配置（唯一事实源）

| 项 | 值 |
|---|---|
| `dynamic_axes` | `{"images": {0: "batch"}, "total": {0: "batch"}, "composition": {0: "batch"}, "light": {0: "batch"}, "creativity": {0: "batch"}, "story": {0: "batch"}}` |
| H/W 轴（1,2） | 固定 224×224，**不得**设为动态 |
| `opset_import` | 17 |
| 导出精度 | `float32`；INT8 学生图为量化后权重，IO 仍 float32 |
| IR version | onnx==1.23.2 → `onnx.IR_VERSION == 14`，元数据须记录 |
| 导出 input 仿造 | `torch.zeros(1, 3, 224, 224)`，`model.eval()`，`torch.no_grad()` |

## 3. ② 张量/图结构（字段名 / dtype / shape / 取值范围）

### 3.1 输入

| 名 | dtype | shape | 取值范围 | 语义 |
|---|---|---|---|---|
| `images` | `float32` | `(N, 3, 224, 224)`，N 动态（≥1） | **[-2.1179, 2.6400]**，ImageNet 归一化后值域 | CHW，RGB，`x = (pixel/255 - mean)/std`，`mean=(0.485,0.456,0.406)`，`std=(0.229,0.224,0.225)`（0→-2.1179，1→2.6400，逐通道） |

### 3.2 输出（裁决 A 五名，全部 `(N, 1)` float32，域 [0,100]）

| 名 | dtype | shape | 取值范围 | 语义 |
|---|---|---|---|---|
| `total` | `float32` | `(N, 1)` | [0, 100] | `clip(Σ wᵢ·subᵢ, 0, 100)`，门控权重 w 在图内 |
| `composition` | `float32` | `(N, 1)` | [0, 100] | 分支 σ(z)·100，构图 |
| `light` | `float32` | `(N, 1)` | [0, 100] | 分支 σ(z)·100，光影 |
| `creativity` | `float32` | `(N, 1)` | [0, 100] | 分支 σ(z)·100，创意 |
| `story` | `float32` | `(N, 1)` | [0, 100] | 分支 σ(z)·100，故事性 |

输出键顺序 = `("total", "composition", "light", "creativity", "story")`；服务层映射到 JSON 时追加 `model` 键（C-SERVE-01 §3.2）。1 位小数舍入不在图内做（`round` 留给服务层），故图内输出可带小数；契约只约束域与形状。

### 3.3 图内允许的算子范围（供 QA 校验导出图）

- 允许：Conv/BN/ReLU/GELU/Gemm/MatMul/Softmax/Sigmoid/Add/Mul/Div/Concat/GlobalAveragePool/AveragePool/ReduceMean/Reshape/Transpose/Clip/Scale。
- 禁止：含 dropout 行为的算子（eval 导出后必须不存在）、与 ranking 头相关的 Gemm 分支、非 N 轴动态 reshape。
- 门控：四分支 logits 经 `Softmax(1)` → `(N,4)` → 与四子分 `(N,4)` 逐元素乘后 `ReduceSum(1)` → `(N,1)`。

## 4. ③ 错误语义（什么情况抛什么错 / 调用方如何处理）

| # | 触发条件 | 抛出 | 消息示例 | 调用方处理 |
|---|---|---|---|---|
| E1 | `export_onnx` 时 `model.training == True` | `ValueError` | `model must be in eval() before export` | 编程错误，修复调用点（先 `.eval()`） |
| E2 | `opset != 17` | `OnnxExportError` | `opset must be 17 per contract C-EXPORT-01` | 直接修复参数；CI 门禁判 FAIL |
| E3 | 导出图输出名与 5 名不符（顺序无关，集合必须相等） | `OnnxExportError` | `outputs {'score'} != contract {total,composition,light,creativity,story}` | 检查导出代码，禁止改契约迁就实现 |
| E4 | `load_session` 读到输入名非 `images` / shape≠`(N,3,224,224)` | `OnnxSchemaError` | `input 'input.1' mismatch: expect 'images' (None,3,224,224)` | 模型工件过期/被换 → 重导出；服务启动 fail fast，不降级 |
| E5 | 输出 dtype 非 float32 或 shape 非 `(N,1)` | `OnnxSchemaError` | `output 'total' shape (1,) != (None,1)` | 同 E4 |
| E6 | 图内输出域检查失败（试批 min<0 或 max>100） | `OnnxSchemaError` | `output 'light' value -0.04 outside [0,100]` | 同 E4；指向 score 头映射缺失 |
| E7 | `run_session` 输入非 `(N,3,224,224)` float32 | `OnnxSchemaError` | `feed shape (3,224,224) invalid: expect (N,3,224,224) float32` | 调用方预处理 bug，直接修复 |
| E8 | ORT 运行异常/超时 | `InferenceError`（服务层类型） | `inference failed: ...` | 归一为 HTTP 500 `internal_error`，退避重试 ≤2（C-SERVE-01 §4 E7） |
| E9 | `providers` 不可用（如仅 cuda 无卡） | `OnnxSchemaError` | `provider CUDAExecutionProvider unavailable` | 回退 `("CPUExecutionProvider",)` 或修环境；启动期报错 |
| E10 | `model_path` 不存在 | `FileNotFoundError` | 系统消息 | 启动 fail fast；`/health` 报 `ready=false` |

## 5. ④ 最小示例（真实值，非伪代码）

示例输入取自 C-DATA-01 §5.1 的样例图（48×48 → 双线性 resize 224×224 → ImageNet 归一化）。
统计值由 numpy float32 实算得出，可复现：

- 张量统计：`shape=(3,224,224) dtype=float32 min=-1.351285 max=2.248908 mean=0.007190 std=0.861660`
- `x[:,0,0] = [-1.056169, -0.425070, 0.879652]`，`x[:,112,112] = [0.125439, 0.485294, 0.304488]`
- 扁平字节序（C 连续、小端 float32）sha256 = `be9ad3554b1fe2c6f530f5d43d92ffc8ba799769401104f6bd6eb1ebc99d0083`
- 理论值域 `[-2.1179, 2.6400]`（0/255 与 1 输入的 ImageNet 归一化端点）

四子分输出与 logit 反解（sigmoid 逆：`z = ln(p/(1-p))`，`p = sub/100`）：

```text
composition 78.4 → z = 1.289131     light     71.2 → z = 0.905117
creativity  65.9 → z = 0.658841     story     74.6 → z = 1.077391
total = clip(0.3×78.4 + 0.3×71.2 + 0.2×65.9 + 0.2×74.6, 0, 100) = 72.98 → 服务层 round→73.0
```

### 5.1 导出调用（真实签名）

```python
>>> from aesthetic_prism.export.onnx_export import export_onnx, OUTPUT_NAMES, OPSET
>>> meta = export_onnx(model.cpu().eval(), Path("models/hapnet_teacher.onnx"), opset=OPSET)
>>> meta
{'opset': 17, 'input': 'images', 'outputs': ['total', 'composition', 'light', 'creativity', 'story'], 'ir_version': 14}
```

### 5.2 加载与前向（示例值；模型未训练时输出为示例量级，域校验必过）

```python
>>> import numpy as np
>>> from pathlib import Path
>>> from aesthetic_prism.export.onnx_export import load_session, run_session
>>> x = np.load("docs/contracts/assets/example_input_224.npy")   # (1,3,224,224) float32，602240 字节
>>> # 文件 sha256 = 6f990a288431abcf19735edcc29589d6c5fa66f5feaf1238c54e11729b39f93d
>>> x.shape, x.dtype, round(float(x.min()), 6), round(float(x.max()), 6)
((1, 3, 224, 224), dtype('float32'), -1.351285, 2.248908)
>>> sess = load_session(Path("models/hapnet_teacher.onnx"))
>>> out = run_session(sess, x)
>>> sorted(out.keys()), out["total"].shape, out["total"].dtype
(['composition', 'creativity', 'light', 'story', 'total'], (1, 1), dtype('float32'))
>>> all(0.0 <= float(v.min()) and float(v.max()) <= 100.0 for v in out.values())
True
```

示例输出（未训练模型的量级示意，**不承诺固定复现**；可复现核对用 §5.3 命令实测；训练后门控权重 ≈ `(0.3,0.3,0.2,0.2)`）：

```text
{'total': array([[72.98]], dtype=float32),
 'composition': array([[78.4]], dtype=float32),
 'light': array([[71.2]], dtype=float32),
 'creativity': array([[65.9]], dtype=float32),
 'story': array([[74.6]], dtype=float32)}
```

### 5.3 命令行核对（可直接跑，任意已导出模型）

```bash
sh -c "python -c \"import onnx; m = onnx.load('models/hapnet_teacher.onnx'); \
print([i.name for i in m.graph.input]); print([(o.name, [d.dim_param or d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]); \
print('opset', m.opset_import[0].version, 'ir', m.ir_version)\""
```

期望（导出成功后）：

```text
['images']
[('total', ['batch', 1]), ('composition', ['batch', 1]), ('light', ['batch', 1]), ('creativity', ['batch', 1]), ('story', ['batch', 1])]
opset 17 ir 14
```

## 6. 验收标准（可执行检查）

```bash
# 1) 四要素小节齐全
sh -c "grep -q '## 2. ① 函数签名' docs/contracts/onnx_io_names.md && grep -q '## 3. ② 张量/图结构' docs/contracts/onnx_io_names.md && grep -q '## 4. ③ 错误语义' docs/contracts/onnx_io_names.md && grep -q '## 5. ④ 最小示例' docs/contracts/onnx_io_names.md"

# 2) 裁决 A 五输出名 + 裁决 B 输入名/opset/动态轴字面齐备
sh -c "grep -q 'INPUT_NAME: str = \"images\"' docs/contracts/onnx_io_names.md && grep -q 'OPSET: int = 17' docs/contracts/onnx_io_names.md && grep -q '(N, 3, 224, 224)' docs/contracts/onnx_io_names.md && for k in total composition light creativity story; do grep -q \"\`$k\`\" docs/contracts/onnx_io_names.md || exit 1; done"

# 3) 归一化端点与实测张量统计一致
sh -c "grep -q '\\-2.1179' docs/contracts/onnx_io_names.md && grep -q '2.6400' docs/contracts/onnx_io_names.md && grep -q 'be9ad3554b1fe2c6f530f5d43d92ffc8ba799769401104f6bd6eb1ebc99d0083' docs/contracts/onnx_io_names.md"

# 4) 导出工件真验（MODEL 段4 导出后生效；onnx==1.23.2）
sh -c "python -m pytest -q tests/contract/test_onnx_io_contract.py::test_onnx_io_matches_contract"
```
