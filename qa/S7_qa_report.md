# S7 QA 报告 — 段7：图表 / 卡片 / 复现性

日期：2026-11-19 　QA 人：石井（独立复核） 　结论：**4/4 PASS**（mae4 门限失败为既有段6结论，如实携带，不阻断 S7 复现性判定）

## S7-01 图表（≥4 张 PNG，每张 >10KB）— PASS

- `reports/figs/` 实测 8 张 PNG，全部 >10KB（23,139B ~ 73,810B）：
  composition_error_heat 30,831 / composition_heatmap 35,608 / distill_curves 69,319 /
  latency_hist 34,708 / light_hist 23,139 / light_scatter 44,005 / metric_compare 38,595 / score_dist 73,810。
- 证据：`qa/evidence/S7/S7-01.log`。判定：8 ≥ 4，PASS。

## S7-02 MODEL_CARD 分节（用途/指标/局限/复现）— PASS

- grep 锚定 `^#+ .*(用途|指标|局限|复现)` 全部命中（用途=True 指标=True 局限=True 复现=True）。
- 指标表如实记录：pairwise val 0.8158 / test 0.9101 PASS；pearson 0.8564 / 0.9564 PASS；
  mae4 val 10.092 / test 8.196 **FAIL**（>5.0，未软化）。局限列 6 条（绝对分误差、域差、
  动态范围坍缩、INT8 无收益、224×224 固定、无排序头）。产物 sha256 与字节数在卡内可核对
  （student.onnx 575,538B / int8 274,625B）。
- 证据：`qa/evidence/S7/S7-02.log` + `reports/MODEL_CARD.md`。PASS。

## S7-03 DATA_CARD 分节（来源/构成/标注/局限）— PASS

- grep 锚定 `^#+ .*(来源|构成|标注|局限)` 全部命中。200 张（train 160 / val 20 / test 20），
  标签 std composition 18.2 / light 15.4 / creativity 19.1 / story 18.9，生成器计算标签 + 受控噪声，
  512 张校准集重复使用问题已在 `reports/int8_calib.json.calib_note` 与局限节如实标注。
- 证据：`qa/evidence/S7/S7-03.log` + `reports/DATA_CARD.md`。PASS。

## S7-04 复现性（make reproduce exit 0 + 复算与报告一致 ≤1e-6）— PASS

- 修复记录：`src/aesthetic_prism/bench/metric_recheck.py` 原以 `round(x, 4)` 落盘导致记录值与
  复算值差 7.96e-06~4.71e-05（S7-04.log 曾 RECHECK-FAIL）。已改为全精度 float 落盘并重跑。
- 复算比对（`python src/eval.py --recheck --against reports/metric_recheck.json`）：
  6 项指标全部 OK，最大 diff 1.11e-16（test.pearson），RECHECK-PASS，EXIT=0。
  test：pairwise 0.910053 / pearson 0.956420 / mae4 8.195879；
  val：pairwise 0.815789 / pearson 0.856392 / mae4 10.091954。
- `make reproduce`（Git sh 执行，裁决 D）：数据体检（新增 `src/aesthetic_prism/bench/data_audit.py`，
  DATA-AUDIT-PASS n=200 missing=0）→ metric_recheck 全精度复算 → 1e-6 比对 →
  AP_MODE=mock pytest 63 passed → 契约键自检 OK，EXIT=0。
- 复现口径冻结在 `configs/repro/repro_constants.txt`（切分/预处理/seed=42/门限）。
- mae4 门限 FAIL（val 10.092 / test 8.196 > 5.0）为真实结论：复算 JSON `gate_mae_pass=false`，
  与 MODEL_CARD/ERROR_ANALYSIS 一致，复现性判定不因此受阻。
- 证据：`qa/evidence/S7/S7-04.log`、`qa/evidence/S7/S7-04-reproduce.log`、`reports/metric_recheck.json`。PASS。

## 独立判断备注

1. S7-04 首跑失败根因是写盘精度而非算法偏差——修复后 0 人工调参即对齐到机器精度，
   说明训练→评测→落盘链路确定性成立。
2. 复现命令与验收命令口径统一为 `reports/metric_recheck.json`（全精度）；`reports/metrics.json`
   中 6 位小数记录值与全精度差 <1e-6，两者同源。
3. mae4 失败是模型质量问题，不是复现问题；段8 FINAL_ACCEPTANCE 须继续如实列出。

## ⚠️ 2026-11-19 追加修订（goal① 取证）

本报告中引用的精度数字（mae4 8.196/10.092、pairwise 0.9101/0.8158、Pearson 0.9564/0.8564）来自 ench/metric_recheck.py，该脚本当时按「id 排序序号」切 split，与训练侧契约口径 C-DATA-01 §2.2 split_of(sha256(id)[:8]%20) 不同源。

泄漏量化：旧口径 test 20 个样本在契约口径下 **20/20 全属 train**。故上述数字全部作废。

契约口径真实值：val (n=19) pairwise 0.5497 / Pearson 0.1551 / mae4 14.2705；test (n=16) pairwise 0.4622 / Pearson 0.0062 / mae4 14.7202 —— **三项全 FAIL**。见 eports/contract_split_metrics.json、eports/MAE4_ROOT_CAUSE.md。

eports/MODEL_CARD.md 与 eports/DATA_CARD.md 中的精度引用需按本节重读。
