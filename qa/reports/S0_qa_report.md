# <qa_report batch="0">

段0（文档契约）QA 终审报告 · Aesthetic Prism · QA 独立审查方 · 2026-11-08
依据：docs/08_ACCEPTANCE.md（唯一执行源，本批终版 46 条 / 24934 B）；证据根：qa/evidence/S0/

---

## blackbox（黑盒验证：只按 08 原文命令跑，不看实现代码）

执行环境钉死：Git sh（`sh -c` / 落盘 `.sh` 法，禁 pwsh 直跑）；工作目录 = aesthetic-prism/。
快照：`ls -la docs/ docs/contracts/ > qa/evidence/S0/docs_snapshot.txt`（exit=0，13 件清单固化于开审前）。

| 条目 | 判定 | 命令（08 原文，sh 包裹） | 输出摘录 | 证据 |
|---|---|---|---|---|
| S0-01 | **PASS** | `n=$(ls docs/*.md 2>/dev/null \| wc -l); echo "docs count=$n"; test "$n" -ge 9` | `docs count=9`，exit=0 | qa/evidence/S0/S0-01.log |
| S0-02 | **PASS**（RW-S0-01 落地后复跑） | `grep -L "## 验收标准" docs/*.md > S0-02.log; test ! -s S0-02.log` | 首跑 FAIL：缺失清单 4 行（00_PRD/01_ARCH/03_TRAINING/06_RISK）→ 退 ARCH×3+MODEL×1；ARCH/MODEL 机械补字面小节后复跑 exit=0，清单空（log 为空文件即 `test ! -s` 成立） | qa/evidence/S0/S0-02.log |
| S0-03 | **PASS**（RW-S0-02 落地后复跑） | `python qa/evidence/S0/S0-03.py`（08 原文单行，tee 吞码缺陷已记录→独立复跑取真值） | 首跑真值 exit=1：`missing=['docs/00_PRD.md']`（缺「错误语义」四字）→ 退 ARCH；ARCH 补「## 错误语义」小节后复跑 `indexed=5 checked=[00_PRD,dataset,score] missing=[]` exit=0 | qa/evidence/S0/S0-03.log |
| S0-04 | **PASS** | `python qa/evidence/S0/S0-04.py`（08 原文自检语义 + 本轮 16 项断言） | `total 46 {'0':5,'1':5,'2':7,'3':5,'4':4,'5':5,'6':6,'7':4,'8':5} manual=5`，16/16 OK，`badchars=[]`，`SELF-CHECK PASS` exit=0 | qa/evidence/S0/S0-04.log |
| S0-05 | **PASS**（[人工复核]） | 逐项对齐 00_PRD + 4 契约（无自动命令，按 08 步骤①②③人工执行） | 15 项一致（端口/五键/四维中文名/错误体/P50 150/P95 500/pairwise 0.68/Pearson 0.70/MAE 5.0/QPS≥5/80% 覆盖率/4 路径/证据目录），2 项无矛盾备注，0 冲突 → **全对齐，无修订工单** | qa/evidence/S0/S0-05.md |

RW 落地说明（主控已核验 + QA 独立复跑双确认）：
- **RW-S0-01**（四份标题去编号插字面小节）：00_PRD 07:12 / 01_ARCH 07:14 / 06_RISK 07:14 / 03_TRAINING 07:07（MODEL 执行），复跑 S0-02 PASS。
- **RW-S0-02**（00_PRD 增「## 错误语义」小节 + 契约索引 4 全路径）：复跑 S0-03 PASS，索引抽 5 份四要素全齐。
- S0-01/04/05 与 RW 无关，原 PASS 结论保留（S0-04 因 08 条目 44→46 重跑复验）。
- 过程缺陷留档：`| tee` 管道吞退出码（已知缺陷 #1），S0-03/S0-04 首跑靠独立 python 复跑取真值，判定不受污染。

黑盒结论：**5/5 PASS**（S0-02/03 各经 1 FAIL→RW→复跑翻正的完整证据链）。

