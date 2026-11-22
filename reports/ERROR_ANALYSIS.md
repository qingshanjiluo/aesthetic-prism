# 错误分析报告（ERROR_ANALYSIS）— aesthetic-prism student.onnx

- 评估口径：60 张合成样本（seed=42 随机抽样），ONNX student（147k 参数，KD 3000 step），ImageNet 归一化 224×224。
- 数据源：`reports/error_analysis_data.json`；图：`reports/figs/composition_*.png`、`reports/figs/light_*.png`、`reports/figs/score_dist.png`。
- 结论先行：**MAE 超标的主因是模型欠拟合（输出动态范围塌缩 + 高分/低分区段系统性偏差），次因是 composition / creativity 两维的学习难度最高。**

## 1. 按维度误差分解（60 样本）

| 维度 | per-dim MAE | pred std | label std | 判读 |
|---|---|---|---|---|
| composition | **13.35** | 9.17 | 18.18 | 压缩最重（std 比 0.50），误差最大 |
| light | 7.24 | 10.69 | 15.45 | 相对最好（std 比 0.69） |
| creativity | **14.10** | 6.65 | 19.12 | 压缩最严重（std 比 0.35），输出几乎坍到窄带 |
| story | 9.16 | 15.69 | 18.87 | std 尚可但绝对误差居中 |

- creativity 与 composition 是 MAE 超标（val 10.1 / test 8.2 vs 门限 5.0）的主要贡献维度。
- 四维 pred std 均小于 label std —— KD student 的典型欠拟合形态：回归到条件均值附近、两端预测不足。

## 2. 低分样本归因（gt_total 最低 10 张）

见 `error_analysis_data.json.lowest_gt_total_10`。模式：gt_total < 30 的样本，四维预测普遍被拉向 40-60 的中带（均值回归），低分区 |err| 平均高于全区均值 —— **模型缺少对"差图"的区分能力**，与合成标签生成器（噪声叠加）中低分段的更强噪声相关。

## 3. 高分歧样本 Top-10（按 mae4 降序）

| 样本 | mae4 | 主要偏差维度 |
|---|---|---|
| syn_000154 | 28.6 | creativity/composition |
| syn_000071 | 26.9 | creativity/composition |
| syn_000148 | 24.5 | composition |
| syn_000131 | 22.2 | creativity |
| syn_000165 | 19.7 | composition/creativity |
| syn_000197 | 19.4 | creativity |
| syn_000189 | 17.7 | composition |
| syn_000151 | 16.0 | composition/creativity |
| syn_000008 | 15.9 | light |
| syn_000025 | 14.4 | composition |

- 10 张最差样本中 8 张偏差集中在 composition 或 creativity —— 与 §1 的维度分解一致。
- 抽查（见 `composition_heatmap.png`）：gt 落在两端区段（<30 或 >70）时误差显著高于中段。

## 4. 构图分支（composition）归因 — T-7-03

- `composition_heatmap.png`：按 gt 分段 × 预测十分位的平均 |err| 热力图。**两端区段（gt<30、gt>80）误差带宽度约为中段的 2 倍**；中段（40-60）模型输出密集、误差相对可控。
- `composition_error_heat.png`：逐样本排序误差长尾分布，Top 20% 样本贡献了约一半的总误差。
- 归因结论：composition 维度 label std=18.2 而剪枝后 branch_feat_dim=39 的窄学生容量不足以覆盖全谱；训练样本仅 160 张 train split，两端区段样本稀疏。

## 5. 光影分支（light）归因 — T-7-04

- `light_hist.png`：gt 直方图宽谱（15-95），pred 直方图集中于 35-65 —— 与 §1 压缩形态一致，但程度最轻。
- `light_scatter.png`：散点整体贴对角线趋势，斜率 <1（系统性收缩）；无系统性符号翻转，说明该分支学到了正确的方向仅幅度不足。

## 6. 修复方向（记录，不在本阶段执行）

1. 提高训练强度：KD steps 3000 → ≥10000，LR 后段衰减保持，观察 stage2 mae4 曲线拐点。
2. 扩数据：合成数据 200 → ≥2000（生成器成本低），消除两端区段稀疏。
3. 学生容量：branch_feat_dim 39 → 64（预算 <10M 允许），优先给 creativity/composition。
4. 校准只能修 bias，已证明不能修 MAE（`metric_recheck_calibrated.json` val 9.98 / test 8.47），不作为修复路径。
