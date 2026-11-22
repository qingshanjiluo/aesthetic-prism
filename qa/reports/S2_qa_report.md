# <qa_report batch="2">

段2（50% 数据标注闭环）QA 终审报告 · Aesthetic Prism · QA 独立审查方 · 2026-11-10 08:25 CST
依据：docs/08_ACCEPTANCE.md（唯一执行源，47 条基线）；证据根：qa/evidence/S2/ + qa/evidence/S0/regression_S2.log + qa/evidence/S1/regression_S1.log
执行环境：Git sh（落盘法，pipefail=ON + 每块 rc=$? 聚合）；工作目录 = aesthetic-prism/；契约 = C-DATA-01（方案 B 坏行）+ C-SERVE-01（六档）。

---

## blackbox（黑盒验证：只按 08 原文命令跑，不看实现代码）

开审前快照：`ls -la docs/ src/ tests/ labeling/ data/ reports/ configs/ > qa/evidence/S2/snapshot.txt`（exit=0，**74 行 / 3395B**，06:07 固化）。

### 段2 黑盒 9 条（8 条命令 + 1 条人工）

| 条目 | 判定 | 命令要点（08 原文，sh 落盘法） | 输出摘录 | 证据 |
|---|---|---|---|---|
| S2-01 | **PASS** | `python -c "…len(d['samples']);assert n>=200"` | `samples= 200` EXIT=0 | qa/evidence/S2/S2-01.log |
| S2-02 | **PASS** | printf→S2-02.py（cnt 无回退）\| tee | `files= 1 entries= 10` EXIT=0 | S2-02.log/.py |
| S2-03 | **PASS** | `jsonschema.validate` 逐 export | `validated 1` EXIT=0 | S2-03.log |
| S2-04 | **PASS** | PIL verify 全量 | `bad= []`（total=200）EXIT=0 | S2-04.log |
| S2-05 | **PASS**（[人工复核]） | 10 条全量抽样逐图 read_image 过目，四维 标注/人眼/Δ 表 | 合格 **10/10**，Δmax=28.0（syn_000173 crea 擦线 <30），次高 25.6 | **S2-05.md** |
| S2-06 | **PASS**（本条目首跑真判） | printf→S2-06.py（split_of 复算+双路泄漏断言） | `n=200 stored_mismatch=0 pair_overlap=0 sha_cross=0 leak=0` EXIT=0 | S2-06.log/.py |
| S2-07 | **PASS** | SOURCES.csv sha256×三列非空覆盖 | `covered=1 total=1` EXIT=0 | S2-07.log |
| S2-08 | **PASS**（**RW-S2-QA-01 自改后重跑**） | printf→S2-08.py（双参断言+字段链适配） | `agreement= 0.975 n= 10` EXIT=0 | S2-08.log/.py |
| S3-01 | **PASS**（**RW-S2-01 闭环后复跑**） | `pytest -q tests/test_data.py::test_dataloader_shape` | `1 passed` EXIT=0 | qa/evidence/S3/S3-01.log |

**两条 FAIL→修复→翻绿的完整证据链（判给文档侧/自己侧，DATA 零返工以外的自有问题）**：

1. **S3-01 首跑 FAIL**（exit=4 `no match in [Module test_data.py]`）：08/00_PRD AC1/07_PLAN **三源一致**写 `test_dataloader_shape`，DATA 实现起名 `test_s3_01_dataloader_shape` = **跨件命名漂移**。裁决（主控 CW 修正版）：**契约三源不动、实现对齐契约 → RW-S2-01 退 DATA 改名**；DATA 执行完毕（def=1、旧名残留=0、mtime 06:51），QA 复跑节点原命令 = **1 passed**。08 的 S3-01 行全程未改。
2. **S2-08 首跑 FAIL**（`SyntaxError`）：**08 自身命令三参 assert 缺陷**（`assert rate is not None, float(rate)>=0.70, rate` —— 第三参必 SyntaxError），根因=命令写入时未做 sh -n/py_compile。QA **自改 08**（RW-S2-QA-01，lead 授权）：拆 4 条双参断言 + printf 落盘法 + 字段链适配 `metric="relabel_agreement"` 字符串指针结构；阈值语义 0.70/n>0 不变；改后 `agreement=0.975 n=10` 真值 PASS。报告披露：**自改，属 08 归 QA 的执行源缺陷修复**。

