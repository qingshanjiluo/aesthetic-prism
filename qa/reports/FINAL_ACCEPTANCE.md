# 最终验收报告 — Aesthetic Prism（阶段 8）

生成时间：2026-11-19T06:23Z · 验收人：QA（独立判断）· 项目根：`G:\皮皮\编程项目\aesthetic-prism`

## 验收结论

**结论：有条件通过（CONDITIONAL PASS）。**7 项检查中 5 项 PASS、1 项 CONFIRMED-FAIL（模型精度三项门控）、
1 项人工检查已补自动化证据待人工签字。交付系统在功能、性能、契约、可复现性维度均达成。

**重要更正（2026-11-19，goal① 取证）**：此前记录的 mae4 8.196 / pairwise 0.910 / pearson 0.956 全部无效 ——
`metric_recheck.py` 的 split 口径（按序号切分）与训练侧契约口径（`split_of(sha256(id)[:8]%20)`）不同源，
旧口径的 test 20 个样本在契约口径下 20/20 属于 train，指标是在训练集上测出的。
修正后按契约口径重跑的**真实指标**为：val mae4 14.2705 / pairwise 0.5497 / pearson 0.1551，test mae4 14.7202 / pairwise 0.4622 / pearson 0.0062 —— **三项全部不达标**。
归因与排除路径见 `reports/MAE4_ROOT_CAUSE.md`，证据见 `qa/evidence/S8/G1-*.log`。

| 编号 | 检查项 | 判定 | 证据 |
|---|---|---|---|
| S8-01 | `make demo` 一键起服务，`/score` 返回 200 | PASS | `qa/evidence/S8/S8-01.log`（health 200 / index 200 / score 200，kill 后 000） |
| S8-02 | locust 压测 qps≥5 且 Failure Count==0 | PASS | `qa/evidence/S8/S8-02.log`、`qps_stats.csv`、`reports/load_report.json`；**两轮独立复现**：run1 qps=8.019 / fail=0 / 209 请求 / p95=140ms，run2 qps=7.622 / fail=0 / 153 请求 / p95=110ms |
| S8-03 | 本文件含「验收结论」「已知限制」「遗留风险」三节 | PASS | 本文件章节（正文 H2 标题） |
| S8-04 | 已知限制条目 ≥5 | PASS | 本文件「已知限制」共 8 条 |
| S8-05 | 人工检查 | PENDING（自动化证据已齐，待人工签） | `qa/evidence/S8/S8-05-auto.log` 四项证据：自有图片上传 200 / total 与四维加权一致 delta 0.010 / 三次重复完全一致 / 重启前后 max_delta 0.000000000 |
| T-8-03 | 主动学习采样脚本产出标注队列 | PASS | `scripts/active_learning.py`、`data/annotations/active_queue.json`、`qa/evidence/S8/S8-00.active.log` |
| T-8-04 | 版本管理计划 | PASS | `reports/versioning.md`、`qa/evidence/S8/S8-00.version.log` |

## 已知限制

1. **模型精度三项门控全部未达标（真实失败，已更正）**：契约口径下 student val mae4 14.2705 / pairwise 0.5497 / pearson 0.1551，test mae4 14.7202 / pairwise 0.4622 / pearson 0.0062；门限为 mae4 ≤5.0、pairwise ≥0.68、pearson ≥0.70。test pairwise 0.4622 已低于随机水平，说明当前模型不具备可用的排序能力。此前 S5–S8 记录的 pairwise 0.910 / pearson 0.956 系评测 split 口径错位造成的指标泄漏（见 `reports/MAE4_ROOT_CAUSE.md`）。
2. **评测脚本口径错位已修复，但影响面需回溯**：`src/aesthetic_prism/bench/metric_recheck.py` 原按 id 排序序号切分，与训练侧 `schema.split_of` 不同源；已改为调用契约 `split_of`。阶段 6/7/8 基于旧口径得出的精度结论均需按新口径重读。
3. **数据量不足是当前第一瓶颈**：契约口径下 train 仅 165 样本、376k 参数的教师自身 val mae4 14.2059 也未达标，说明不是剪枝/蒸馏损失，而是样本量不足。修复方向为扩数据重训，不是调参。
4. **剪枝不是 mae4 主因**：147k 学生与 376k 教师在**同口径**下 mae4 几乎相同（14.2705 vs 14.2059）。
5. **INT8 量化模型不可用为 primary**：`student_int8.onnx`（274,625B，sha256_1MB=4acde982…）精度未对齐且实测推理慢于 FP32，故 `primary=fp32`；量化收益（体积 -52%）未兑现为延迟收益。
6. **负载并发上限低**：`MAX_INFLIGHT=4`，超出即 429（E13，不排队）。S8-02 达标依赖压测侧限速至 between(0.6,1.0)s；8 并发真实打满会稳定产生 429，容量不具备突发弹性。
7. **单机单进程服务**：uvicorn 单 worker，无横向扩容、无队列削峰；进程内 Semaphore 限流无法跨进程生效。
8. **非 git 仓库，无版本追溯**：项目目录未初始化 git，`reports/versioning.md` 的标签计划需在 `git init` 后生效；v0.1.0 之前的可追溯性仅依赖 `qa/` 目录 sha256 证据链。

## 遗留风险

- **精度风险（高）**：三项指标全不达标且 test pairwise 低于随机，当前模型不可用于任何依赖分数或排序的业务判据。必须完成扩数据重训后方可放行。
- **历史结论可信度风险（高）**：阶段 6/7/8 的精度类结论建立在有泄漏的评测口径上；除本文已更正的数字外，`reports/MODEL_CARD.md`、`reports/DATA_CARD.md`、`qa/S6~S8_qa_report.md` 中的精度引用需一并复核。
- **容量风险（中）**：8 并发以上稳定 429，且客户端需自行实现退避重试（契约 §3.5）。无重试逻辑的调用方在突发流量下会直接看到错误率上升。
- **单点风险（中）**：单进程服务，崩溃即全站不可用；无健康检查自动重启、无优雅降级到 mock 模式。
- **可追溯风险（低）**：非 git 仓库，无法用 tag/commit 定位任一验收时点的完整代码状态。
- **量化风险（低）**：INT8 路径未验证精度对齐，若后续切换为 primary 将引入未测量的精度回退。

## 冻结命令复现

```bash
# S8-01
make demo &
sleep 30
curl -s -o /dev/null -w "%{http_code}\n" -F "image=@assets/sample.png;type=image/png" http://127.0.0.1:8000/score
kill %1

# S8-02
PYTHONUTF8=1 locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv qa/evidence/S8/qps
python -c "import csv;r=list(csv.DictReader(open('qa/evidence/S8/qps_stats.csv')))[-1];q=float(r['Requests/s']);f=int(r['Failure Count']);print('qps=',q,'fail=',f);assert q>=5 and f==0,(q,f)"
python src/aesthetic_prism/bench/load_report.py

# T-8-03
python scripts/active_learning.py

# T-8-04
cat reports/versioning.md
```
