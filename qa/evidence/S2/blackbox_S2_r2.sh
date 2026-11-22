# 段2 补跑：S2-08（修后）+ S3-01 双证据（08 原节点 FAIL 留证 + 实现真名补跑）+ S0 回归
set -o pipefail 2>/dev/null || true
mkdir -p qa/evidence/S2 qa/evidence/S3 qa/evidence/S0
rc=0

echo '=== S2-08 after self-fix ==='
mkdir -p qa/evidence/S2
printf '%s' 'import json,sys;d=json.load(open("reports/label_quality.json"));m=d.get("metric") or d.get("relabel_agreement") or d.get("agreement");rate=m.get("agreement") if isinstance(m,dict) else m;rate=d.get("agreement",rate) if rate is None else rate;n=d.get("n",d.get("sample_n",d.get("n_relabel")));print("agreement=",rate,"n=",n);assert rate is not None,rate;assert float(rate)>=0.70,rate;assert n is not None,n;assert int(n)>0,n' > qa/evidence/S2/S2-08.py
python qa/evidence/S2/S2-08.py 2>&1 | tee qa/evidence/S2/S2-08.log
echo "S2-08_EXIT=$?"

echo '=== S3-01 as-written (08 original node id) ==='
pytest -q tests/test_data.py::test_dataloader_shape 2>&1 | tee qa/evidence/S3/S3-01.log
echo "S3-01_EXIT=${PIPESTATUS[0]}"

echo '=== S3-01 supplementary: actual node id ==='
pytest -q tests/test_data.py::test_s3_01_dataloader_shape 2>&1 | tee qa/evidence/S3/S3-01_actual_node.log
echo "S3-01_actual_EXIT=${PIPESTATUS[0]}"

echo '=== regression S0-01..04 (no port) ==='
sh qa/evidence/S0/S0-01.sh 2>&1 | tee -a qa/evidence/S0/regression_S2.log
echo "S0-01_EXIT=$?"
sh qa/evidence/S0/S0-02.sh 2>&1 | tee -a qa/evidence/S0/regression_S2.log
echo "S0-02_EXIT=$?"
python qa/evidence/S0/S0-03.py 2>&1 | tee -a qa/evidence/S0/regression_S2.log
echo "S0-03_EXIT=$?"
python qa/evidence/S0/S0-04.py 2>&1 | tee -a qa/evidence/S0/regression_S2.log
echo "S0-04_EXIT=$?"
