# 版本管理计划（T-8-04 / S8-00.version）

生成时间：2026-11-19 · 项目：aesthetic-prism · 当前仓库状态：**非 git 仓库**（目录无 .git，Windows 本地工程目录）

## 1. 现状

- 项目目录未初始化 git；无历史提交、无远程、无标签。
- 交付物以磁盘快照 + sha256 记录于 `qa/`（如 student.onnx 575,538B sha256_1MB=8fb5c6da…、student_int8.onnx 274,625B sha256_1MB=4acde982…）。

## 2. 初始化建议（执行序列）

```bash
cd <AP_ROOT>
git init -b main
printf '__pycache__/\n*.pyc\ndata/uploads/\nreports/html/\nqa/evidence/S8/qps_*.csv\nnode_modules/\n' > .gitignore
git add -A
git commit -m "v0.1.0: initial release (student ONNX serve pipeline, QA gates 1-7)"
git tag -a v0.1.0 -m "first tagged release"
```

## 3. 标签计划 v0.1.0 → v1.0.0

| 标签 | 触发条件 | 关键内容 |
|---|---|---|
| v0.1.0 | 本计划落地 + git init | 当前全部阶段产物；mae4 门控失败已知（val 10.092 / test 8.196 > 5.0） |
| v0.2.0 | 主动学习第一轮标注闭环 | active_queue 标注 ≥200 样本并重训，mae4 test ≤ 8.0 |
| v0.3.0 | INT8 量化修复 | student_int8 精度对齐 FP32（ΔMAE ≤0.5）且延迟不劣化，切 primary=onnx_int8 |
| v0.5.0 | mae4 门控达成 | test mae4 ≤ 5.0（GATE-6 由 PARTIAL FAIL 转 PASS） |
| v0.9.0 | 负载容量升级 | qps ≥ 20 @ fail=0（MAX_INFLIGHT 排队化或横向扩容） |
| v1.0.0 | 全验收门通过 + 人工检查签字 | S8-05 人工检查完成，全部 GATE PASS |

## 4. 版本号约定

- 语义化版本 MAJOR.MINOR.PATCH；预发布用 `-rc.N` 后缀（如 v0.5.0-rc.1）。
- 每个标签必须附：模型工件 sha256（1MB 分块）+ 当轮 QA 报告路径（`qa/Sx_qa_report.md`）。

## 5. 已知限制

- 当前非 git 仓库，标签计划仅在 git init 后生效；v0.1.0 之前的可追溯性依赖 `qa/` 目录 sha256 证据链。
- 大二进制（.onnx、数据集）建议后续引入 git-lfs；本计划先以 sha256 记录替代。

## 6. 冻结命令复现

```
python scripts/active_learning.py     # S8-00.active
cat data/annotations/active_queue.json
cat reports/versioning.md             # 本文件
```

证据：`qa/evidence/S8/S8-00.version.log`