---

## whitebox（白盒审查：读实现文档找契约未覆盖边界；证据 qa/evidence/S0/whitebox.md）

读序（按主控排定）：07_PLAN×46 映射 → C-SERVE-01 并发/超大上传 → C-DATA-01 jsonl 坏行 → 03_TRAINING split 泄漏可测性 → 02/04/05 + C-EXPORT/C-BRANCH → 00/01/06 终读。共 9 件 docs + 4 契约全读。

**已知缺陷 #1（主控已批，修单排段5）**：`python … | tee file` 管道吞退出码——S0-03/S0-04 首跑实证（内容 FAIL / 管道 exit=0）。影响面 = 08 全部带 `| tee` 收尾的 S 条目（约 30 条）。处置：段5 工程化批，Makefile 门禁统一 `set -o pipefail` 或落盘→回读→判 exit 三段式；不阻塞段0。本轮判定以独立 python 复跑真值为准，证据不受污染。

### 15 个具体问题分诊表（W1–W15）

| # | 问题 | 定位 | 分诊（主控裁决） | 落地 |
|---|---|---|---|---|
| W1 | `| tee` 吞退出码（≈30 条 S 条目） | 08 命令缺陷 | **已知缺陷 #1**，段5 修 | SERVE·段5 前置；不在本批 verdict 风险内 |
| W2 | 07_PLAN 5 行「等价简写」非合法 shell（`sh -c "python -c import json;d=…"` 裸 `;` 分裂→假失败）+ T-0-01/02 简写强度低于原文 | 07_PLAN | **已裁决**：ARCH e7' 就地修（落地=ARCH 批次 B，07_PLAN mtime 仍 04:40 在途） | ARCH；batch0 报告时点未落地→见风险项 F1 |
| W3 | C-SERVE `async def post_score` 直跑阻塞 ORT→事件循环停转，`/health` 探针被饿死；并发/in-flight 上限/过载档位未定义 | C-SERVE-01 | 段1 前置修（契约回改须 lead 批准） | ARCH+SERVE；S1-01/S1-02/S8-02 验收 |
| W4 | 10MiB 无 Content-Length 预检（读满才 413=DoS 面）；0B 文件/重复 image 字段/`../` filename 无 E 条目 | C-SERVE-01 | 段1 前置修 | ARCH+SERVE；S4-03 验收 |
| W5 | jsonl 坏行 §2.1「读到才抛」vs §4 E9「跳过 warning」自相矛盾；行号 0/1 基、CRLF/BOM/末行无换行未定义 | C-DATA-01 | 段2 前置（DATA 段2 前 ARCH 补 E 条目） | ARCH+DATA；S2-03/S2-04 验收 |
| W6 | split 泄漏「混入判 FAIL」无黑盒断言，自检=实现方自任裁判（08 无此 S 条目、03 §12 无此命令） | 03_TRAINING×08 | QA 段2 补 S 条目 | QA；新 S 条目验收（段2） |
| W7 | S6-03/S6-06 未断言 `n_test≥20`，n<20 小样本可绕过终验线（03 §7.2/7.4 冲突） | 08 自身命令缺陷 | **就地修（lead CW 已批=QA 改）** | QA **已改**：两行断言+阈值列补 `int(n)>=20`；S0-04 自检 OK n_test_20 |
| W8 | 02_DATA 四条标签公式括号不配对（`round(100·(…,1)` 缺右括号 ×4）→ 照抄 SyntaxError | 02_DATA | 段2 返工 | DATA；S2-01 标签生成验收 |
| W9 | 04 `rater_id`/`round_id` 无白名单拼文件路径→`../` 路径穿越可写 `qa/`（违裁决 C 只读边界） | 04_LABELING·**安全** | 段4 前置（完整功能过 S2 前必须修） | DATA；S2-02/S2-03 验收 |
| W10 | S2-02 cnt `or len(x)` 回退→5 个空 export=entries 10 误判 PASS；与 04 §5.1 声明互斥 | 08 自身命令缺陷 | **就地修（lead CW 已批=QA 改）** | QA **已改**：删回退+阈值列注明「W10：空文件计 0，无回退」；自检 OK no_or_len_fallback |
| W11 | 05_DEPLOY §7.1 判定仍写 `p50≤100 && p95≤300`（CW-S0-02 废线），与 §4/PRD/08 三处矛盾 | 05_DEPLOY | 段1 返工 | SERVE；S6-02 验收 |
| W12 | 导出 `artifacts/model.onnx` vs 服务 `models/hapnet_teacher.onnx` 路径链断，无搬运步骤→段4 必然 500 | 03×05×C-EXPORT | 段4 前置·**已裁决**（归属=ARCH e' 批次；归一路径步骤待 ARCH 落地核验） | ARCH（裁决）+SERVE；S4-01/S4-03 验收 |
| W13 | C-EXPORT §5.2「真实值，非伪代码」72.98 逐字示例不可复现（与「未训练时输出」自相矛盾） | C-EXPORT-01 | **就地修（lead 批=ARCH）** | ARCH **已落地**（mtime 08:22，已改为代表值标注）——已核 |
| W14 | 教师分支宽度 96（01_ARCH L71 / 06_RISK L32）vs 64（C-BRANCH 冻结 D=64）三文档互斥，直击 G5/S6-01 参数预算 | 01_ARCH×06×C-BRANCH | **已裁决**：以冻结契约 64/48 为准，修 01/06 | ARCH e1'-e7' 批次——**已落地核验**（01_ARCH 08:20 `width96_hits=0`、06_RISK 08:24） |
| W15 | 06_RISK 三项缓解产物（label_quality.json / test_license_whitelist.py / holdout）无 08/07 承载；R3 中位数错引 C-DATA-01（应 04_LABELING §3.2） | 06_RISK×08×07 | 验收补条目=**QA q3/q4**；06 文档修订=ARCH e 批次 | QA **已补 S2-07（覆盖率 100%）、S2-08（一致率≥0.70 且 n>0）**；06_RISK mtime 08:24 已落；07_PLAN 引用行=ARCH 批次 B 在途；holdout 项=段2 后 DATA 补（风险登记） |

