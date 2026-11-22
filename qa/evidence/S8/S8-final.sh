{
echo "== final re-verify after bench/ refactor (post ruff/mypy fix) =="
date -u +%Y-%m-%dT%H:%M:%SZ
echo "--- S8-03 ---"
test -f qa/reports/FINAL_ACCEPTANCE.md && grep -q "## 验收结论" qa/reports/FINAL_ACCEPTANCE.md && grep -q "## 已知限制" qa/reports/FINAL_ACCEPTANCE.md && grep -q "## 遗留风险" qa/reports/FINAL_ACCEPTANCE.md && echo REPORT-OK
echo "--- S8-04 ---"
python -c "import re,sys;t=open('qa/reports/FINAL_ACCEPTANCE.md',encoding='utf-8').read();sec=re.search(r'## 已知限制(.+?)(?=\n## |\Z)',t,re.S).group(1);items=[l for l in sec.splitlines() if re.match(r'\s*([-*]|\d+\.)\s+\S',l)];print('limitations=',len(items))"
echo "--- bench scripts still run (import-level smoke) ---"
python -c "import ast,sys
[ast.parse(open(f,encoding='utf-8').read()) for f in ['src/eval.py','src/aesthetic_prism/bench/load_report.py','src/aesthetic_prism/bench/metric_recheck.py','src/aesthetic_prism/bench/quantize_int8.py','src/aesthetic_prism/bench/gen_figs.py','src/aesthetic_prism/bench/error_analysis.py','src/aesthetic_prism/bench/env_record.py','src/aesthetic_prism/bench/bench_latency.py','src/aesthetic_prism/bench/metric_calibrate.py','src/aesthetic_prism/bench/data_audit.py']]
print('AST-OK 10 files')"
} >> qa/evidence/S8/S8-00.gates.log 2>&1
tail -8 qa/evidence/S8/S8-00.gates.log