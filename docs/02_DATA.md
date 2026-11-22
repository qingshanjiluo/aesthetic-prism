# 02 数据方案（DATA：合成数据 + Dataset + 划分 + 质检）

| 项 | 值 |
|---|---|
| 文档 ID | D-DATA-02 |
| 归属 | DATA 起草，lead 批准；段 2 实现照单执行 |
| 状态 | 草案 |
| 关联契约 | C-DATA-01（docs/contracts/dataset_DatasetSample.md）、C-EXPORT-01 §3.1（归一化）、docs/00_PRD.md、docs/08_ACCEPTANCE.md（S2-01/S2-04/S3-01） |
| 裁决 | A=五键同名 `total`/`composition`/`light`/`creativity`/`story`；C=qa/ 归 QA（本档只读）；D=命令走 sh -c |

## 1. 职责范围与目录归属

DATA 只负责：合成数据生成器、torch Dataset、标注平台前后端、导出 schema（04_LABELING.md）。不碰模型结构与训练循环；数据格式变更须 lead 批准并由 ARCH 回写契约。

```text
aesthetic-prism/
├── data/                          # DATA 所有
│   ├── synthetic/
│   │   ├── index.json             # {meta:{...}, samples:[DatasetSample,...]}（S2-01 计数依据）
│   │   └── batch_00/syn_000001.png …   # 图像 + 同名 .json 单样本（C-DATA-01 §5.1 形态）
│   ├── annotations/               # 标注平台运行数据（详见 04_LABELING.md）
│   │   ├── schema.json            # 导出 schema（S2-03 校验对象）
│   │   └── export_*.json          # 每次导出一份（S2-02 计数依据）
│   └── exports/                   # 汇总 DatasetSample JSONL（训练入料，UTF-8/LF）
├── src/aesthetic_prism/data/      # 段 2 实现：schema.py（契约签名）+ dataset.py（本档 §3）
├── labeling/                     # 标注平台前后端（04_LABELING.md）
└── qa/                           # QA 所有，DATA 只读（裁决 C）
```

## 2. ① 合成数据方案（几何图形 + 噪声 + 可控参数空间）

**目标量**：段 2 门禁 `N ≥ 200`（S2-01，硬下限）；设计目标 **5000 条**（`data/synthetic/index.json` 的 `samples` 长度），生成器按 `--n` 分批落盘，幂等可复跑。

**可复现性**：`rng_seed = int(sample_id 后 6 位)`，numpy `Generator(PCG64(rng_seed))`；同一 `id` 在任何机器生成逐字节相同的 PNG 与标签（PNG 编码固定 `optimize=False`、无时间戳元数据）。

**生成流水线**（单样本四步）：

1. **画布**：尺寸从 `{224, 384, 512, 768}` 按 rng 抽取（正方形），RGB PNG；背景 = 双线性渐变（起点/终点色相、方向角 θ 均为参数）。
2. **几何图形层**：形状 ∈ {圆, 矩形, 三角, 星形, 环, 多边形(n=5..8)}；数量 1..12；每图有位置 (x,y)、尺寸、旋转、透明度 α、填充/描边风格。
3. **光影层**：点光源位置 (lx,ly)、衰减指数 γ∈[0.5,4]、暗角强度 v∈[0,0.8]、对比度 c∈[0.6,1.6]、高斯噪声 σ∈[0,12]、颗粒种子。
4. **构图/叙事元素**：三分法网格锚点、视觉重量偏移、引导线（地平线/斜向路径）、多主体关系（1..3 个"视线方向"箭头、前后景层次）。

**参数空间（全参数可学差异的来源）**：

| 维度 | 主控参数 | 取值范围 |
|---|---|---|
| `composition` | 主体锚点与三分法距离 d₃、视觉重量方差 w、留白比 g | d₃∈[0,1]（0=压角，1=精确落点）；w∈[0,1]；g∈[0.1,0.7] |
| `light` | 光源-主体距离 d_L、对比度 c、暗角 v、噪声 σ | d_L∈[0,1]；c∈[0.6,1.6]；v∈[0,0.8]；σ∈[0,12] |
| `creativity` | 形状组合新颖度 u（模板外组合概率）、旋转/尺寸抖动熵 e、图层数 L | u∈[0,1]；e∈[0,1]；L∈[1,4] |
| `story` | 主体数 k、引导线存在 b、前后景层次 h、关系箭头 r | k∈[1,12]；b∈{0,1}；h∈[0,1]；r∈{0,1,2,3} |