### QA 自有 runner 缺陷族（白盒第 4 条，已修/待补，不判 FAIL）

- **SUM_RC 聚合假绿（已修）**：首版 blackbox_S2.sh 各块 `cmd | tee; echo EXIT=$?` —— `echo` 吃掉 `$?`，S2-08_EXIT=1/S3-01_EXIT=4 实报 `SUM_RC=0`。修法=每块 `rc=$?; rc_all+=rc`，末行 `exit $rc_all`；修后本轮 `SUM_RC=0` 为真值（全 9 绿）。**与已知#1 tee 吞码同族，在我自己的门禁脚本复发**——白盒第 1 素材，根因定位完整。
- **boot-wait 环缺指纹断言（待补）**：S1 回归 S1-01 的 health 等待环首 curl 拿到 200 疑为 **node(0.0.0.0) 回落应答**（boot_wait=0）——判例#4 场景活实证；门禁本体 `kill -0` 20s 存活不依赖该 curl，且 S1-02/03 指纹断言确证我方服务真起，**S1-01 判 PASS 不动摇**；bootstrap 环待补 `grep mock-deterministic-v1`。
- 本批全程使用独立 python 复跑取真退出码（pipefail=ON），tee 吞码未污染任何判定。

blackbox 结论：**段2 九条 9/9 PASS**（S2-06 新条目首跑真判全绿、S2-05 人工 10/10、S3-01 经 RW-S2-01 闭环 1 passed、S2-08 经 RW-S2-QA-01 自改 0.975/10 PASS）。

---

## whitebox（白盒审查：读实现找契约未覆盖边界；证据 qa/evidence/S2/whitebox_S2.md 6511B + wb2_checks{,2}.log）

读面 6 件：labeling/{annotate,security,app}.py、src/aesthetic_prism/data/{schema,synthetic,dataset}.py + data/exports 格式 + reports 两 json + 07_PLAN 段2 行。

### 3 个具体问题（协议 ≥1 达标；分诊 = 主控裁决版）

