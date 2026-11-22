# Aesthetic Prism · 图片审美评分系统

0%→200% 八段推进：合成数据 → HAP-Net 训练 → ONNX 导出 → FastAPI `/score` `/health` → 前端 Demo → benchmark/压测验收。

## 快速开始（段1 骨架）

```sh
make dev          # 一键起服务 http://127.0.0.1:8000（无模型文件时自动 mock 模式）
make test         # pytest -q 冒烟
make lint         # ruff check src tests
make typecheck    # mypy src
make coverage     # pytest-cov，TOTAL 行 ≥80%
make demo         # 一键前后端（段8 扩展，当前 = dev + 静态页）
make reproduce    # 一键复现（段7 扩展，当前 = test + 契约自检）
```

make 不在 PATH 时用全路径：
`C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\make.exe`
兜底：`C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\ezwinports.make_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\make.exe`

## 路径可微调说明与权属（01_ARCH §5）

- `docs/00–07`：ARCH 起草、lead 批准后冻结；`docs/contracts/assets/` 归 ARCH。
- **`qa/` = QA 所有，实现方只读**（裁决 C）：任何实现方不得写入 `qa/evidence/`、`qa/reports/`。
- `data/` `labeling/` = DATA；`src/aesthetic_prism/{model,train,export}` = MODEL；
  `src/aesthetic_prism/serve` `frontend/` = SERVE；`tests/` `scripts/` 由 QA 出题、对应实现方落码；lint/CI 由 SERVE 接线。
- 其余路径（`configs/` `docker/` `benchmarks/` `models/` `reports/` `assets/` `scripts/`）在 01_ARCH §5 树内可微调，回改经 lead 批准。

## 文档与门禁

- 需求/架构/部署/计划/验收：`docs/00_PRD.md` `docs/01_ARCH.md` `docs/05_DEPLOY.md` `docs/07_PLAN.md` `docs/08_ACCEPTANCE.md`
- 契约：`docs/contracts/score_api_request_response.md`（C-SERVE-01）、`docs/contracts/onnx_io_names.md`（C-EXPORT-01）
- 门禁命令一律 Git `sh -c "…"` 执行（裁决 D，01_ARCH §6）；端口 8000。

## 蒸馏与评分复现（阶段 4）

```sh
# 1) 合成数据 + 全量蒸馏（teacher 6000 步 + student 蒸馏 + ONNX 导出）
PYTHONPATH=src python -m aesthetic_prism.distill --source data/synthetic/index.json
# 产物：artifacts/student.onnx、models/hapnet_teacher.onnx、reports/distill_report.json、
#       checkpoints/distill/{teacher,student}/*/best.pt

# 2) 单图评分 CLI
PYTHONPATH=src python -m aesthetic_prism.score path/to/img.jpg
# 输出 6 字段 JSON；缺 artifacts/student.onnx 时 rc=1

# 3) 服务 /score 真实 ONNX 模式
AP_MODE=onnx make dev          # 默认加载 artifacts/student.onnx
# mock 模式（无模型文件时）：AP_MODE=mock 或缺模型自动回退
```

## 验收标准（README 自检）

```sh
sh -c "grep -q 'make dev' README.md && grep -q 'qa/' README.md && grep -q 'sh -c' README.md"
```