**标签公式（确定性、无随机，保证可学）**——四个子分各由其主控参数经单调打分函数合成，裁到 [0,100] 保留 1 位小数：

```text
composition = round(100·(0.55·d₃ + 0.25·(1−|w−0.5|·2) + 0.20·(1−|g−0.35|/0.35)), 1)
light       = round(100·(0.40·(1−d_L) + 0.30·(1−|c−1.1|/0.5) + 0.20·(1−v/0.8) + 0.10·(1−σ/12)), 1)
creativity  = round(100·(0.50·u + 0.30·e + 0.20·min(L,3)/3), 1)
story       = round(100·(0.40·min(k,6)/6 + 0.25·b + 0.20·h + 0.15·min(r,3)/3), 1)
total       = round(0.3·composition + 0.3·light + 0.2·creativity + 0.2·story, 1)   # 权重与 C-DATA-01 §5.1 一致
```

**如何产生可学的审美差异**：

- 每维参数在生成批次内按**分层网格 + 均匀抖动**覆盖全值域（不是高斯挤在中段），保证 0–100 各分数段都有样本、标签分布近似均匀（分箱 0–100 每 10 分一箱，每箱 ≥2% 样本，质检见 §5）。
- 同一画布可派生"对照兄弟"：固定 rng 主种子，仅扰动单维参数（如把主体从三分法锚点挪到正中），产生**标签差 ≥10 分**的成对样本，供 Bradley-Terry 成对素材与排序可学性验证；兄弟样本共享 `family_id = rng_seed 基值`，划分按 §4 防泄漏。
- `total` 与子分为纯函数关系，无噪声注入 → 模型可解析地学到门控加权（与 C-EXPORT-01 §3.2 的 `clip(Σ wᵢ·subᵢ)` 同构）。
- **旧键禁用**：全链路只允许 `total`/`composition`/`light`/`creativity`/`story`，禁止任何历史键名。

## 3. ② torch Dataset 与预处理（与 onnx 契约逐字一致）

实现文件：`src/aesthetic_prism/data/dataset.py`（DATA 实现；schema 读取复用 C-DATA-01 §2 的 `iter_dataset_jsonl(path, *, on_bad_line=None)` / `validate_dataset_sample`，签名不得改动）。

**输入**：`data/exports/*.jsonl`（合成 + 标注导出合并后的 DatasetSample JSONL，UTF-8/LF）。坏行处理按 C-DATA-01 §4 E9 **方案 B**（CW-S1-01）：`iter_dataset_jsonl(path, *, on_bad_line=None)` 对坏行**跳过**（不抛），发结构化 warning `bad_line:{"line_no":N,"error":...}`（N = 物理行号 1-based，空行静默占号），经 `on_bad_line` 回调汇总——**任何被跳过的坏行计入质检失败清单**（禁止无记录静默丢弃）；文件不存在仍抛 `FileNotFoundError`。单文件入口 `load_dataset_sample` 保持 **strict**，坏内容仍抛 `DatasetValidationError`（段 2 单样本调试与 S2-03 逐文件校验的严格性不变）。

**归一化（与 docs/01_ARCH.md §2 表及 C-EXPORT-01 §3.1 逐字一致，不得自定义）**：

```text
x = (pixel/255 - mean)/std,  mean=(0.485,0.456,0.406),  std=(0.229,0.224,0.225)
理论值域 [-2.1179, 2.6400]（0 → -2.1179，1 → 2.6400，逐通道）
```

**预处理管线（唯一定义，训练/评测/对照服务同一份代码）**：