### 3 项人工复核（RW 收口终读核销：**3/3 通过**）

1. **00_PRD 终读 → 通过**：`## 验收标准` 字面（L126）+ 新增 `## 错误语义` 小节（L123，①②③④四约束齐）+ 契约索引 4 全路径（L40–47）+ 自检 4 条实跑全绿（#1 M 表 9 锚定 0 / #2 ac=9 cmd=13 / #3 阈值串 / #4 残留 0·evid=9）；乱码 0。证据 whitebox_checks.log。
2. **01_ARCH §3 × C-BRANCH §3.1 逐形状 → 通过**：12 形状全对上（stem/trunk/feat·64/fused·256/sub 批量 (N,4) vs dict (N,1) 并存/gate 行和=1/total∈[0,100]/ranking 不进 ONNX）；C-BRANCH 自检 #3（无空格字面 grep -F）exit=0；形状一致但参数区冲突=W14 另记（已修）。
3. **06_RISK 风险×门禁对照 → 结构通过**：R1–R5 各 5/5/5/5（触发信号/事前/事后/责任方），自检 4 条全绿，矩阵 5 行，关键词 0 缺；内容级缺口=W15 另记（部分已修）。

whitebox 结论：**≥1 具体问题达成（15 项）**，无需引用「N 项人工复核」兜底（3 项复核已全过并单列）。

---

## regression（回归验证）

**N/A（首段无上前段）**：段0 是 0%→200% 推进的第一个批次，不存在「上一段已通过的测试」可回归。
回归机制自段1 起启用：届时 regression 节须复跑段0 全部已 PASS 条目（本批 = S0-01..05 共 5 条 + 后续随 RW/CW 增补的条目），逐条列通过/失败。
（防漂移说明：本批 5 条证据均已落盘 qa/evidence/S0/，段1 回归以同名文件重跑覆盖、旧值以 GATE_LOG 时间戳对账。）

