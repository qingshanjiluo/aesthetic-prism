# Aesthetic Prism · Makefile（GNU Make 4.4.1 · Windows；约束见 docs/05_DEPLOY.md §6）
# make PATH alias   : C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\make.exe
# make full fallback: C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\ezwinports.make_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\make.exe
# 编写硬约束：命令体=纯 python/ruff/mypy/locust/docker 调用（cmd 与 sh 双壳安全）；
#   禁 bash-only 语法（无 [[ ]]、无数组、无进程替换、无 heredoc）；不假设 .ONESHELL
#   （每行 recipe 独立 shell，多步逻辑落 scripts/*.py）；Tab 缩进 + .PHONY。
# 门禁命令一律 Git sh -c "..." 执行（裁决 D，docs/01_ARCH.md §6）；端口 8000。

.PHONY: dev test lint typecheck coverage demo reproduce bench load build help

# dev：起 FastAPI（契约端口 8000，前台阻塞；S1-01 由 sh 后台 & 拉起并 kill -0 存活判定）
dev:
	python -m uvicorn --app-dir src aesthetic_prism.serve.app:app --host 127.0.0.1 --port 8000

# test：全量 pytest（S1-04 / S5-04；测试走 mock 模式，不依赖 ONNX）
test:
	python -m pytest -q

# lint：ruff 静态检查（S5-02 / CI lint 门禁）
lint:
	ruff check src tests

# typecheck：mypy 类型检查（S5-03）
typecheck:
	mypy src

# coverage：pytest-cov，输出 TOTAL 行（S5-05 阈值 >=80%）
coverage:
	python -m pytest --cov --cov-report=term -q

# demo：一键前后端（段8 扩展；当前=dev 同源服务，前端静态页挂 /，S8-01 单命令全链路）
demo:
	@echo Aesthetic Prism demo: http://127.0.0.1:8000/
	python -m uvicorn --app-dir src aesthetic_prism.serve.app:app --host 127.0.0.1 --port 8000

# reproduce：段7 全链路复现（T-7-07 / S7-04）：数据体检 -> 评估复算(metric_recheck 全精度)
#   -> 1e-6 与报告比对(src/eval.py --recheck) -> pytest 回归 -> 契约键自检；任一步失败即非零退出
reproduce:
	python src/aesthetic_prism/bench/data_audit.py
	python src/aesthetic_prism/bench/metric_recheck.py
	python src/eval.py --recheck --against reports/metric_recheck.json
	python -m pytest -q
	python -c "import pathlib; t=pathlib.Path('docs/contracts/score_api_request_response.md').read_text(encoding='utf-8'); ks=('total','composition','light','creativity','story','model'); assert all(k in t for k in ks), 'contract keys missing'; print('contract-check OK')"

# ---- 附加目标（段6/段8 门禁执行，命令为真、本轮回执不跑）----
# bench：ORT 推理延迟实测 P50/P95 落盘（S6-02；模块 src/bench 由段6 落码）
bench:
	python -m src.bench --n 200 --out reports/latency.json

# load：locust 压测（S8-02 / AC8；场景 tests/load/locustfile.py 由段8 落码）
load:
	locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv reports/load

# build：CI 镜像构建（AC7）
build:
	docker build -f docker/Dockerfile -t aesthetic-prism:ci .

help:
	@echo targets: dev test lint typecheck coverage demo reproduce bench load build
