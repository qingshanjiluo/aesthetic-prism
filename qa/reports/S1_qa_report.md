# <qa_report batch="1">

段1（25% 骨架）QA 终审报告 · Aesthetic Prism · QA 独立审查方 · 2026-11-09 08:08 CST
依据：docs/08_ACCEPTANCE.md（唯一执行源，46 条基线）；证据根：qa/evidence/S1/ + qa/evidence/S0/regression_S1.log
执行环境：Git sh（sh -c / 落盘法，禁 pwsh 直跑）；工作目录 = aesthetic-prism/；契约 = C-SERVE-01（CW-S1-01 六档）。

---

## blackbox（黑盒验证：只按 08 原文命令跑，不看实现代码；5/5 PASS）

开审前快照：`ls -la docs/ docs/contracts/ src/ tests/ frontend/ configs/ .github/workflows/ > qa/evidence/S1/snapshot.txt`（exit=0，68 行，17:50 固化）。
跑前探端口：8000 listeners=0（跑完自清，dev.pid/dev.log 留原始证据）。

| 条目 | 判定 | 门禁命令原文（08，sh 包裹） | 输出摘录 | 证据 |
|---|---|---|---|---|
| S1-01 | **PASS** | 落盘法：`(make dev > dev.log 2>&1 & echo $! > dev.pid); sleep 20; kill -0 $(cat dev.pid)` | `S1-01_ALIVE=0 pid=541`（20s 后 kill -0 成立）+ `health_during=200` + dev.log 尾 `Application startup complete` / `200 OK` | qa/evidence/S1/S1-01.log（436B）+ S1-01.sh + dev.pid/dev.log |
| S1-02 | **PASS** | `curl -s -w '\n%{http_code}' http://127.0.0.1:8000/health \| tee S1-02.log; test "$(tail -1 …)" = "200" && grep -q '"status"…"ok"'` | `{"status":"ok","ready":true,"model":"mock-deterministic-v1","device":"cpu","uptime_s":0.4}` + `200`，S1-02_EXIT=0 | qa/evidence/S1/S1-02.log |
| S1-03 | **PASS** | `curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score \| tee S1-03.json; python -c "…ks=('total','composition','light','creativity','story');全 0–100 + 键集恰等 + 'mock' in model"` | `{"total":34.6,"composition":82.6,"light":43.5,"creativity":98.0,"story":35.6,"model":"mock-deterministic-v1"}` → `SIX-KEYS-OK ['composition','creativity','light','model','story','total']`，S1-03_EXIT=0 | qa/evidence/S1/S1-03.json |
| S1-04 | **PASS** | `python -m pytest -q > S1-04.log 2>&1`（08 原文 `pytest -q`，tee 吞码已知#1→落盘取真值） | `.............. [100%]` → **14 passed / 0 failed**，S1-04_EXIT=0 | qa/evidence/S1/S1-04.log |
| S1-05 | **PASS** | `grep -qE "pytest\|make test" .github/workflows/*.yml && grep -qE "ruff\|flake8\|make lint" … && echo CI-GATES-OK` | `CI-GATES-OK` + `jobs=lint,test,`，S1-05_EXIT=0 | qa/evidence/S1/S1-05.log |

**交叉同值确认（主控 GATE_LOG 段1 终证节 + SERVE 自报，独立三方同值）**：pytest=14p、/health=200 六字段、/score=SIX-KEYS-OK、静态 200 text/html、typecheck=0、CI jobs=[lint,test]——QA 独立复跑全部同值命中；QA 侧不采信对方复跑、以本表证据为准。
已知登记（不判 FAIL）：lint=1 B008（裁决 I 挂段5 #noqa）、tee 吞码（已知#1 挂段5 pipefail）、sample.png 二进制 mojibake 误计（判例#3）、index.html color CSS（判例#2）。

blackbox 结论：**5/5 PASS**。

---

## whitebox（白盒审查：读实现找契约未覆盖边界；证据 qa/evidence/S1/whitebox_S1.md + w2_refcheck.log + frontend_check.log）

