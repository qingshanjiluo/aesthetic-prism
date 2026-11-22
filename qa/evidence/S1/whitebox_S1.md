# 段1 白盒审查记录 whitebox_S1.md（QA 独立审查方 · 2026-11-09 06:45 CST）

范围：src/aesthetic_prism/serve/{app.py,service.py}、tests/、frontend/、Makefile、configs/、.github/workflows/ci.yml、07_PLAN、08 引用互核；契约=C-SERVE-01（CW-S1-01 六档）。

## 片1 · W3/W4 落地面：E10–E14 逐项审计

| 项 | 判定 | 依据（行号） |
|---|---|---|
| E12 CL 预检行序 | PASS（主路径） | app.py L155-158 第2步在 body(L162)/form(L165) **之前**，guard 内先查后读；路由级二重检 L100-104；r6b 单测 L20-29 注入 11MiB 真验 413。 |
| E12 无 CL 分支 | CONCERN→**S1-P2** | 契约后半句「无 Content-Length 边读边累计、达 10,485,761 立即中断」实现缺失：chunked 经 L162 body() 整读，src 全树无 fail_after/wait_for/move_on_after；超限仅 score_bytes L122 读满兜底，违契约字面。 |
| E10 空文件→400 | PASS | service L124-125 `if not data` 在 413(L122)后、415(L126)前→0B 走 400；单测 test_error_4xx L19-24 真发 0B。 |
| E11 重复 image→400 | PASS | app L168-171 `len(form.getlist("image"))>1→400`；单测 L26-37 双 part 真发。 |
| E13 locked 非阻塞 | PASS（**真断言**） | app L84-86 locked 在 acquire 前，无排队路径；r6b L32-82：_sem(1) 满时断言 429 **elapsed<1.0**——若排队则主线程卡 acquire 而 release.set(L80) 要 r2 返回后才执行→死锁挂测→14p 不可能成立，非摆设。次级：429 判定在 image.read(L81) 后→S1-P3。 |
| E14 threadpool | PASS | app L89 `await anyio.to_thread.run_sync(service.score_bytes,...)` 真包；sem 进池前取（L86<L89）合契约；事件循环不被 session.run 占→/health 可探。 |
| 六档映射 | PASS | 400=service L46-49+app L123-126/L166-171；404=app L129-136（405→404 not_found 合契约「未知方法」）；413=service L36-38+guard L157；415=service L43-45+guard L153；429=service L51-55；500=service L58-65+app L110-114/L139-144；契约 §3.5 六档+CW-S1-01 留痕 L8。 |

### 片1 具体问题（3）
- **S1-P1 · SCORE_TIMEOUT_MS 未接线，E7 超时档空转**：service L14 定义 5000ms，全 src 无消费点；app L110-111 `except TimeoutError` 永不可达（无抛出点）。契约 §2「单次推理超时→500」与 §4 E7 无执行体——段4 ONNX 后 session.run 无 5s 上限，卡死占满 4 许可→全 429。归 SERVE，验收 S4-03。
- **S1-P2 · chunked 无 CL 超大体违 E12**：整读后才 413。归 SERVE，验收 S4-03。
- **S1-P3 · 429 晚于 body 读取**（次级）：L81 read 先于 L84 locked，满载洪峰仍读满 body。归 SERVE（段5）。

## 片2 · W2 语法级补验 + S2-07/08 引用互核（2026-11-09 07:20）

脚本/证据：qa/evidence/S1/w2_refcheck.sh → w2_refcheck.log、W2_syntax.log（只验语法不执行，`sh -n -c <inner>` 逐行）。

### ① 07_PLAN 43 任务行 sh -c 语法级结果表

**语法 OK = 40/43，FAIL = 3**（照实记录，不静默跳过）：

| 行 | 任务ID | sh -n 结果 | 首个报错（截断） | 命令片段 |
|---|---|---|---|---|
| 9 | T-2-01 | **FAIL** | `sh: -c: line 1: syntax error near unexpected token '('` | `python -c \"import json;d=json.load(open('data/synthetic/index.json'))...` |
| 13 | T-2-05 | **FAIL** | 同上 `syntax error near unexpected token '('` | `python -c \"import json,glob,jsonschema as js;sch=json.load(open('data/...` |
| 27 | T-6-01 | **FAIL** | 同上 | `python -c \"import onnx,math;m=onnx.load('artifacts/student.onnx');n=s...` |

重点行复验（e7' 五改行 + T-0-01/02）：
- FOCUS T-2-01 = **FAIL** / T-2-03 = OK / T-2-05 = **FAIL** / T-6-01 = **FAIL** / T-6-02 = OK / T-0-01 = OK / T-0-02 = OK。

**定性（具体问题 S1-P4，归 ARCH，07_PLAN 批次 B 残留）**：e7' 修复只落了 5 行中的 2 行（T-2-03/T-6-02 转合法），**T-2-01、T-2-05、T-6-01 三行仍是裸 `python -c "…(` 形态**——sh 层解析 `(` 即语法错，运行必假失败（与 batch0 W2 同根，e7' 未修净）。3 行形态一致、修法一致：python 源整体单引号包或转义引号，与 08 原文等价。
- 归属：ARCH（07_PLAN）；验收：段2 开审前 QA 复跑本片脚本 43/43 OK 才放行 T-2-01/T-2-05/T-6-01 对应门禁。
- 注：此为**文档内验收列**缺陷，不改 08（08=唯一执行源，07 简写列仅等价摘要），不判段1 FAIL（e7' 部分落地残留，随 verdict 风险项带出）。

