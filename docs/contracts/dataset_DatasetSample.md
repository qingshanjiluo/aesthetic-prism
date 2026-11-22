# 契约 C-DATA-01：DatasetSample（合成样本与标注导出共用）

| 项 | 值 |
|---|---|
| 契约 ID | C-DATA-01 |
| 归属 | ARCH 定义签名与 schema；DATA 实现；QA 验证 |
| 批准状态 | 已冻结 @2026-11-08 03:30（lead 批准，回改须 lead 批准） |
| 修订留痕 | CW-S1-01 @2026-11-08 10:15（lead 批准·W5：坏行方案 B——iter 跳过+结构化 warning line_no 1-based+on_bad_line 汇总；load_dataset_sample 单文件仍 strict；§2.1/§4 E9/§5.5 同步） |
| 已并入裁决 | 裁决 A：标签键五键全链路同名 `total` / `composition` / `light` / `creativity` / `story` |
| 四要素索引 | ① 函数签名=§2 ② JSON 结构=§3 ③ 错误语义=§4 ④ 最小示例=§5 |

## 1. 用途与适用范围

- 合成数据生成器（DATA 段2）、标注平台导出（labeling/）、训练 DataLoader 读入，三处共用**同一个** JSON 对象结构，不做任何字段分叉。
- 存储形态：JSON Lines（`.jsonl`），每行一个 DatasetSample 对象，UTF-8，LF 换行；单样本也可存为单个 `.json` 文件。
- 标签键 `total` / `composition` / `light` / `creativity` / `story` 与 API 响应体、PyTorch 双头 dict key、ONNX 输出名**逐字相同**（裁决 A）。
- 本契约不规定图像文件本身的编码，只规定样本记录对图像文件的引用方式（路径 + sha256 + 尺寸）。

## 2. ① 函数签名（参数名 / 类型 / 返回类型 / 异常类型）

实现文件归属：`src/aesthetic_prism/data/schema.py`（ARCH 定义，DATA 实现，签名不得改动）。

```python
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Literal, None

class DatasetValidationError(ValueError):
    """DatasetSample 校验失败。args[0] 为 str，格式 '<field>: <reason>'。"""

def validate_dataset_sample(sample: dict[str, Any]) -> None:
    """按 §3 JSON Schema + 2 条语义规则校验。通过返回 None；失败抛 DatasetValidationError。"""

def load_dataset_sample(path: str | Path) -> dict[str, Any]:
    """读取单个 .json 样本文件，解码后调用 validate_dataset_sample，返回 dict。"""

def iter_dataset_jsonl(path: str | Path, *, on_bad_line: Callable[[dict[str, Any]], None] | None = None) -> 'Iterator[dict[str, Any]]':
    """逐行读取 .jsonl 并逐条校验；惰性产出合法 dict（过 §3 schema + R1/R2）。
    方案 B（W5/CW-S1-01）：坏行不抛——跳过 + 结构化 warning（line_no 物理行号 1-based，
    形如 bad_line: {"line_no": 2, "error": "invalid json"}），经 logging 与 on_bad_line
    回调汇总；空行静默跳过（计入物理行号）。文件级错误仍抛 FileNotFoundError。"""

def split_of(sample_id: str) -> Literal["train", "val", "test"]:
    """确定性划分，不依赖全局随机源。"""
```

### 2.1 参数与返回明细

| 函数 | 参数名 | 参数类型 | 返回类型 | 抛出异常类型 |
|---|---|---|---|---|
| `validate_dataset_sample` | `sample` | `dict[str, Any]` | `None` | `DatasetValidationError` |
| `load_dataset_sample` | `path` | `str \| pathlib.Path` | `dict[str, Any]` | `FileNotFoundError`, `DatasetValidationError` |
| `iter_dataset_jsonl` | `path` | `str \| pathlib.Path` | `Iterator[dict[str, Any]]` | `FileNotFoundError`（坏文件级；方案 B：坏行不抛，跳过+结构化 warning，见 §4 E9） |
| `iter_dataset_jsonl` | `on_bad_line`（keyword-only，默认 None） | `Callable[[dict[str, Any]], None] \| None` | 同上 | 无（回调内异常属编程错误，上抛） |
| `split_of` | `sample_id` | `str` | `Literal["train","val","test"]` | `DatasetValidationError` |