读面：src/aesthetic_prism/serve/{app.py,service.py}、tests/（5 文件）、frontend/{index.html,app.js}、Makefile、configs/×4、.github/workflows/ci.yml、07_PLAN、08 互核。

### 片1 · W3/W4 落地面 E10–E14（5 PASS + 3 concern）

- **E12 CL 预检行序 = PASS**：app.py L155-158「第2步」在 `await request.body()`(L162) 与 `request.form()`(L165) **之前**，guard 内先查后读；路由级二重检 L100-104；r6b 单测 header 注入 11MiB 真验 413。
- **E10 空文件 = PASS**：service L124-125 `if not data` → 400，位序 413(L122) 后、415(L126) 前；单测真发 0B。
- **E11 重复 image = PASS**：app L168-171 `len(form.getlist("image"))>1` → 400；单测双 part 真发。
- **E13 locked 非阻塞 = PASS（真断言非摆设）**：app L84-86 `if _sem.locked(): raise` 在 `acquire` 前，无排队路径；r6b L32-82 断言 429 **且 elapsed<1.0**——若退化为排队：主线程卡 acquire 而 `release.set()`(L80) 要 r2 返回后才执行 → 死锁挂测 → 14p 不可能成立，故 elapsed<1s 为有效断言链。
- **E14 threadpool 真包 = PASS**：app L89 `await anyio.to_thread.run_sync(service.score_bytes, data, mime)`；Semaphore 进池前取（L86<L89），事件循环不被 session.run 占 → /health 恒可探。
- **六档映射 = PASS**：400（service L46-49 + guard L166/171）/404（app L129-136，404 与 405→404 not_found）/413（L36-38+L157）/415（L43-45+L153）/429（L51-55，MAX_INFLIGHT=4 L15）/500（L58-65+app L110-114/L139-144）；契约 §3.5 六档表 + **CW-S1-01 修订留痕在位（契约 L8）**。

### 片2 · W2 语法级 + S2-07/08 互核 + 段1 新地盘机械面

- **W2 语法级 = 40/43 FAIL 3**（`sh -n -c <inner>` 逐行，只验语法不执行）：**T-2-01(L9)/T-2-05(L13)/T-6-01(L27)** 仍为裸 `python -c "…(` → `syntax error near unexpected token '('`；FOCUS 行 T-2-03/T-6-02/T-0-01/T-0-02 = OK → **e7' 只修净 2/5，自报"残留=0"被 sh -n 实测打脸**（见问题 S1-P4）。
- **S2-07/08 互核 = 一致**：07 L57→(S2-07)、L59→(S2-08) ↔ 08 L52/L53；证据路径集合 diff = **PATHS-IDENTICAL**；映射 46/46 全覆盖（in_acc 空），plan 独有 6 个 `S*-00` = 附加 manifest 合规（batch0 结论互证）。
- **configs yaml = 4/4 `yaml.safe_load` 可解析**；**make 七目标 `make -n` = 全 0**（dev/test/lint/typecheck/coverage/demo/reproduce，均无 bash-only 语法违例）。
- **前端轮询字面 = CONCERN（判例级，不判 FAIL）**：app.js L117 `setInterval(pollHealth, 3000)` = 3000ms vs 05_DEPLOY L115「每 5 s 轮询」——实现快于文档；S1-02 验收未锁周期。改文档迁就实现 vs 反之，由 lead 段4 前裁决（预告裁决单号），本批记档不判 FAIL。

### 片3 · 前端三点