---

## verdict: **PASS_WITH_RISK**

黑盒 5/5 PASS（含两条 RW 闭环翻正）；白盒 15 问题全部完成分诊（3 项就地修完：W7/W10=QA、W13=ARCH；2 项终读核销通过）；首段回归 N/A。
不判 FAIL 的依据（lead 裁决 H + 本批实证）：无任何一项问题要求**段0 交付物在本批内返工**——所有遗留项均已归属明确的后续段前置修，且 08_ACCEPTANCE 自身的两个命令缺陷（W7/W10）已就地修完并复验（S0-04 自检 16/16 OK、exit=0）。

### 风险项清单（全部不阻塞段0 收口，逐项标注归属与验收点）

**【段1 前置修清单】**
1. **W3/W4 · C-SERVE 并发与超大上传边界**（async 阻塞饿死 /health、无 in-flight 上限、10MiB 读满才 413、0B/重复字段无 E 条目）→ 归 **ARCH（契约补丁，lead 解冻）+ SERVE（实现 run_in_executor/Content-Length 预检/E 条目表）**；验收：S1-01/S1-02（探针存活）、S4-03（错误五档）、S8-02（并发压测 0 失败）。
2. **W5 · jsonl 坏行语义统一**（§2.1 抛 vs §4 E9 跳，行号/CRLF/BOM 未定义）→ 归 **ARCH（C-DATA 补 E 条目行）**，DATA 按终版实现；验收：S2-03/S2-04。
3. **W11 · 05_DEPLOY §7.1 废线 100/300** → 归 **SERVE**（改 150/500 + 证据路径双轨注明）；验收：S6-02。
4. **W2 · 07_PLAN 5 行非 shell 简写 + T-0-01/02 强度差** → 归 **ARCH e7'**（批次 B 在途，报告时点 07_PLAN 未落地，落地后须 QA 补验映射行）；验收：QA 段1 开审前复读 07_PLAN。

**【段2 前置修清单】**
5. **W6 · split 泄漏黑盒断言缺失** → 归 **QA**（段2 批次新增 S 条目：三 split id 两两交集空 + 同 sha256 不跨 split）；验收：新 S 条目。
6. **W8 · 02_DATA 公式缺右括号 ×4** → 归 **DATA**；验收：S2-01/S2-04（标签可生成、可解码）。

**【段4 前置修清单】**
7. **W9 · rater_id 路径穿越（安全）** → 归 **DATA**（白名单正则 + resolve 越界拒绝；修复前标注平台完整功能不得过 S2→S4 过渡）；验收：S2-02/S2-03。
8. **W12 · artifacts/ ↔ models/ 路径链断** → 归 **ARCH 裁决已出**（归一方式待 ARCH e' 批次落地核验）+ SERVE 实施；验收：S4-01/S4-03。

**【登记在案·不设段门】**
9. **W1 · tee 吞码** → SERVE·段5 修单（已批）；段1 起 QA 各批继续用独立复跑兜底。
10. **W15 余项 · holdout 集无承载** → DATA 段2 后补（R1 事后缓解）；07_PLAN 对 S2-07/08 的引用行 → ARCH 批次 B，落地后 QA 补验 44→46 映射。

### 交付物

- 本报告：qa/reports/S0_qa_report.md（全文）
- 证据：qa/evidence/S0/{docs_snapshot.txt, S0-01.log, S0-02.log, S0-03.log, S0-04.log, S0-04.py, S0-05.md, whitebox.md, whitebox_checks.sh, whitebox_checks.log, whitebox_checks2.sh, whitebox_checks2.log, S0-01.sh, S0-02.sh, S0-03.py, S0-04.sh}
- 被审交付物（13 件）：docs/00–08 九份 + docs/contracts/ 四契约 + 08_ACCEPTANCE 终版（46 条/24934 B，badchars=0）

— QA（独立审查方），批号 0，2026-11-08 09:12 +08:00