### 2.2 split_of 算法（确定性，数据契约的一部分）

```text
v = int(hashlib.sha256(sample_id.encode("utf-8")).hexdigest()[:8], 16) % 20
split = "train" if v < 16 else ("val" if v < 18 else "test")   # 80% / 10% / 10%
```

真实值：`split_of("syn_000001")` → `v=15` → `"train"`；`split_of("img_000123")` → `v=19` → `"test"`。
`split` **不是** JSON 存储字段，由 `split_of(id)` 推导；同一 `id` 在任何机器、任何时刻得到相同划分。

### 2.3 调用示例（真实值）

```python
>>> from aesthetic_prism.data.schema import load_dataset_sample, split_of
>>> s = load_dataset_sample("data/synthetic/batch_00/syn_000001.json")
>>> s["id"], split_of(s["id"])
('syn_000001', 'train')
>>> s["labels"]["composition"], round(0.3 * 78.4 + 0.3 * 71.2 + 0.2 * 65.9 + 0.2 * 74.6, 1)
(78.4, 73.0)
```

## 3. ② JSON 数据结构（字段名 / 类型 / 取值范围）

### 3.1 字段表

| 字段 | 类型 | 必填 | 取值范围 / 约束 |
|---|---|---|---|
| `id` | string | 是 | 正则 `^(syn\|img)_[0-9]{6}$`；`syn_*`=合成，`img_*`=标注导出；全库唯一 |
| `image_path` | string | 是 | 相对项目根的 POSIX 路径（禁止 `\`），后缀 `.jpg`/`.jpeg`/`.png`，≤260 字符 |
| `image_sha256` | string | 是 | 64 位小写十六进制，= 图像文件内容 sha256 |
| `bytes` | integer | 是 | 1 … 10,000,000（图像文件字节数） |
| `width` | integer | 是 | 16 … 8192（像素） |
| `height` | integer | 是 | 16 … 8192（像素） |
| `source` | enum | 是 | `"synthetic"` \| `"labeled"` |
| `labels` | object \| null | 是（键必须存在） | 见 3.2；不需要标签时为 `null` |

### 3.2 `labels` 子对象（五键同名，裁决 A）

| 字段 | 类型 | 必填 | 取值范围 |
|---|---|---|---|
| `total` | number | 是 | 0 … 100，≤1 位小数 |
| `composition` | number | 是 | 0 … 100 |
| `light` | number | 是 | 0 … 100 |
| `creativity` | number | 是 | 0 … 100 |
| `story` | number | 是 | 0 … 100 |
| `rater_count` | integer | 条件必填 | 1 … 100；`source=="labeled"` 时必填，`synthetic` 省略 |

语义规则（由 `validate_dataset_sample` 在 schema 之外追加校验）：

- R1：`source == "labeled"` ⇒ `labels` 不得为 `null` 且必须含 `rater_count`。
- R2：`labels` 非 `null` ⇒ 五键（`total`+四子分）同时存在且同时合法，不允许只给部分维度。

### 3.3 JSON Schema（draft 2020-11 → 2020-12，权威定义）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aesthetic-prism.local/contracts/DatasetSample.schema.json",
  "title": "DatasetSample",
  "type": "object",
  "required": ["id", "image_path", "image_sha256", "bytes", "width", "height", "source", "labels"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^(syn|img)_[0-9]{6}$"},
    "image_path": {"type": "string", "pattern": "^[^\\\\]*\\.(jpg|jpeg|png)$", "maxLength": 260},
    "image_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "bytes": {"type": "integer", "minimum": 1, "maximum": 10000000},
    "width": {"type": "integer", "minimum": 16, "maximum": 8192},
    "height": {"type": "integer", "minimum": 16, "maximum": 8192},
    "source": {"enum": ["synthetic", "labeled"]},
    "labels": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "required": ["total", "composition", "light", "creativity", "story"],
          "additionalProperties": false,
          "properties": {
            "total": {"type": "number", "minimum": 0, "maximum": 100},
            "composition": {"type": "number", "minimum": 0, "maximum": 100},
            "light": {"type": "number", "minimum": 0, "maximum": 100},
            "creativity": {"type": "number", "minimum": 0, "maximum": 100},
            "story": {"type": "number", "minimum": 0, "maximum": 100},
            "rater_count": {"type": "integer", "minimum": 1, "maximum": 100}
          }
        }
      ]
    }
  }
}
```