- **锚点齐全 = 8/8 PASS**：score-form L49 / bar-composition L60 / bar-light L61 / bar-creativity L62 / bar-story L63 / error-box L65 / health-dot L43 / model-badge L58；app.js 引用侧（含模板 `fill-/value-/bar-${k}` L72-74,85-86 × DIMS 四键 L6）无悬空引用。
- **四键旧键 = 0 真命中 PASS**：模式 `colou?r|ligh[t]ing|detai[l]`；app.js **0 命中**；index.html 9 命中全在 style 块（L7–L37）CSS `color:`/`border-color` 属性字面（L10/13/18/19/22/25/26/33/34）→ 判例#2 豁免；style 外 0 命中；`ligh[t]ing|detai[l]` 两文件合计 0。
- **错误体/健康灯 = 2 PASS + 1 concern**：错误体 L49-56（类型守卫 code/message str + L54 `http_${resp.status}` 兜底 + L60 本地 network_error 不违契约 §3.5）；健康灯 L92-117（L116 即刻 + 三色 L100/103/106 + L111-112 失败红 + L109 meta `model·device·uptime_s` 对齐 05_DEPLOY §3.5）；concern = 轮询 3000ms 字面（见片2）。

### 4 个具体问题（协议 ≥1 达标；各归其主 + 验收 S 条目）

| # | 问题 | 依据 | 归属 | 验收点 |
|---|---|---|---|---|
| **S1-P1** | SCORE_TIMEOUT_MS 未接线，E7 超时档空转 | service L14 定义 5000ms，src 全树无消费点（fail_after/wait_for/move_on_after/signal 均无）；app L110-111 `except TimeoutError` 分支永不可达——契约 §2「推理超时→500」与 §4 E7 无执行体；段4 ONNX 后 session.run 无 5s 上限，卡死占满 4 许可 → 全 429 | **SERVE** | S4-03（500 档）+ S6-02（P95 兜底） |
| **S1-P2** | 无 Content-Length（chunked）超大体违契约 E12 后半句 | app L162 `body()` 整读入内存；无「边读边累计、达 10,485,761 立即中断」实现；超限仅 service L122 读满兜底 | **SERVE** | S4-03 |
| **S1-P3** | 429 判定晚于 body 读取（次级） | app L81 `image.read()` 先于 L84 `locked()`——满载洪峰每请求仍读满 ≤10MiB 才 429，内存面放大；E13「满→立即」语义限于推理不排队 | **SERVE**（段5 批） | 段5 工程化批 |
| **S1-P4** | 07_PLAN 三行验收命令 sh -n 语法错（e7' 残留） | T-2-01/T-2-05/T-6-01 裸 `python -c "…(` → sh 解析 `(` 即 syntax error，运行必假失败；e7' 自报修净 5/5 实测 2/5 | **ARCH** | 段2 开审前复跑 `w2_refcheck.sh` **43/43** 放行 |

whitebox 结论：**4 具体问题 S1-P1..P4 各归 SERVE/ARCH + 验收点明确，协议 ≥1 达标**（判例级 concern：轮询 3000ms 字面随段4 裁决）。

---

## regression（回归验证：段0 五条按名重跑，证据 qa/evidence/S0/regression_S1.log = 1775B）

段1 期间 05_DEPLOY/00_PRD/07_PLAN 经授权修订（W11/CW-S1-01/e7'），S0-01..04 实跑复验、S0-05 人工对照标注；**S0 5/5 PASS**：

| 条目 | 判定 | 重跑输出摘录 | 备注 |
|---|---|---|---|
| S0-01（a2） | **PASS** | `docs count=9` exit=0；标题字面 `grep -L` lines=0 exit=0 | 9/9 含段1 授权改动三文件（05_DEPLOY/00_PRD/07_PLAN）撞题验证通过；**a2 引号穿透自抓留痕**：首跑 pwsh→sh `##` 被当注释 → grep usage err → missing=0 假绿，改 batch0 落盘法 sh 脚本+内层单引号重跑更正，log 已记「rewritten after pwsh quote-mangling false-green」 |
| S0-02（a3） | **PASS** | `grep -L '## 验收标准'` 空清单 lines=0 exit=0 | 按名重跑，四份 RW 后字面仍齐 |
| S0-03（a3） | **PASS** | `indexed=5 checked=[00_PRD,dataset,score] missing=[]` exit=0 | S0-03.py 原脚本，零引号穿透 |
| S0-04（a4） | **PASS** | `total 46 {'0':5,'1':5,'2':7,'3':5,'4':4,'5':5,'6':6,'7':4,'8':5} manual=5`、`badchars=[]`、16 断言全 OK、`SELF-CHECK PASS` exit=0 | 46 条基线未被段1 波及（08 归 QA 未动） |
| S0-05（a4b） | **PASS**（[人工复核]） | 结论行已写入 log：「段1 修订已对照：05_DEPLOY W11/CW-S1-01、00_PRD、07_PLAN 授权改动逐项对照，无新暂定值冲突；PASS」 | 暂定值清单 + n_test≥20 无新增冲突 |