1. 解码 RGB（PIL `Image.open(...).convert("RGB")`；RGBA/调色板/灰度统一转 RGB，PNG 不带 alpha 直接取三通道）。
2. 双线性 resize 到 **224×224**（`Image.BILINEAR`；短边先按比例缩放再中心裁剪到正方，非正方形图先补灰边再裁，避免拉伸形变）。
3. `ToTensor` → float32 `[0,1]` → 减 mean 除 std → `(3,224,224)` float32。
4. 训练期增强（仅 `split=="train"` 且 `augment=True`）：随机水平翻转 p=0.5、±15° 内随机仿射、亮度/对比度 ±10%；**不改变标签**（增强只在线上，不落盘新样本，见 §4 防泄漏）。

**`__getitem__` 返回结构（键名固定）**：

```python
{
  "image":  torch.float32,        # (3, 224, 224)，ImageNet 归一化
  "labels": torch.float32,        # (4,) = [composition, light, creativity, story]，顺序固定、值域 [0,100]
  "total":  torch.float32,        # 标量，[0,100]
  "id":     str,                  # 原样透传，用于 split_of/去重/追溯
}
```

`DataLoader(batch_size=B, collate_fn=default_collate)` 后：`x.shape == (B,3,224,224)`、`label.shape == (B,4)` 且 `label ∈ [0,100]` —— 正对 S3-01 断言；`total` 为 `(B,)`。四子分顺序 `(composition, light, creativity, story)` 与 HAP-Net 四分支/ONNX 输出顺序（C-EXPORT-01 §3.2）同序。

**split 过滤**：Dataset 构造参数 `split: Literal["train","val","test"] | None`，内部用 C-DATA-01 §2.2 `split_of(id)` 过滤；JSONL 中**不存** split 字段（契约明确 split 不是存储字段）。

## 4. ③ 划分与防泄漏策略

**唯一划分算法** = C-DATA-01 §2.2 `split_of`（sha256，80/10/10），本档无第二实现：

```text
v = int(hashlib.sha256(sample_id.encode("utf-8")).hexdigest()[:8], 16) % 20
split = "train" if v < 16 else ("val" if v < 18 else "test")   # 80% / 10% / 10%
```

真实值锚点：`split_of("syn_000001") → "train"`（v=15）、`split_of("img_000123") → "test"`（v=19）。

**防泄漏规则（硬约束）**：

1. **同源图禁跨 split**：一张图（一个 `image_sha256`）在全库只允许对应**一个** `id`；生成器与标注导出共用 `sha256 → id` 注册表（`data/synthetic/index.json` 的 `meta.sha256_index`），同一图像内容二次入库复用既有 id，不生成新 id。同源对照兄弟（§2 family）因共享基种子，其 id 段统一在 `syn_000000..` 内按家族前缀分配——**家族内所有 id 先本地试算 `split_of`，命中多 split 的家族在生成期直接重排 id 后缀**（枚举 id 后 6 位直至全家族同一 split；同家族 id 前缀不同但同 split），并把重排记录写入 `meta.family_split_map` 供质检 §5.4 断言。
2. **增强不落盘**：翻转/仿射/抖动只在线上生成（§3 步 4），禁止落盘为新样本 id——否则同一视觉内容会以不同 id 撒进不同 split。
3. **划分只在读取侧计算**：JSONL 与 index.json 不存 split 字段；任何脚本需要 split 一律 `from aesthetic_prism.data.schema import split_of`，禁止在别处复写 sha256 逻辑。
4. **分布自检**：生成完成后统计三 split 占比，容差 ±5%（5000 条量级下 80/10/10 的二项波动远小于 5%；`N=200` 下允许 ±8%），偏差超限换 id 重排并记录，不改算法。

## 5. ④ 质检流程（生成后逐批执行，产物落 `qa/evidence/` 只读由 QA 归档，DATA 自检输出到 `data/synthetic/qc_report.json`）

