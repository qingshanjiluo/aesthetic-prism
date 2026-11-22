# 段0 白盒审查记录（QA 独立审查方，2026-11-08 07:13 CST）

读序：07_PLAN×44 映射 → C-SERVE-01 并发/超大边界 → C-DATA-01 jsonl 坏行 → 03_TRAINING split 泄漏可测性 → 02/04/05 + C-EXPORT/C-BRANCH 兜底。
已读：07_PLAN、四契约、02_DATA、03_TRAINING、04_LABELING、05_DEPLOY（8 件）。
未读（挂起）：00_PRD / 01_ARCH / 06_RISK —— 等主控「RW 收口 done」回执后终读，对应 3 项人工复核（见末节）。

## 0. 已知缺陷（主控已批，列第 1 个具体问题）

**W1 · `python … | tee file` 管道吞退出码**（本轮黑盒实证）：S0-03/S0-04 原文命令经 `| tee` 后 `$?` 恒 0——S0-03 内容实判 FAIL 而管道退出码为 0，QA 靠独立 python 复跑（exit=1）才取得真值。S-条目凡以 `| tee` 收尾者退出码判定全部失效。
影响面：S0-03、S0-04、S1-02/03/04、S2-01~04、S3-01~05、S4-01~03、S5-02~05、S6-01~03、S6-06、S8-02/03/04 等全部带 tee 的条目。
修复归属：**段5 工程化批**（裁决 H 已批修单），Makefile 门禁统一 `set -o pipefail` 或「落盘→回读→判 exit」三段式；不阻塞段0。

## 1. 07_PLAN（CW-S0-04 重写版）验收列 × 44 S 映射

映射核对结论（lead 预检问题的答复）：
- 44 条 S-条目被任务行**逐条覆盖 44/44**（段0:5/段1:5/段2:5+引S3-01/段3:4/段4:4/段5:5/段6:6/段7:4/段8:5）；
- 9 条 `manifest 附加` 行（T-1-01、T-1-03、T-2-04、T-4-04、T-5-02、T-6-02、T-7-02、T-8-03、T-8-04）**均为附加，无一替代 S 条目**，证据名 S\*-00.\* 不占用 08 定义的证据文件名——符合 §0 规则。

**W2 · 「等价简写」多行不是合法 shell，且强度与 S 原文不等价**（07_PLAN 具体问题）：
- T-2-01 / T-2-03 / T-2-05 / T-6-01 / T-6-02 五行命令形如 `sh -c "python -c import json;d=json.load(...)"`：`-c` 体未加引号且裸 `;` 在 sh 层即为语句分隔——实跑 `python -c import` → SyntaxError，后半 `d=json.load(...)` 被当独立命令 → 两段皆非 0。数据齐全也会 FAIL（假失败），5 行。
- T-0-01 标注（S0-01/S0-02/S0-03）但命令只 `test -f` 5 个文件：不计数 ≥9、不 grep 验收小节、不校验四要素——强度远低于原文；T-0-02 标注（S0-04/S0-05）但 `grep -c 条目ID` 数的是 9 个表头 ≠44，且 S0-05 是人工复核项，无命令可替代。
- T-4-01 标注（S4-01）但跑 CLI `scripts/score.py`，S4-01 断言的是 HTTP `/score` schema 六字段——判定面不同。
修复归属：ARCH（07_PLAN 简写列改成「引 08 原文执行」或至少合法可跑的等价断言；`sh -c` 列内不得出现未引号 `;`/python -c 体）。

## 2. C-SERVE-01（并发 / 超大文件边界）

**W3 · 并发路径未定义，`async def post_score` 默认实现会堵死事件循环**：
- §2 签名 `async def post_score(...)`；`score_bytes` → `session.run` 为阻塞调用（`SCORE_TIMEOUT_MS=5000`）。契约未规定 `run_in_executor`/线程池/并发上限/排队超时——若直写阻塞体，单请求最长挂 5s 期间**事件循环停转，`GET /health` 探针同被饿死**（与 §1「/health 恒 200 可探」目标冲突），S8-02 压测 `-u 8` 并发下必现。
- 无 worker 数、无 in-flight 上限、无 429/503 档位（§3.5 五档无过载档）。
**W4 · 超大文件只在读满后才 413，且空文件/重复字段无 E 条目**：
- `score_bytes(data: bytes, ...)` 契约签名意味着**body 先整体读入内存再判 10,485,760**——无 Content-Length 预检、无流式早断，攻击者可先灌内存再吃 413（DoS 面）；契约未写「何时判 413」（读前/读后）。
- E1–E9 缺口：0 字节文件（魔数空 → 落 415 还是 400？）、重复 `image` 字段（取第一个还是 400？）、filename 含 `../`/超长、`Content-Length` 与实际 body 不符。均未定义 → 同一实现两套测试会各判各的。
修复归属：ARCH（契约补丁，C-SERVE 冻结件须 lead 解冻）。