## 4. ③ 错误语义（什么情况抛什么错 / 调用方如何处理）

| # | 触发条件 | 抛出 / 返回 | 异常消息示例（真实格式） | 调用方处理方式 |
|---|---|---|---|---|
| E1 | `sample` 非 dict | `DatasetValidationError` | `root: expected object` | 编程错误，直接修复，不捕获重试 |
| E2 | `id` 缺失或不匹配正则 | `DatasetValidationError` | `id: pattern '^(syn\|img)_[0-9]{6}$' failed` | 批量读取时捕获：丢弃该样本、记 warning、继续下一行；单文件加载时向上抛 |
| E3 | `image_sha256` 非 64 位小写 hex | `DatasetValidationError` | `image_sha256: must match ^[0-9a-f]{64}$` | 同 E2；并把该样本列入数据质检失败清单交 DATA |
| E4 | `width`/`height` 越界（如 8） | `DatasetValidationError` | `width: 8 is less than minimum 16` | 丢弃样本 + warning，不中断 |
| E5 | `source=="labeled"` 但 `labels is null` 或缺 `rater_count` | `DatasetValidationError` | `labels: required for source=labeled` | 指向标注导出流程报 bug 给 DATA，阻断该批次入库 |
| E6 | `labels` 只含部分维度（如缺 `story`） | `DatasetValidationError` | `labels.story: required when labels != null` | 同 E5 |
| E7 | 分数越界（如 `total=120`） | `DatasetValidationError` | `labels.total: 120 is greater than maximum 100` | 同 E5 |
| E8 | 文件不存在（`load_dataset_sample`） | `FileNotFoundError` | 内置 | 路径/产物缺失属硬错误，fail fast，上层转门禁失败 |
| E9 | `.json` 解码失败（单文件）→ 抛；`.jsonl` 行非 JSON 或过不了 §3 校验 → **不抛（方案 B，W5/CW-S1-01）**：跳过 + warning + on_bad_line 汇总 | 单文件 `DatasetValidationError`；JSONL 返回侧无异常 | 单文件 `body: invalid json`；JSONL warning `bad_line: {"line_no": 17, "error": "invalid json"}`（**line_no 物理行号 1-based**，含空行计数） | 单文件上抛 fail fast；JSONL 调用方无需 catch——坏行经 logging 与 on_bad_line 汇总（DATA 段2 门禁核对丢弃数），未产出即不入训练；禁止无记录静默丢弃 |
| E10 | `split_of` 收到不合法 `sample_id` | `DatasetValidationError` | `id: pattern ... failed` | 编程错误，直接修复 |

通用规则：`DatasetValidationError` 是 `ValueError` 子类，只携带人类可读单行消息；**任何调用方不得吞掉异常后继续用未校验数据训练**；门禁中出现未捕获的 `DatasetValidationError` 即判 FAIL。

## 5. ④ 最小示例（真实值，非伪代码）

示例资产：`docs/contracts/assets/example_sample.jpg` —— 48×48 JPEG，666 字节，
sha256 = `0d68a002600799244210f3fee9d34a1dfc4fa23f6b06beda4a42dfded542980c`。

### 5.1 输入：合成样本（带标签，`source="synthetic"`）

`data/synthetic/batch_00/syn_000001.json`：

```json
{
  "id": "syn_000001",
  "image_path": "docs/contracts/assets/example_sample.jpg",
  "image_sha256": "0d68a002600799244210f3fee9d34a1dfc4fa23f6b06beda4a42dfded542980c",
  "bytes": 666,
  "width": 48,
  "height": 48,
  "source": "synthetic",
  "labels": {
    "total": 73.0,
    "composition": 78.4,
    "light": 71.2,
    "creativity": 65.9,
    "story": 74.6
  }
}
```