| # | 检查项 | 方法 | 通过阈值 |
|---|---|---|---|
| 1 | 数量门禁 | `len(index.json['samples'])` | ≥200（S2-01 硬门禁；目标 5000） |
| 2 | 100% 可解码 | PIL `Image.open().verify()` 遍历 `image_path` | 失败 = 0（S2-04） |
| 3 | 逐样本 schema | `validate_dataset_sample` 跑遍 index（严格，异常=0）；JSONL 读取用 `iter_dataset_jsonl(*, on_bad_line=cb)`（方案 B）汇总坏行 | 单文件异常 = 0；JSONL 坏行数计入 qc `failures`（=0 才 pass）；五键齐备率 100%（R2） |
| 4 | 元数据一致 | 重算 sha256/bytes/width/height 与样本记录比对 | 不一致 = 0 |
| 5 | 防泄漏 | 同 `image_sha256` 只一 `id`；`meta.family_split_map` 全家族单 split；split 占比 ±5%(N=200 ±8%) | 违规 = 0 |
| 6 | 标签分布 | 四子分 + total 各按 10 分一箱直方图 | 每箱占比 ≥2%（5000 条）；N=200 时每箱 ≥1 条的箱 ≥8/10 |
| 7 | 公式回算 | 由样本标签重算 `0.3c+0.3l+0.2cr+0.2s` vs `total` | 绝对差 ≤0.1（1 位小数舍入内） |
| 8 | 对照兄弟有效性 | family 内 max−min `total` | ≥10 分的 family 占比 ≥30% |
| 9 | id 唯一 + 格式 | 正则 `^(syn\|img)_[0-9]{6}$` 全匹配 | 重复 = 0，违例 = 0 |
| 10 | 可复现性 | 同 id 二次生成逐字节比对 | sha256 全等 |

qc_report.json 结构：`{"checked": int, "pass": bool, "failures": [{"check": str, "ids": [...]}], "split_ratio": {...}, "hist": {...}}`；任一 check 失败 → `pass=false`，段 2 门禁按 FAIL 处理，禁止静默截断续跑。

## 验收标准（可执行检查，裁决 D：一律 `sh -c`；工作目录=项目根 `aesthetic-prism/`）

> 生效时点：1–3 为段 2/段3 门禁（生成器与 dataloader 落地后跑，QA 归档 `qa/evidence/S2/`、`qa/evidence/S3/`）；4–6 为本文档自身检查，现即生效。

```bash
# 1) S2-01 合成样本 ≥200（data/synthetic/index.json 的 samples 计数）
sh -c "python -c \"import json;d=json.load(open('data/synthetic/index.json'));n=len(d['samples']);print('samples=',n);assert n>=200,n\""

# 2) S2-04 全部合成图像 100% 可解码（PIL verify，失败清单为空则退出码 0）
sh -c "python -c \"exec('def _verify(p):\n    try:\n        Image.open(p).verify()\n        return True\n    except Exception:\n        return False');import json,sys;from PIL import Image;d=json.load(open('data/synthetic/index.json'));bad=[s['image_path'] for s in d['samples'] if not _verify(s['image_path'])];print('bad=',bad);sys.exit(1 if bad else 0)\""

# 3) S3-01 dataloader 形状：x=(B,3,224,224)、label=(B,4) 且 label∈[0,100]（tests/test_data.py）
sh -c "python -m pytest -q tests/test_data.py::test_dataloader_shape"

# 4) 裁决 A 五键逐字在位（反引号包裹、键级匹配；逐字面量写出，避开外层 shell 变量展开）
sh -c "grep -q '\`total\`' docs/02_DATA.md && grep -q '\`composition\`' docs/02_DATA.md && grep -q '\`light\`' docs/02_DATA.md && grep -q '\`creativity\`' docs/02_DATA.md && grep -q '\`story\`' docs/02_DATA.md"

# 5) 三历史键名零残留（模式以括号自避，不与本文文本自匹配；命中任一即 FAIL）
sh -c "! grep -qE 'colo[u]r|light[in]g|det[a]il' docs/02_DATA.md"

# 6) split 算法唯一引用 C-DATA-01 §2.2（sha256 80/10/10 字面在位，且本文声明不复写）
sh -c "grep -q '% 20' docs/02_DATA.md && grep -q '禁止在别处复写 sha256 逻辑' docs/02_DATA.md"
```

判定：1–3 退出码 0 = 段2/段3 对应门禁通过；4–6 现在即可跑，0 通过即本文档合规。
