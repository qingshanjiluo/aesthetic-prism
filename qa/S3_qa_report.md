<qa_report batch="3">

# 批3 终判 QA 报告（裁决人：qa2 · 独立裁决 · 2026-11-17）

裁决独立性声明：全部裁决基于 qa2 亲自执行的检查（read_image 逐图实读 10 图、亲自读 cli.py 源码、亲自跑训练、亲自起服务打端点），lead 代采数据仅作交叉参照。

## 1 · Black-box S3-02..06

证据：`qa/evidence/S3/blackbox_S3.log`（SUM_RC=0）+ 逐项 log。

| 项 | 内容 | 结果 | 证据 |
|---|---|---|---|
| S3-02 | forward/backward shapes（pytest 单测） | **PASS**（EXIT=0） | S3-02.log |
| S3-03 | 20-step loss descent（loss_desc=OK n=20；head5 222.82→tail5 51.53） | **PASS**（EXIT=0） | S3-03.log, S3-03_train.log |
| S3-04 | checkpoint roundtrip（pytest） | **PASS**（EXIT=0） | S3-04.log |
| S3-05 | output range 0-100（pytest） | **PASS**（EXIT=0） | S3-05.log |
| S3-06 | 渲染/评分复验（pixel_diff_pass15 15/15, max_corr 0.448） | **PASS**（S3-06_EXIT=0） | S3-06.log, S3-06_run.log |

**小节：Black-box S3-02..06 = 5/5 PASS。**

## 2 · White-box 修复验证 W-3-02/03/04（qa2 亲自读 `src/aesthetic_prism/train/cli.py` + 亲自跑训练）

| 项 | 验证点 | 实测 | 判定 |
|---|---|---|---|
| W-3-02 (S3-P1) | L_reg 四维子项 per-sample ¼ 权重 | cli.py:126-140 `regression_loss`：`sub_se = 0.25 * (pred_sub - subs).pow(2).sum(dim=-1)`（(B,) per-sample ¼Σ_k e²），batch 归约 `.mean()` 在最后。docstring 明记 per-sample 语义 + test_train_loss.py 锁 1/4。稀释 bug 已修复 | **PASS** |
| W-3-03 (S3-P2) | train/val dual-split loading（val=19） | cli.py:756-780：train 与 val 双路加载、永不同一对象；实测 `python -m src.train --steps 2` 输出 `[data] real data/synthetic/index.json split=train labeled=165 split=val labeled=19` | **PASS** |
| W-3-04 (S3-P3) | stage_criteria + meets_criteria 输出 | cli.py:244-275 `stage_criteria`（val PAcc_rank≥0.65 / mae4≤5.0 且 pairwise≥0.68），`meets_criteria` 字段写进 bundle（cli.py:314）与日志；val 缺失时显式 null 不伪造（cli.py:599-637） | **PASS** |
| 训练冒烟 | `PYTHONPATH=src` 下 `python -m src.train --steps 2` | EXIT=0，loss 454.7→358.2 | **PASS** |

**小节：White-box 修复 3 项 + 训练冒烟 = 全 PASS。**

## 3 · S2-05 标注质量抽样（qa2 独立裁决）

- 10 图（syn_000180/125/128/175/117/071/035/099/094/173）qa2 全部 read_image 亲自实读打分，SHA256 与 export 一致。
- 独立裁决：合格 5/10（#1,3,8,9,10），不合格 5/10（#2,4,5,6,7：story Δ=30.7/34.4/42.9/47.2 四样超阈 + #7 light Δ=39.1），低于 ≥9/10 门禁。
- **S2-05 = FAIL**。处置 = DATA 侧 story/light 维系统性标注偏移 → 退回重标 → 重新导出 → 重新抽样复检。
- 证据：`qa/evidence/S2/S2-05.md`（QA 独立裁决版）。

## 4 · D-双端复验（qa2 亲自执行）

