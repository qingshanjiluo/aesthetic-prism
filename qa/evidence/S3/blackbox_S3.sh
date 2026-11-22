# batch3 黑盒 S3-02..05（47 条基线内已存在；pipefail + 每块 rc=$? 聚合）
mkdir -p qa/evidence/S3
set -o pipefail 2>/dev/null && echo "pipefail=ON" || echo "pipefail=OFF"
rc_all=0

echo '=== S3-02 forward/backward shapes ==='
pytest -q tests/test_model.py::test_forward_backward_shapes 2>&1 | tee qa/evidence/S3/S3-02.log
rc=$?; echo "S3-02_EXIT=$rc"; rc_all=$((rc_all+rc))

echo '=== S3-03 20-step loss descent ==='
python -m src.train --steps 20 --loss-log qa/evidence/S3/loss.json 2>&1 | tee qa/evidence/S3/S3-03_train.log
rc=$?; echo "S3-03_train_EXIT=$rc"; rc_all=$((rc_all+rc))
if [ $rc -eq 0 ]; then
  python -c "import json,statistics as st,json as j;L=j.load(open('qa/evidence/S3/loss.json'));assert len(L)>=20,len(L);assert st.mean(L[-5:])<st.mean(L[:5]),(L[:5],L[-5:]);print('loss_desc=OK n=',len(L))" 2>&1 | tee qa/evidence/S3/S3-03.log
  rc=$?; echo "S3-03_check_EXIT=$rc"; rc_all=$((rc_all+rc))
else
  echo "S3-03_train_FAIL skip check" | tee qa/evidence/S3/S3-03.log; rc_all=$((rc_all+1))
fi

echo '=== S3-04 checkpoint roundtrip ==='
pytest -q tests/test_model.py::test_checkpoint_roundtrip 2>&1 | tee qa/evidence/S3/S3-04.log
rc=$?; echo "S3-04_EXIT=$rc"; rc_all=$((rc_all+rc))

echo '=== S3-05 output range 0-100 ==='
pytest -q tests/test_model.py::test_output_range 2>&1 | tee qa/evidence/S3/S3-05.log
rc=$?; echo "S3-05_EXIT=$rc"; rc_all=$((rc_all+rc))

echo "SUM_RC=$rc_all"
exit $rc_all