### ② S2-07/08 引用互核

- 07_PLAN L57 `T-2-04 → （S2-07）`、L59 `T-2-06 → （S2-08）`；矩阵行 L24 / 段头 L50 均含 `S2-07/S2-08（W15 承载）`。
- 08_ACCEPTANCE L52 `| S2-07 |`、L53 `| S2-08 |` 条目在位。
- 证据路径集合 diff（plan vs acc 各自 grep `qa/evidence/S2/S2-0[78]...` sort -u 后 diff）→ **PATHS-IDENTICAL**（编号与证据路径逐字一致）。

### ③ 43 行引用 vs 08 实有 46 条映射缺口复验

- plan_unique = 52、acc_total = 46；
- `in_acc_not_in_plan:` **空**（08 全部 46 条均被 07_PLAN 引用，无缺口）；
- `in_plan_not_in_acc:` = `S1-00 S4-00 S5-00 S6-00 S7-00 S8-00` 六个 **S\*-00 manifest 附加行**（batch0 已核：附加非替代，证据名 S\*-00.\* 不占 08 证据列）——复验通过，与 batch0 结论一致。

片2 结论：**语法 40/43（3 FAIL = S1-P4 归 ARCH）；互核一致 = 是（PATHS-IDENTICAL + 46/46 覆盖 + 6 个 -00 合规）**。

## 片3 · 前端三点（2026-11-09 07:47；白名单读 frontend/index.html + frontend/app.js）

### ① 锚点齐全性 = **8/8 PASS**（index.html 实测行号）

| 锚点 | 行 | 结果 |
|---|---|---|
| `score-form` | L49 | OK |
| `bar-composition` | L60 | OK（同块 fill-/value- 锚点 L60 亦在） |
| `bar-light` | L61 | OK（fill-/value- L61） |
| `bar-creativity` | L62 | OK（fill-/value- L62） |
| `bar-story` | L63 | OK（fill-/value- L63） |
| `error-box` | L65 | OK（error-code/error-message 同行在内） |
| `health-dot` | L43 | OK（health-text L44/health-meta L45 在内） |
| `model-badge` | L58 | OK |

app.js 引用侧交叉：`$("...")` 字面引用 drop-zone(L13)/file-input(L14)/submit-btn(L31,38,41)/preview(L32)/total-score(L68,82)/model-badge(L69,83)/error-\boxed(L79)/error-code(L80)/error-message(L81)/health-dot(L93)/health-text(L94)/health-meta(L95) 与模板 `fill-/value-/bar-${k}`（L72-74,85-86，DIMS=L6 四键）——全部在 index.html 有对应 id，无悬空引用。

### ② 四键旧键扫描（模式 `colou?r|ligh[t]ing|detai[l]`，字符类防自匹配）

- **app.js：0 命中**（appjs_hits=0）——JS 逻辑层旧键 = 0，DIMS L6 = `["composition","light","creativity","story"]` 逐字新键。
- **index.html：9 命中，全部位于 style 块（L7–L37）内**：L10/L13/L18/L19/L22/L25/L26/L33/L34，逐行核均为 CSS `color:`/`border-color`/`background` 属性字面（如 L33 `#error-code{color:var(--red)...}`）——**判例#2 CSS color 豁免**，非键名。
- **style 块外（正文 HTML）：0 命中；`ligh[t]ing`/`detai[l]` 两文件合计 0 命中。**
- 结论：四键旧键 = **0 真命中（PASS）**。

### ③ app.js 错误体与健康灯逻辑（3 点判读）

1. **错误体 → PASS**：L49-56——`!resp.ok || !body || body.error` 进错误分支；L51 类型守卫 `typeof err.code==="string" && typeof err.message==="string"` 后 L52 展示契约错误体；L54 非 JSON 兜底 `` `http_${resp.status}` ``（对齐 05_DEPLOY §3.4）；L60 fetch 异常本地码 `network_error`（前端本地码，非服务端 error.code，不违契约 §3.5 取值表——服务端 code 只展示不伪造）。
2. **健康灯 → PASS**：L116 加载即刻 `pollHealth()` + L117 `setInterval(pollHealth, 3000)`；三色分支 L100 绿（ok∧ready）/L103 黄（degraded）/L106 红（其余）+ L111-112 fetch 失败红·离线；L109 meta 显示 `model · device · uptime_s`（对齐 05_DEPLOY §3.5「灯旁显示 device 与 uptime_s」）。
3. **轮询周期字面 → CONCERN（已登记判例级，不判 FAIL）**：app.js L117 = **3000ms**，05_DEPLOY L115 = 「每 5 s 轮询」——实现快于文档，S1-02 验收未锁周期（200/status=ok 与周期无关）；改文档迁就实现 vs 改实现迁就文档，由 lead 段4 前裁决（预告裁决单号）。

片3 前端三点结论：**锚=8/8 PASS、旧键=0 真命中 PASS（9 处 CSS 判例#2 豁免）、逻辑=错误体 PASS/健康灯 PASS/轮询周期 concern**。