回归结论：**S0 5/5 PASS**，段0 基线无漂移，放行段2（附条件，见风险项组1）。

---

## verdict: **PASS_WITH_RISK**

- 黑盒 **5/5 PASS**（S1-01..05 独立跑，三方交叉同值）；
- 白盒 **4 个具体问题 S1-P1..P4**（协议 ≥1 达标）+ 1 判例级 concern（轮询字面）；
- 回归 **S0 5/5 PASS**；
- 不判 FAIL 依据：4 问题均属契约/文档残留级、黑盒门禁与契约主路径（E10–E14 六档行序）全部成立，逐项已有归属与验收 S 条目，段内无须返工件。

### 风险项清单（四组，各归其主 + 验收点）

**【组1 · 段2 前置（阻塞段2 放行）】**
- **S1-P4 · 07_PLAN 三行 sh -n 语法错**（T-2-01/T-2-05/T-6-01 裸 `python -c "…(`，e7' 只修净 2/5）→ 归 **ARCH**；验收：段2 开审前 QA 复跑 `qa/evidence/S1/w2_refcheck.sh` 必须 **43/43** 全过才放行三行对应门禁。

**【组2 · 段4 前置（接真实 ONNX 时并 W 系清单派修单）】**
- **S1-P1 · SCORE_TIMEOUT_MS 未接线、E7 超时档空转**（src 无消费点、TimeoutError 分支永不可达）→ 归 **SERVE**；验收：**S4-03**（500 档可触发）+ S6-02。
- **S1-P2 · chunked 无 Content-Length 违契约 E12 后半句**（整读才 413）→ 归 **SERVE**；验收：**S4-03**。

**【组3 · 段5（工程化批一并修）】**
- **S1-P3 · 429 判定晚于 image.read**（洪峰内存面）→ 归 **SERVE**；
- **W1 · `| tee` 吞退出码**（已知#1，`set -o pipefail` 或落盘→回读→判 exit 三段式）→ 归 **SERVE**；
- **前端轮询字面裁决**（app.js 3000ms vs 05_DEPLOY「每 5 s」）→ 归 **lead**（裁决单号 lead 段4 前发）。

**【组4 · 已知登记项（判例/裁决在案，本批不判 FAIL）】**
- lint=1 B008（裁决 I 挂段5 #noqa 处置）；
- tee 吞码（已知#1，同组3 W1）；
- sample.png 二进制 mojibake 误计（判例#3）；
- index.html color CSS（判例#2）+ 前端轮询 3000ms（判例级）。

### 交付物

- 本报告：qa/reports/S1_qa_report.md（3 段 write 拼合；p1=2945B、p2 累计 8376B、p3 实测见回执）
- 证据：qa/evidence/S1/（snapshot.txt、S1-01.log/S1-01.sh、S1-02.log、S1-03.json、S1-04.log、S1-05.log、S1-0203.sh/.log、S1-0405.sh/.log、whitebox_S1.md、whitebox_S1_checks.sh/.log、w2_refcheck.sh/.log、W2_syntax.log、make_*.err、paths/ids 文件）+ qa/evidence/S0/regression_S1.log（1775B）
- 被审面：src/serve 2 文件 + tests 5 文件 + frontend 2 文件 + Makefile + configs×4 + ci.yml + 07_PLAN/08 引用 + C-SERVE-01/C-DATA-01（CW-S1-01 扩档）

— QA（独立审查方），批号 1，2026-11-09 08:22 +08:00