## 3. C-DATA-01（jsonl 坏行语义）

**W5 · 同一函数两种行为，§2.1 与 §4 E9 自相矛盾**：
- §2.1 表：`iter_dataset_jsonl` 抛出列 =「DatasetValidationError（**惰性，读到坏行才抛**）」；
- §4 E9：「JSONL 场景**跳过该行并 warning**；单文件场景上抛」；02_DATA §3 已按「丢弃+warning+计数」实现。
→ 坏行到底抛还是跳？抛则批读取方必须 catch（与通用规则「不得吞异常」张力），跳则「门禁出现未捕获 DatasetValidationError 即 FAIL」在 jsonl 路径永不触发、且**跳过计数由谁累计、丢弃清单写哪**未定义。行号 0/1 基、多行 pretty-printed JSON（非逐行）、行尾 CRLF/UTF-8 BOM、末行无换行——均未定义。
修复归属：ARCH（契约补丁，须 lead 解冻）。
次要：`image_path` 的 schema 正则 `^[^\\]*\.(jpg|jpeg|png)$` 允许绝对 POSIX 路径（`/etc/x.jpg` 通过），与字段表「相对项目根」语义不一致——可注入相对路径约束。

## 4. 03_TRAINING（split 泄漏断言可测性）

**W6 · 「val/test 混入训练集判 FAIL」无任何黑盒断言，裁判=实现方自己**：
- §1.1 规定混入即 FAIL，但实现该判定的是 T2（训练进程启动期自检 SystemExit）——**由被检验方实现检验逻辑**；
- 08 44 条无一条断言 `train ∩ val ∩ test = ∅`；03 §12 验收标准 7 条命令也无一检查 split 互斥（#5 只 grep 字面 `--steps 20`/`10,000,000`/`atol=0`）；
- 泄漏恰发生在自检被绕过（如 resume 路径、`--init-from` 跨阶段初始化、配对采样器另行读入）时，正是自检最不可信的场景。
建议：08 增补一条 S 条目（QA 侧独立断言，遍历三 split 的 id 集合两两交集为空 + 同 sha256 不跨 split），或 03 §12 增可执行检查——**需 lead CW 后我改 08**。
**W7 · S6-03/S6-06 未校验 `n_test`，小样本可绕过终验线**（08 自身缺陷）：
- 03 §7.2 规定「n<20 相关系数不可信——判 FAIL、不出报告（S6-03 视为未达成）」、§7.4 要求 20≤n<50 必须在 metrics.json 记 `n_test`；
- 但 08 S6-03 命令只 `assert pa>=0.68 and pe>=0.70`，S6-06 只查 MAE——**n_test=10 的报告照样全绿**。
修复归属：QA（我）改 08 S6-03/S6-06 加 `n_test>=20` 断言——**等 lead CW 批准后执行**（08 为唯一执行源，回改须批）。

## 5. 02_DATA

**W8 · 四条标签公式括号不配对，按字面实现直接 SyntaxError**（02_DATA §2，55–58 行）：
```
composition = round(100·(0.55·d₃ + … + 0.20·(1−|g−0.35|/0.35), 1)   ← 100·( 未闭合
light / creativity / story 三行同构同错（每行均缺 1 个右括号）
```
四行全部 `round(` 内 `100·(` 开而未合，`, 1)` 直接关了 round——生成器若照抄四行全崩。（total 行无此错。）
修复归属：DATA（02_DATA 返工，4 处补 `)`）。
其他核对：参数域内各项非负性逐一验算通过（c∈[0.6,1.6]、g∈[0.1,0.7] 边界恰好归 0，无负分）；split 防泄漏 4 条规则自洽。

## 6. 04_LABELING

**W9 · `rater_id`/`round_id` 无校验即拼文件路径，存在路径穿越**（04 §1.2 / §4.1）：
- `data/annotations/sessions/{rater_id}/{round_id}.jsonl`，`rater_id` 来自 index.html 自由文本输入——`rater_id="../../.."` 可写到 `qa/`（QA 所有、裁决 C 只读边界）或任意位置覆盖文件；契约与本文均未定义 rater_id 白名单/正则。
- 黄金题同理：`gold.jsonl` 内 `gold_answer` 防前端下发靠「服务端保管」一句话，无防伪（标注者可猜合成标签——黄金答案=合成 total 较大侧，可暴力对答案，§2 acc≥80% 判据被博弈面未评估）。
修复归属：DATA（rater_id/round_id 正则白名单 + 路径 resolve 越界拒绝）。
计数口径顺带核验：S2-02「累计条目≥10」与 §5.1「Σ len(samples)」一致声明成立——**但与 08 S2-02 实际 cnt 函数有偏差，见 W7 附注（W10）**。

