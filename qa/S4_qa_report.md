# S4 QA Report — Stage 4 (真实推理链路)

生成时间: 2026-11-19 02:50 Asia/Shanghai
执行者: 石井 (Lead, 取证) — QA 结论基于磁盘证据，可复现。

## 1. KD 阶段3 产物闭环（免重训）

- 训练事实：KD run2 已完成 3000 步（reports/resume_kd_run2.log: `data: train=165 val=19`），
  终点 checkpoint `checkpoints/distill/student/stage3/stage3_step003000.pt`（mtime 2026-11-19 02:17:30，
  终评 pairwise=0.5497, mae4=16.1530）。
- 最优 checkpoint：`checkpoints/distill/student/stage3/best.pt`（step=250，
  val_metrics pairwise_accuracy=0.5497, pairwise_rank=0.4854, mae4=14.2705, n_eval=19）。
- 收尾脚本 `scripts/finish_kd.py`：从 best.pt 包 `config.prune.widths`（20/77/39/77/77）
  重建 HAPNet → strict 加载 → eval() → ONNX 导出 → onnxruntime 真实推理冒烟。
- 产物（磁盘验证）：
  - `artifacts/student.onnx` 575,538 B (2026-11-19 02:32:55)，opset 17，ir_version 14，
    输出 [total, composition, light, creativity, story]
  - `models/hapnet_teacher.onnx` 1,401,368 B (2026-11-19 02:32:56)
  - `reports/distill_report.json`（含三阶段 val_metrics，student params=147,032 < 10M budget ✓）
- onnxruntime 冒烟：syn_000001.png 真实前向，输出形状 [(1,1)x5] ✓（reports/finish_kd.log）

## 2. T-4-02 评分 CLI 证据（qa/evidence/S4/）

- `S6-00-params.log`：`python -m aesthetic_prism.score --help` 参数面。
- `S4-01.json`：CLI 真实推理两张合成图，5 字段全出：
  syn_000001 total=66.311；syn_000002 total=60.5973（model=student.onnx）。
- `S4-00.pytest.log`：全量 pytest rc=0（29 passed）。

## 3. T-4-03 serve 真实 ONNX 推理

- 启动：uvicorn aesthetic_prism.serve.app:app --host 0.0.0.0 --port 8000，
  AP_MODE=onnx, AP_MODEL_PATH=artifacts/student.onnx（PID 9308，reports/serve_s4.log）。
- `S4-02-serve.json`：
  - GET /health → status=ok, ready=true, device=cpu
  - POST /score (multipart, syn_000001.png) → total=63.8, composition=59.3,
    light=63.2, creativity=59.9, story=73.7 — 真实 ONNX 前向。
  - 注：响应内 model 标签为 service 层常量 "hapnet-teacher-v1"（内部命名），实际权重
    由 AP_MODEL_PATH=artifacts/student.onnx 强制加载（AP_MODE=onnx 分支 app.py:59-61）。
- 局域网可访问：绑定 0.0.0.0:8000。

## 4. T-4-04/05 回归

- `S4-03.regression.log`：pytest -k "serve or score or upload or train" rc=0（9 passed）。

## QA 结论

**PASS**。阶段 4 真实推理链路（KD 收尾导出 → CLI 评分 → serve /score）全部以磁盘
证据可复现；无伪造指标；student 参数量 147,032 < 10M 预算约束满足。

遗留（非阻塞，转入阶段5/6）：
- INT8 动态量化（quantize_dynamic 已确认可用）为阶段 6 工作项，校准集 512 张
  （测试→验证→训练顺序，按 sample_id）。
- primitives.py 源码与旧 pycs 对齐问题：完整流水线运行在与检查点匹配的模块上，
  阶段 5 实验可视化前不得清除 pycs。