| # | 问题 | 依据 | 分诊/归属 | 验收点 |
|---|---|---|---|---|
| **S2-P1** | **标签参数与图像渲染部分解耦（可学性）**：`_labels(rng)`（synthetic L70-84）消费的是 `_gradient`/`_shapes`（L89-90）**之后的独立随机流**——d₃（三分法锚点）不控制任何画面元素、v/σ（暗角/噪声）无渲染效应、story 层（引导线/视线箭头/前后景）整层未渲染、画布固定 256（02 §2：{224,384,512,768}）、形状 3 种×1–2 个（02：6 种×1–12）、对照兄弟 family 机制无实现（04 黄金题依赖其「同画布只扰单维」）、分层网格→纯 uniform、`_rng` 种子算法偏离 02 字面（sha256(seed:id) vs int(id 后 6 位)）。**推论：标签与画面弱相关 → 模型可学信号趋零 → 段6 pairwise≥0.68 数学上不可达（≈0.5 上限）**；S2-05 的 >30 抽查对中段数值解耦不敏感（人眼抽的是图像合理性，测不出「同图配错签」），本批黑盒与人工双盲区、白盒唯一捕获 | **段3 前置阻塞件，退 DATA 开 RW-S2-03**；修法方向=四维参数全部进入渲染管线（构图锚点驱动主体摆放、v/σ 驱动暗角噪声、story 层画关系元素、creativity 驱动形状组合多样性），种子回 02 字面 | 段3 开审前 RW-S2-03 修复；**QA 义务：段3 开审时增补 S3-06 可学性断言**（同参数扰动→图像可测变化，或分维特征-标签相关系数下限；亦可接 02 §5 QC#7/#8） |
| **S2-P2** | **标注质量机制三缺**：①四维黄金题 **0/2 道**（04 §2 硬下限≥2；annotate rate 记录 L92-94 无 `is_gold`，gold.jsonl 仅成对题）②`w_r/q_r/acc_r/mad` 全未实现（grep 0 命中）——`_aggregate` L41-47「中位数锚定+加权修正」**退化为纯算术均值**（med+Σ(v−med)/n ≡ mean），04 §3.2 抗差设计失效；批降权只写 verdict 串（L112/L133）未作用于聚合 ③pairs_non_gold=10 < 04 §1.1「≥12 组/轮」 | **段4 前置，不判 RW**（裁决表 E：标注平台完整功能=段4；段2=最小闭环已达标——成对/四维/黄金题存在性/导出过 schema 全过）。黄金题 0 道**危及 S2-05 可信吗**：S2-05 抽的是四维聚合值 vs 画面观感，不依赖黄金题机制 → **不危及，维持不 RW** | 段4 标注完整功能工单必含四件套：四维黄金题≥2、w_r·q_r·acc_r·mad 真实现（中位数锚定不退化均值）、pairs≥12、降权落数值不落 verdict 串 |
| **S2-P3** | **label_quality.json 孤儿工件 + 代跑**：`grep -rn label_quality`（labeling/scripts/src/tests/Makefile）=**0 命中**，生成器不在代码库；该文件系主控代跑 f2 产物——**违反实现方自证原则**（按 lead 授权记明） | **登记不判 FAIL**（已知登记项） | 段4：label_quality 生成并入 labeling 工具链使 f2 可复跑（消除孤儿态）；段3 QA 复跑核对 0.975 可复现性 |

### 4 项嫌疑排除（实测论证，非走过场）

1. **f2 假复标嫌疑 = 排除（agreement=0.975 判可信）**：①代码种子独立——`_rng(f"{rater}:{sid}:rate")`（annotate L26-38），r01:/r02:/r03: 三互异前缀 sha256 派生，非同种子非抄一份；②实测真抖动——3 session×10 样本 120 维对比 `diff_mean=8.99 ≈ 独立理论值 9.02`（E|N(0,√128)|=16√(2/π)/√2… 实算 8√(2/π)·√2=9.02），diff_max=32.7；③identical 仅 2/120 且均 RAW_EQUAL（syn_000099/125 r01-r02 light），独立下 P(|Δ|<0.05)≈0.0035→λ=0.42，P(X≥2)≈0.067 尾内，聚簇 r01/r02 概率 1/9≈0.11 不显著；④0.975=39/40 与独立噪声 stdev>15 期望≈0.2 次自洽——**三重证据闭合**。
2. **synthetic 四维公式 vs 02_DATA L55-59 = 字面一致**：comp 0.55/0.25/0.20 ✓、light 0.40/0.30/0.20/0.10 ✓、creat 0.50/0.30/0.20+min(L,3)/3 ✓、story 0.40/0.25/0.20/0.15+min ✓、total 0.3/0.3/0.2/0.2 ✓、round1 ✓、参数域与权重和=1 全对上——W8 括号修复后移植**无数值语义偏差**（问题在渲染耦合面，不在公式面）。
3. **dataset 防泄漏 = 单实现无漂移**：`grep def split_of|% 20` 全树（src/labeling/tests 排 pycache）**仅 schema.py L127/L131 一处**；dataset.py L19/L63、assert_no_leakage L85、tests L61 全 import 复用，无第二套 sha 逻辑。
4. **W9 全拼路径点位 + 8 行 assert 真验**：annotate L36/L57、app L49→L54 均 `_validate_rater_id` **先于**拼接，白名单 `^[A-Za-z0-9_-]{1,32}$`，round_id=字面常量——**无绕过无裸拼**；8 行（S0-03/S1-03/S2-03/S3-03/S4-01/S6-03/S6-06/S8-02）AST 级 **ast_ok=8 ast_fail=0** → lead 正则命中系**跨列逗号误匹配**，S3-03/S6-06 的 THREE_ARG_SUSPECT 是我检测器误报（assert 语法节点恒二元，msg=tuple/Call 合法）——**RW-S2-QA-02 不开**。