**W10 · 08 S2-02 的 cnt 回退分支可被空导出文件刷过门禁**（08 自身缺陷，与 04 §5.1 声明冲突）：
- 08 S2-02：`cnt=lambda x: len(x) if isinstance(x,list) else (sum(len(v) for v in x.values() if isinstance(v,list)) or len(x))`——export 文件 `{meta, samples:[]}` 中 `samples` 长 0 → `sum(...)=0` 为假 → 回退 `len(x)=2`（顶层键数）；
- 于是**5 个 samples 为空的 export 文件 → entries=10、files=5 → S2-02 误判 PASS**（零标注通过「完成 10 次标注」）；
- 04_LABELING §5.1 声称「与 08 cnt 函数语义一致（list 取 len，对 dict 值中的 list 求和）」——**声明里根本没有 `or len(x)` 回退**，两文档字面互斥。
修复归属：QA（我）删 08 的 `or len(x)` 回退，cnt 恒按「dict 值中 list 求和、list 取 len」——**等 lead CW 批准后执行**；04 §5.1 随之自洽。

## 7. 05_DEPLOY

**W11 · §7.1 延迟判定值是被 CW-S0-02 废止的旧数，文档内三处自相矛盾**：
- §7.1：「判定 `p50_ms≤100 && p95_ms≤300`」；
- 同文 §4：「P50≤150、P95≤500」；00_PRD G4：150/500；08 S6-02：150/500。
→ SERVE 按 §7.1 自验收会用错线（也可能反向：达标判 FAIL）。另 bench 落盘路径 §7.1/`make bench` 写 `reports/latency.json`，08 S6-02 证据列写 `qa/evidence/S6/latency.json`（QA 自跑可另存，非硬冲突，但 §7.3「S6-02 判定路径=§7.1」一节应注明 QA 执行时的 --out 以 08 为准）。
修复归属：SERVE（05_DEPLOY §7.1 改 150/500 + 注明证据路径双轨关系）。

## 8. 跨文档（03 / 05 / C-EXPORT / 08）——路径链

**W12 · 模型工件路径三处不一致，段4 联调必然断链**：
- 03 §10 导出命令 → `artifacts/model.onnx`；08 S4-02 / 00_PRD AC5 校验 `artifacts/model.onnx`；
- 05 §1.1 服务加载 → `models/hapnet_teacher.onnx`（AP_MODEL_PATH 默认值）；C-EXPORT-01 §1 通篇 `models/hapnet_teacher.onnx` / `models/hapnet_student_int8.onnx`；
- **无任何文档定义 artifacts/ → models/ 的搬运/链接/双路径别名步骤** → 段4 时 ONNX 已导出而服务 ModelNotReady（E6 500），S4-01/S4-03 黑盒全挂，且 5 档错误码里找不到「路径配置错」档位（归 internal_error 掩盖配置错误）。
修复归属：ARCH（定一条：导出双写 or 服务默认指 artifacts/ or 增 make 步骤；同步 03/05/C-EXPORT/08 四处）。

## 9. C-EXPORT-01 / C-BRANCH-01（读过部分）

**W13 · C-EXPORT §5.2「真实值，非伪代码」示例输出不可复现**：声称加载未训练/训练后模型将得 `total 72.98 / composition 78.4 …` 逐字输出——该组值要求门控**恰为** (0.3,0.3,0.2,0.2) 且四分支 logits 恰为给定逆解，任何真实模型（尤其 §5.2 标题自称「模型未训练时」）不可能逐字复现；同段先说「未训练时输出为示例量级」后贴精确值，自相矛盾。契约 §5 定位为「最小示例（真实值）」的可核验锚点，此处失效。
修复归属：ARCH（标注为「训练收敛后期代表值（构造目标）」或给出可复现的确定性构造脚本）。
C-BRANCH §3 与 01_ARCH §3 逐形状一致性：**待 01_ARCH RW 收口后终读比对**（人工复核项 3）。

## 9.5 终读核销（RW 收口 done 后，mtime 00/01/06 = 07:12/07:14/07:14）