| 项 | 实测 | 判定 |
|---|---|---|
| 服务启动 | `uvicorn aesthetic_prism.serve.app:app --port 8000` 起服务 | OK |
| GET /health | HTTP 200，`{"status":"ok","ready":true,"model":"mock-deterministic-v1"}` | **PASS** |
| GET / | HTTP 200 | **PASS** |
| POST /upload（multipart `image=`，真图 syn_000180.png） | HTTP 200，返回 `{"path":"data/uploads/syn_000180-409df9c7.png","width":224,...}`；假 PNG 字节被正确拒 400 invalid_request | **PASS** |
| Desktop 快捷方式 | `C:\Users\Administrator\Desktop\Aesthetic Prism.lnk` 存在 = True | **PASS** |
| emoji 扫描 frontend\*.py | 0 命中 | **PASS** |
| emoji 扫描 frontend\index.html | 0 个装饰性 emoji；仅 2 处 U+2192 `→`（第 357/359 行 API 说明文案符号，非 emoji） | **PASS**（注：如验收口径要求连 U+2192 也禁，则该 2 处需替换；非 emoji 域命中） |

## 第 3 节（批3）Gate

**Gate = FAIL。**

结论行：Black-box 5/5 PASS + White-box 修复 3/3 PASS + D 双端复验全 PASS，但 S2-05 标注质量抽样 qa2 独立裁决 FAIL（5/10 < 9/10 门禁，story 维系统性偏高 + light 维双向偏移），批3 整体不达标。

处置：DATA 侧退回——对 S2-05 不合格样本（syn_000125 / syn_000175 / syn_000117 / syn_000071 / syn_000035）重标 story/light 两维 → 重新 export → 重新抽样复检（复检通过后批3 才可收口）。

## 5 · S2-05-r2 复检（qa3 独立裁决 · 2026-11-17）

- DATA 已对 5 个不合格样本重标 story/light（主源 `data/synthetic/index.json` → 重跑 labeling.annotate → 3 rater 确定性重生成），产出新导出 `data/annotations/export_20261116-171534.json`。
- 复检抽样：同 10 样本全量抽样，10 图均由 qa3 逐张 `read_image` 独立实读打眼值（图片 sha256 与新导出逐条比对一致），未采信 DATA 预填。
- 独立裁决：**合格 10/10 ≥ 9/10 门禁**；单维最大 Δ = 5.7（#3 syn_000128 story），全部 ≤30。5 个重标样本（#2/#4/#5/#6 story、#7 light）新 Δ 分别为 1.9 / 2.3 / 2.1 / 0.9 / 2.9。
- **S2-05-r2 = PASS**。证据：`qa/evidence/S2/S2-05-r2.md`（qa3 独立裁决版，含逐图眼值/Δ/判定）。

## 6 · 冻结抽验（qa3 · 2026-11-17）

未修复样本在新旧导出间逐字段对比（qa3 亲自执行）：

| 样本 | 对比字段 | 旧 export_20261110-094811 | 新 export_20261116-171534 | 结果 |
|---|---|---|---|---|
| syn_000180 | composition/light/creativity/story/total/rater_count/image_sha256 | 46.3 / 27.9 / 54.2 / 66.4 / 46.4 / 3 / ab4006… | 完全一致 | ✅ 一致 |
| syn_000094 | composition/light/creativity/story/total/rater_count/image_sha256 | 40.6 / 25.4 / 80.9 / 63.6 / 48.7 / 3 / b24ee4… | 完全一致 | ✅ 一致 |

冻结结论：重标仅影响 5 个目标样本的 story/light 与随公式更新的 total；未修复样本标注值完全冻结，旧导出未被改动。

## 批3 Gate 终判（改判 · qa3 · 2026-11-17）

**Gate = PASS（由 FAIL 改判）。**

改判依据：批3 此前 FAIL 的唯一阻塞项为 S2-05 标注质量（qa2 裁决 5/10 < 9/10）。DATA 侧按处置完成 5 样本 story/light 重标并重新导出后，qa3 独立复检（S2-05-r2）裁决 10/10 合格，且冻结抽验确认其余样本标注未受影响。Black-box 5/5 PASS、White-box 修复 3/3 PASS、D 双端复验全 PASS 维持不变。

最终结论行：Black-box 5/5 PASS + White-box 修复 3/3 PASS + D 双端复验全 PASS + S2-05-r2 复检 10/10 PASS（qa3 独立裁决）+ 冻结抽验一致 → **批3 Gate = PASS，批3 达标可收口。**

</qa_report>