参考一致性（仅供生成器自检，不作校验规则）：`0.3×78.4 + 0.3×71.2 + 0.2×65.9 + 0.2×74.6 = 72.98 ≈ 73.0`。

### 5.2 输出：调用返回值

```python
>>> load_dataset_sample("data/synthetic/batch_00/syn_000001.json")["labels"]["total"]
73.0
>>> split_of("syn_000001")
'train'
```

### 5.3 标注导出变体（`source="labeled"`，复用同一物理样例图）

```json
{
  "id": "img_000123",
  "image_path": "docs/contracts/assets/example_sample.jpg",
  "image_sha256": "0d68a002600799244210f3fee9d34a1dfc4fa23f6b06beda4a42dfded542980c",
  "bytes": 666,
  "width": 48,
  "height": 48,
  "source": "labeled",
  "labels": {
    "total": 73.0,
    "composition": 78.4,
    "light": 71.2,
    "creativity": 65.9,
    "story": 74.6,
    "rater_count": 5
  }
}
```

```python
>>> split_of("img_000123")
'test'
```

### 5.4 反例（期望异常，真实消息）

```python
>>> validate_dataset_sample({"id": "x", "labels": {"total": 120, "composition": 0, "light": 0, "creativity": 0, "story": 0}, ...})
DatasetValidationError: id: pattern '^(syn|img)_[0-9]{6}$' failed
```

### 5.5 坏行跳过（方案 B，W5/CW-S1-01；行号 1-based）

输入 `demo.jsonl`（3 个物理行，第 2 行坏；空行静默跳过但仍占行号）：

```text
1  {"id": "syn_000001", ...合法...}
2  {broken json
3  {"id": "syn_000003", ...合法...}
```

```python
>>> seen, bad = [], []
>>> for s in iter_dataset_jsonl("demo.jsonl", on_bad_line=bad.append):
...     seen.append(s["id"])
>>> seen
['syn_000001', 'syn_000003']
>>> bad
[{'line_no': 2, 'error': 'invalid json'}]
```

同步 warning（logging，逐字）：`bad_line: {"line_no": 2, "error": "invalid json"}`。
边界：行号=物理行号（1-based，空行计入）；文件不存在仍抛 `FileNotFoundError`（E8）；
单文件 `.json` 坏内容不适用跳过——`load_dataset_sample` 保持 strict 抛（E9，兼容 08 S2-03 逐文件严格校验）。

## 6. 验收标准（可执行检查）

```bash
# 1) 四要素小节齐全（①②③④ 标题均在位），退出码 0/1
sh -c "grep -q '## 2. ① 函数签名' docs/contracts/dataset_DatasetSample.md && grep -q '## 3. ② JSON 数据结构' docs/contracts/dataset_DatasetSample.md && grep -q '## 4. ③ 错误语义' docs/contracts/dataset_DatasetSample.md && grep -q '## 5. ④ 最小示例' docs/contracts/dataset_DatasetSample.md"

# 2) 裁决 A 五键逐字存在于本文档（JSON 字段级匹配）
sh -c "for k in total composition light creativity story; do grep -q \"\\\"$k\\\"\" docs/contracts/dataset_DatasetSample.md || exit 1; done"

# 3) 示例资产真实存在且元数据一致（48×48 不在此校验，sha+字节数必过）
sh -c "python -c \"import hashlib,pathlib; p=pathlib.Path('docs/contracts/assets/example_sample.jpg'); assert p.exists() and p.stat().st_size==666 and hashlib.sha256(p.read_bytes()).hexdigest()=='0d68a002600799244210f3fee9d34a1dfc4fa23f6b06beda4a42dfded542980c'\""

# 4) §5.1 示例 JSON 通过 §3.3 schema（QA 段1 交付后生效）
sh -c "python -m pytest -q tests/contract/test_dataset_sample_contract.py::test_example_matches_schema"
```
