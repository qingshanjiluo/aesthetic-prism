# 段2 白盒审查 whitebox_S2.md（QA 独立审查方 · 2026-11-10 08:06 CST）

读面（6 件）：labeling/{annotate,security,app}.py、src/aesthetic_prism/data/{schema,synthetic,dataset}.py、data/exports 格式、reports 两 json、07_PLAN 段2 行。
证据：qa/evidence/S2/wb2_checks.log（7086B）+ wb2_checks2.log + {wb2_checks.sh,wb2_checks2.sh,wb2_assert.py,wb2_identical.py,wb2_artifacts.py}。

## f2 假复标嫌疑（第 1 白盒面）→ **排除，三重证据**

1. **代码种子独立**：annotate.py L26-38 `_rng(f"{rater}:{sid}:rate")` —— seed 串首段 = `r01:`/`r02:`/`r03:` 三个互异前缀，sha256 派生，**非同一种子、非抄一份**；`_rate(true, rater, sid)` = true四维 + `rng.gauss(0,8)` 独立噪声 + clip[0,100]。
2. **实测分值真抖动**（wb2_identical.py）：3 session 文件 × 10 样本 = 120 维度对比，diff_mean=**8.99** ≈ 独立理论值 E|N(0,√(8²+8²))|=8√(2/π)·√2=**9.02** 强吻合；diff_max=32.7。若同种子/抄数，120 个 diff 应全 0。
3. **identical 仅 2/120 且均 RAW_EQUAL**：syn_000099 与 syn_000125 的 r01/r02 light 维同值（50.3/43.7，非 clip 边界）。独立抽样下 P(|Δ|<0.05)≈0.0035/次 → λ=0.42，P(X≥2)≈0.067（尾内）；聚簇 r01/r02 概率 1/9≈0.11——均不显著。
4. **agreement=0.975 与独立噪声自洽**：40 维（10×4）stdev>15 期望 ≈0.2 次，实测 1 次 → 0.975 落理论带内，非"高得可疑"。
→ 嫌疑**排除**；label_quality.json 数值可信（生成器孤儿问题另见 P3）。

## a) synthetic 四维公式 vs 02_DATA L55-59 → **公式字面一致 ✓，但同节生成流水线违契约 → 具体问题 S2-P1**

公式逐项对照（synthetic.py L79-83 ↔ 02_DATA L55-59）：comp 0.55/0.25/0.20 ✓、light 0.40/0.30/0.20/0.10 ✓、creat 0.50/0.30/0.20+min(L,3)/3 ✓、story 0.40/0.25/0.20/0.15+min 截断 ✓、total 0.3/0.3/0.2/0.2 ✓、round 1 位 ✓、参数域 g∈[0.1,0.7] c∈[0.6,1.6] v∈[0,0.8] σ∈[0,12] L∈[1,4] k∈[1,12] r∈[0,3] 全对上；各维权重和=1、项非负 → 值域 [0,100] ✓。**W8 括号修复后的移植无数值语义偏差。**

## c) dataset 防泄漏双实现漂移 → **排除（单实现实测）**：`grep def split_of|% 20` 全树（src/labeling/tests, 排 pycache）仅 **schema.py L127/L131 一处**；dataset.py L19/L63、assert_no_leakage L85、tests L61 全部 import 复用；无第二套 sha 逻辑。

## d) W9 全拼路径点位 → **全过**：annotate.py L36(`_rate`)/L57(`_write_session`) 均 `_validate_rater_id` **先于**路径拼接；app.py L49 validate → L54 拼接（PATH POINT 1/1 注释在位）；白名单 `^[A-Za-z0-9_-]{1,32}$`（security L7）禁 `..`/`/`/`\`/非 ASCII；`rd_001.jsonl` round_id 为字面常量不经用户输入 → **无绕过点、无裸拼接**。

## e) 8 行三参 assert 真验 → **正则跨列误匹配，实测 8/8 语法合法（无需 RW-S2-QA-02）**

