mkdir -p qa/evidence/S1
echo '=== S1-04 pytest ==='
python -m pytest -q > qa/evidence/S1/S1-04.log 2>&1
r4=$?
cat qa/evidence/S1/S1-04.log
echo "S1-04_EXIT=$r4"
echo '=== S1-05 CI ==='
grep -qE "pytest|make test" .github/workflows/*.yml && grep -qE "ruff|flake8|make lint" .github/workflows/*.yml && echo CI-GATES-OK | tee qa/evidence/S1/S1-05.log
r5=$?
echo "jobs=$(grep -E '^  (lint|test):' .github/workflows/*.yml | tr -d ' :' | tr '\n' ',')"
echo "S1-05_EXIT=$r5"
exit $((r4+r5))
