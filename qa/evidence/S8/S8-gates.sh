{
echo "== S8-00 quality gates (final, after fix) =="
date -u +%Y-%m-%dT%H:%M:%SZ
echo "--- ruff ---"
ruff check src tests
echo "ruff_exit=$?"
echo "--- mypy ---"
mypy src
echo "mypy_exit=$?"
echo "--- pytest (AP_MODE=mock) ---"
AP_MODE=mock python -m pytest -q
echo "pytest_exit=$?"
echo "--- coverage ---"
AP_MODE=mock python -m pytest --cov --cov-report=term -q 2>&1 | grep -E "^TOTAL|passed|failed"
} >> qa/evidence/S8/S8-00.gates.log 2>&1
tail -20 qa/evidence/S8/S8-00.gates.log