wb2_assert.py（落盘法，AST 级强于 py_compile）：S0-03/S1-03/S2-03/S3-03/S4-01/S6-03/S6-06/S8-02 → **ast_ok=8, ast_fail=0**。
标 THREE_ARG_SUSPECT 的 2 处（S3-03、S6-06）为**我检测器误报**：`ast.Assert` 语法节点恒为二元 (test, msg)，msg=Call（如 `assert len(L)>=20, len(L)`、`assert mx<=5.0, mx` 的 tuple/函数调用）是合法两参——**三参在 parse 层必 SyntaxError（S2-08 原病即此），8 行全 parse 成功即证明无三参**。lead 正则命中的是 `assert cond,(tuple 内逗号)` / 表格列间逗号的跨列误匹配。
→ 结论：**误匹配安全，8/8 实测语法合法**；RW-S2-QA-02 **不开**。

## 产物存在性（07_PLAN 段2 行）→ 9/9 EXISTS（index/annotations/SOURCES/data_bias/label_quality/pairs/gold/schema/exports 目录）；export=1 文件；`data/exports/*.jsonl`=**0**——04 §4.2 明示 JSONL 汇编属段4 范围外，非缺陷。

## 具体问题（3 项，协议 ≥1 达标）

| # | 问题 | 依据（行号/实测） | 归属 | 验收点 |
|---|---|---|---|---|
| **S2-P1** | **标签参数与图像渲染完全解耦 + 02 §2 生成流水线 4 层只实现 2 层**：`_labels(rng)`（L70）消费的是 `_gradient`/`_shapes` **之后的独立随机流**——d₃（三分法锚点距离）不控制任何画面、v/σ（暗角/噪声）无渲染、引导线/视线箭头/前后景（story 层）整层缺失、画布固定 256（02: {224,384,512,768}）、形状 3 种×1–2 个（02: 6 种×1–12）、"对照兄弟 family"机制无实现（04 黄金题依赖它）、分层网格→纯 uniform 抽样、`_rng` 种子算法偏离 02 字面（sha256(seed:id) vs int(id 后 6 位）→ **标签学不到画面**：段6 pairwise≥0.68 数学上不可能达（≈0.5 上限），段3 S3-03 还可能假过 | **DATA**（02_DATA §2 字面 vs synthetic.py） | **段3 前置**（现无 S 条目覆盖可学性——S2-05 的 >30 阈值对中段数值解耦不敏感，人眼先见标签有锚定效应；建议 lead 增补 S 条目或把 02 §5 QC#7/#8 接线） |
| **S2-P2** | **标注质量机制三缺**：①四维黄金题 **0/2 道**（04 §2 硬下限≥2；annotate rate 记录 L92-94 无 is_gold，gold.jsonl 仅成对题）②`w_r/q_r/acc_r/mad` 全未实现（grep 0 命中）——_aggregate L41-47 等权下"中位数锚定+加权修正"**退化为纯算术均值**（med+Σ(v-med)/n≡mean），04 §3.2「单人极端值打不飞」的抗差设计失效；批降权路径只写 verdict 串（L112/L133）未作用于聚合 ③pairs_non_gold=10 < 04 §1.1「≥12 组/轮」 | **DATA**（04_LABELING §1.1/§2/§3 字面 vs annotate.py） | 段2 收口前定夺（质量门禁缺实现=黄金题 acc 机制形同虚设，若 lead 判阻塞则 RW-S2-02） |
| **S2-P3** | **label_quality.json 孤儿工件**：`grep -rn label_quality`（labeling/scripts/src/tests/Makefile）=**0 命中**，生成器不在代码库 → 主控代跑 f2 产物不可复跑（**代跑违反实现方自证原则**，按 lead 授权记明） | DATA + 主控代跑（已知登记） | 不判 FAIL（登记）；建议 DATA 把生成逻辑落 `labeling/quality.py` 或 `scripts/` 使 f2 可复现，段3 验收时复跑 |

## 人工复核：**0 项**（f2/c/d/e/a 五面全部实测闭环，无遗留人工项）

白盒结论：**具体问题 3 项（S2-P1 可学性解耦为最重，S2-P2 质量机制三缺，S2-P3 已登记），协议 ≥1 达标**；排除项 4（f2 种子独立/公式字面一致/split 单实现/W9 全点位/8 行 assert 合法）。