**人工复核 1 · 00_PRD 终读 → 通过**：「## 验收标准」字面小节在位（L126）；新增「## 错误语义」小节在位（L123，①错误体 ②五档归 C-SERVE ③内部异常归一 500 不外泄 ④/health 恒 200 四条约束齐）；契约索引 4 全路径在位（L40–47，S0-03 正则可抽）；自检 4 条实跑全绿（#1 M 表 9 锚定 exit=0；#2 ac=9 cmd=13 exit=0；#3 六字段/150/500/0.70/补件 exit=0；#4 残留 0、evid=9 exit=0）；乱码 0。证据 qa/evidence/S0/whitebox_checks.log。

**人工复核 2 · 01_ARCH §3 × C-BRANCH §3.1 逐形状比对 → 通过**：stem (N,32,56,56)/trunk (N,128,14,14)/feat 教师 (N,64)/fused (N,256)/z·sub (N,4) 批量视图（C-BRANCH §3.2 注释 (N,1) dict vs (N,4) 批量并存不矛盾）/gate (N,4) 行和=1/total (N,1)∈[0,100]/ranking (N,1) 不进 ONNX —— 12 形状全对上；C-BRANCH 自检 #3（两文件无空格字面 grep -F + fallback）实跑 exit=0。证据同上 log。
→ 终读**新发现 W14**（见下）：形状一致但参数预算区冲突，不属本复核项范围，另记。

**人工复核 3 · 06_RISK 风险×S/AC 对照 → 结构通过，挂 2 个内容级新发现**：R1–R5 五条齐备，触发信号/缓解·事前/缓解·事后/责任方 各 5/5/5/5，自检 4 条实跑全绿（SC1/SC3/SC4 PASS、关键词 0 缺），乱码 0；矩阵 5 行。→ **新发现 W15**：缓解产物 3 项无门禁承载 + R3 归属错误（见下）。

## 9.6 终读新发现（W14/W15，追加进问题清单 → 总 15 项）

**W14 · 教师分支宽度 96 vs 64，三文档互斥**（01_ARCH §4 vs C-BRANCH §3.1 vs 06_RISK）：
- 01_ARCH L71：教师「四分支全宽（分支宽度 **96**）」、L74「gate (256→4)」（256=4×64，按 D=64 才自洽）；
- C-BRANCH L101：`D=**64** 教师 / 48 学生`（L90：学生/教师分支维度 64/48）；
- 06_RISK L32：R2 缓解引「分支宽度预算上限 96（01_ARCH §4）」——把 96 当预算写进风险门禁。
→ MODEL 段3 按哪个实现？96 与 64 参数量差 ~50%，直击 G5 教师 ≤25M 与 S6-01 学生 <10M 预算；且 01_ARCH 自带内部矛盾（96 与 gate 256→4 不符）。**契约冻结件 C-BRANCH 为准（D=64）**，按 C-BRANCH 头部「不一致以本契约为准并回报 lead 修订 01_ARCH」——退 ARCH 修订 01_ARCH L71 + 06_RISK L32（96→64 上限口径）。
**W15 · 06_RISK 三项缓解产物无门禁承载 + R3 归属错引**：
- `reports/label_quality.json`（R3③ 双盲复标）、`tests/test_license_whitelist.py`（R5③ SOURCES 覆盖率）、真实 holdout 集（R1② 事后）——grep 实测 08=0、07=0、02/03/C-DATA=0：**三件缓解产物无任何 S 条目、无 07_PLAN 任务行**，R1/R3/R5 的"段2 门禁"承诺落空（data_bias.json/SOURCES.csv 有 T-2-04 承载，恰反证缺的是另三件）。
- R3② 称「C-DATA-01 labels 语义：total 等字段=**中位数**」——C-DATA-01 §3.2 无中位数语义（仅 0..100+R1/R2）；中位数锚定+加权修正在 **04_LABELING §3.2**，且公式非纯中位数（median + Σw·偏差/Σw）。引用对象错。
- 证据 qa/evidence/S0/whitebox_checks2.log（段 B/D）。

## 10. 挂起的人工复核项（已核销）

原 3 项（00_PRD 终读 / 01_ARCH×C-BRANCH 形状比对 / 06_RISK 对照）已于 §9.5 核销完毕：**3/3 通过**（附 2 个终读新发现 W14/W15 入白盒清单）。

## 汇总

- 具体问题：**15 项**（W1–W15；其中 08 自身缺陷 W7/W10、契约断链 W12、终读新发现 W14/W15）。
- 人工复核：3 项已全部核销（3 通过）。
- 需 lead CW 才能动的自改项：W7、W10（08_ACCEPTANCE 回改须批）。