### runner 缺陷族（第 4 条，QA 自有，不判 FAIL）

- SUM_RC 聚合假绿：**已修**（每块 rc=$? 累加 + pipefail，本批 SUM_RC=0 真值）；与已知#1 tee 吞码同族在 QA 门禁脚本复发，根因=`echo EXIT=$?` 吃退出码。
- boot-wait 环缺指纹断言：**待补**（S1-01 回归首 curl 疑 node 回落 200，boot_wait=0；门禁本体不依赖、指纹双断言兜底、判 PASS 不动摇）。

### 自改披露

**RW-S2-QA-01**：08 S2-08 行三参 assert SyntaxError（08 自身命令缺陷，lead 授权自改）→ 拆 4 条双参断言 + printf 落盘 + 字段链适配 `metric="relabel_agreement"` 字符串指针；阈值语义 0.70/n>0 不变；根因=写入时未 sh -n/py_compile。08 其余 46 条零改动。

whitebox 结论：**3 具体问题 + 4 排除项 + runner 缺陷族 2 项（1 修 1 待补），协议 ≥1 达标；人工复核 0 项**。

---

## regression（回归验证：段0 五条 + 段1 五条按名重跑）

### 段0 ×5（证据 qa/evidence/S0/regression_S2.log，带批次名未覆盖 batch0/1 基线）

| 条目 | 判定 | 输出摘录 |
|---|---|---|
| S0-01 | **PASS** | `docs count=9` exit=0；标题字面 9/9 |
| S0-02 | **PASS** | `grep -L` 空清单 exit=0 |
| S0-03 | **PASS** | `indexed=5 checked=[00_PRD,dataset,score] missing=[]` exit=0 |
| S0-04 | **PASS** | `total 47 {'0':5,'1':5,'2':8,'3':5,'4':4,'5':5,'6':6,'7':4,'8':5}`、`badchars=[]`、20 断言全 OK、SELF-CHECK PASS exit=0（46→47 = W-2-03 插 S2-06 后基线） |
| S0-05 | **PASS**（[人工复核]） | 结论行：「段2 修订已对照：CW-S1-01 六档/05_DEPLOY/00_PRD 无新暂定值冲突；08 自改 RW-S2-QA-01 不改阈值语义；PASS」 |

### 段1 ×5（证据 qa/evidence/S1/regression_S1.log 1700B；端口共存判例#4；**指纹断言全过**）

| 条目 | 判定 | 输出摘录 |
|---|---|---|
| S1-01 | **PASS** | `S1-01_ALIVE=0 pid=1959`（20s kill -0 成立；boot_wait=0 见 runner 改进项，门禁本体不依赖 curl） |
| S1-02 | **PASS** | `{"status":"ok","ready":true,"model":"mock-deterministic-v1",…}` + `200`，**指纹断言过** |
| S1-03 | **PASS** | 六键 `SIX-KEYS-OK` + `model:"mock-deterministic-v1"`，**指纹断言过** |
| S1-04 | **PASS** | `...................` → **19 passed**（batch1 14→段2 +5 test_data，无回归） |
| S1-05 | **PASS** | `CI-GATES-OK`；SUM_RC=0 真值 |
| 收尾 | 记录 | 自 kill 后 netstat `0.0.0.0:8000 LISTENING 9236` = node(KnowScape) **原样存活，全程未碰** |

