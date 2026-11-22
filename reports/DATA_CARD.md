# DATA CARD — aesthetic-prism 合成数据集（data/synthetic）

## 来源

- 程序化合成：项目内置生成器产出 200 张 224×224（或等比缩放后 224）RGB JPEG，含可控构图扰动、光照梯度、纹理噪声与主体放置变化。
- 无外部数据、无人网抓取、无版权素材：全部图像由代码生成，`source` 字段记录生成配方。
- 生成即标注：标签与图像同源生成（见下「标注」），不存在人工标注环节。

## 构成

> **⚠️ 2026-11-19 修订（goal① 取证）**：本节原文把「test=idx0..19 / val=idx20..39 / train=其余」写成「与 hash 切分等价冻结」——**这句话是错的，也正是指标泄漏的来源**。序号切分与 `split_of(sha256(id)[:8]%20)` 完全不等价：旧序号口径的 20 个 test 样本，在契约 hash 口径下 **20/20 全部属于 train**；序号 val 20 个中 14 个属 train。`bench/metric_recheck.py` 当时按序号切分，因此 S6–S8 的精度数字全部是训练集指标。脚本已修为调用 `schema.split_of`。

- 数量：**2000 张**（原 200；2026-11-19 扩增，旧 200 个 id 的 `image_sha256` 200/200 完全保留，纯新增）。
- 切分（确定性，契约口径 `C-DATA-01 §2.2`：`sha256(id)[:8] % 20`，`<16` train / `<18` val / 其余 test）：
  - N=2000：train **1603** / val **208** / test **189**
  - N=200：train 165 / val 19 / test 16
- 标签结构：每样本 `labels = {composition, light, creativity, story, total}`（0-100）；`total = 0.3c+0.3l+0.2cr+0.2s`，纯函数关系。
- 标签分布（60 样本实测，`error_analysis_data.json.label_std`）：composition 18.2 / light 15.4 / creativity 19.1 / story 18.9 —— 宽谱覆盖，但两端区段样本稀疏。
- 文件完整性：逐样本 `image_sha256` + `bytes` + `width/height` 记录于 index.json，可全量校验。

## 标注流程

- 生成器按配方参数（构图扰动幅度、光照方向、噪声等级等）直接计算四维分值并合成 `total`；同一配方固定 seed 可完全复现（`scripts/goal1_ceiling.py` 实测 2000/2000 标签零误差复现）。
- 量化噪声：分值含受控噪声项（模拟标注噪声），噪声 std 与配方绑定。
- 无二次人工校对；`reports/label_quality.json` 记录标签分布体检。
- 已知契约：512 张校准需求经整表 repeat 补足（`reports/int8_calib.json.calib_note`），oversample 口径已如实记录。

## 局限

1. **域差**：合成图与真实照片/艺术图分布差异显著，模型跨域表现未验证，不可直接用于真实图评分。
2. **规模**：原 200 张（train 165）偏小；已扩至 2000（train 1603）。扩数据实测把契约口径 val mae4 从 14.21 降到 11.76、pairwise 从 0.62 升到 0.726（`reports/goal1_dircheck.json`），方向已验证但未达门限。
3. **标签为先验合成**：四维分值来自生成配方而非人类感知判断，「美学正确性」无外部锚定。
4. **total 冗余**：total 为四维加权纯函数，评分结构上不含额外信息，排序能力主要来自子维学习。
5. **无负样本外推**：生成配方的低分/高分端由参数极值产生，形态单一，模型难以学到真实的「差图多样性」。
6. **参数可观测性已实测**：`scripts/goal1_observability.py` 固定单参数扫描、比对 PNG 逐字节，creativity 的 u/e/L 三项 **0% 用例像素相同**（即全部可见），不存在「标签含不可学习成分」的问题。