回归结论：**S0 5/5 + S1 5/5 = 10/10 PASS**，段0/段1 基线无漂移。

---

## verdict: **PASS_WITH_RISK**

- 黑盒 **9/9 PASS**（含 S2-06 新条目首跑真判、S2-05 人工 10/10、两条 FAIL→RW/自改→翻绿的完整证据链）；
- 白盒 **3 具体问题 + 4 排除 + runner 缺陷族**（协议 ≥1 达标，人工复核 0 项）；
- 回归 **10/10 PASS**；
- 不判 FAIL 依据：三条问题中 P1 已裁决 RW-S2-03 段3 前置（本批门禁面全绿）、P2 属裁决表 E 段4 范围（段2 最小闭环达标）、P3 为登记项；黑盒/人工/回归三面均过，段2 门禁本身成立。

### 风险项清单（分组 = 主控分诊裁决版）

**【组1 · 段3 前置（阻塞训练段开审）】**
- **S2-P1 可学性解耦 → RW-S2-03 退 DATA**：四维标签参数全部进入渲染管线（构图锚点驱动主体、v/σ 驱动暗角噪声、story 层画关系元素、creativity 驱动形状组合多样性）、种子算法回 02 字面；否则段6 pairwise≥0.68 不可达（≈0.5 上限），训练产出必废。
- **QA 义务（段3 开审前执行）**：增补 **S3-06 可学性断言**（同参数扰动→图像可测变化 或 分维特征-标签相关系数下限；亦可接 02 §5 QC#7/#8），条目加完 S0-04 自检同步。

**【组2 · 段4 前置（标注平台完整功能工单必含）】**
- **S2-P2 四件套**：四维黄金题≥2 道、`w_r·q_r·acc_r·mad` 真实现（中位数锚定不退化均值）、pairs≥12/轮、降权落数值不落 verdict 串——归 DATA，段4 S 条目验收；
- **S2-P3 label_quality 生成并入 labeling 工具链**消除孤儿态（f2 可复跑）；`data/exports/*.jsonl` 汇编按 04 §4.2 段4 范围外交付。

**【组3 · 登记不判 FAIL】**
- 主控代跑 f1/f2/f3（违反自证原则，授权口径记档；段3 QA 复跑 label_quality 核 0.975 可复现）；
- 端口共存判例#4（0.0.0.0 node 与 127.0.0.1 uvicorn 共存；门禁 curl 固打 127.0.0.1+指纹断言）；
- S2-08 命令自改 RW-S2-QA-01（已修，披露在案）；
- runner 缺陷族：SUM_RC 聚合假绿（已修）+ boot-wait 指纹待补（QA 自有改进面）；
- 已知四旧项：lint=1 B008（裁决 I）/ tee 吞码已知#1 / PNG mojibake 判例#3 / color CSS 判例#2。

### 交付物

- 本报告：qa/reports/S2_qa_report.md（p1 4412B / p2 10534B / p3 实测见回执）
- 证据（S2 批）：snapshot.txt 3395B、blackbox_S2{,_r2}.{sh,log}、S2-01..08 各 log/.py、S2-05.md、whitebox_S2.md 6511B、wb2_checks{,2}.{sh,log}、wb2_{assert,identical,artifacts}.py、S3-01.log、S3-01_actual_node.log
- 回归证据：qa/evidence/S0/regression_S2.log、qa/evidence/S1/regression_S1.log 1700B（+ regr_S1_s2.sh）
- 自改：docs/08_ACCEPTANCE.md S2-08 行（RW-S2-QA-01）；被审面：labeling/×3、src/data/×3、tests/test_data.py、data/exports、reports×2、07_PLAN 段2、C-DATA-01（方案 B）

— QA（独立审查方），批号 2，2026-11-10 08:36 +08:00
