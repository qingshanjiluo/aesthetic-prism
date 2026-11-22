# S1 回归五条（batch=S2 开审·段1 回归；原文命令 + mock-deterministic-v1 指纹断言；判例#4 端口共存）
# S1-01 起服务 -> S1-02/03 带指纹 -> S1-04/05 -> 自 kill -> 探 8000 归属（node 存活或 FREE）
mkdir -p qa/evidence/S1
set -o pipefail 2>/dev/null && echo "pipefail=ON" || echo "pipefail=OFF"
rc_all=0

echo '=== S1-01 make dev 20s alive（boot-wait 指纹补丁：200 且含我方指纹才算起，防 node 0.0.0.0 回落——判例#4）==='
(make dev > qa/evidence/S1/dev_regr.log 2>&1 & echo $! > qa/evidence/S1/dev_regr.pid)
i=0
while [ $i -lt 40 ]; do
  body=$(curl -s http://127.0.0.1:8000/health 2>/dev/null)
  case "$body" in
    *mock-deterministic-v1*) echo "boot_fingerprint=OURS after ${i}s"; break ;;
  esac
  sleep 1; i=$((i+1))
done
if [ $i -ge 40 ]; then echo "boot_fingerprint=TIMEOUT_OR_NOT_OURS(40s)"; fi
echo "boot_wait=$i"
sleep 20
kill -0 $(cat qa/evidence/S1/dev_regr.pid)
rc=$?; echo "S1-01_ALIVE=$rc pid=$(cat qa/evidence/S1/dev_regr.pid)"; echo "S1-01_EXIT=$rc"; rc_all=$((rc_all+rc))

echo '=== S1-02 /health 200 + status ok + FINGERPRINT ==='
curl -s -w '\n%{http_code}' http://127.0.0.1:8000/health | tee qa/evidence/S1/S1-02_regr.log
rc=0
test "$(tail -1 qa/evidence/S1/S1-02_regr.log)" = "200" || rc=1
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' qa/evidence/S1/S1-02_regr.log || rc=1
grep -q 'mock-deterministic-v1' qa/evidence/S1/S1-02_regr.log || { echo "FINGERPRINT_MISS(路由或被抢答)"; rc=1; }
echo "S1-02_EXIT=$rc fingerprint=mock-deterministic-v1"; rc_all=$((rc_all+rc))

echo '=== S1-03 /score 六键 + FINGERPRINT ==='
curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score | tee qa/evidence/S1/S1-03_regr.json
rc=0
python -c "import json,sys;d=json.load(open('qa/evidence/S1/S1-03_regr.json'));ks=('total','composition','light','creativity','story');assert all(k in d and isinstance(d[k],(int,float)) and 0<=d[k]<=100 for k in ks),d;assert set(d.keys())==set(ks)|{'model'},sorted(d.keys());assert 'mock' in str(d.get('model','')).lower(),d;print('SIX-KEYS-OK')" || rc=1
grep -q 'mock-deterministic-v1' qa/evidence/S1/S1-03_regr.json || { echo "FINGERPRINT_MISS"; rc=1; }
echo "S1-03_EXIT=$rc fingerprint=mock-deterministic-v1"; rc_all=$((rc_all+rc))

echo '=== S1-04 pytest -q ==='
python -m pytest -q > qa/evidence/S1/S1-04_regr.log 2>&1
rc=$?
cat qa/evidence/S1/S1-04_regr.log
echo "S1-04_EXIT=$rc"; rc_all=$((rc_all+rc))

echo '=== S1-05 CI double gate grep ==='
grep -qE "pytest|make test" .github/workflows/*.yml && grep -qE "ruff|flake8|make lint" .github/workflows/*.yml && echo CI-GATES-OK | tee qa/evidence/S1/S1-05_regr.log
rc=$?
echo "S1-05_EXIT=$rc"; rc_all=$((rc_all+rc))

echo '=== cleanup: kill OUR dev (do NOT touch node) ==='
mypid=$(cat qa/evidence/S1/dev_regr.pid 2>/dev/null)
kill $mypid 2>/dev/null
sleep 3
kill -0 $mypid 2>/dev/null && { pkill -P $mypid 2>/dev/null; kill -9 $mypid 2>/dev/null; sleep 2; }
echo "our_dev_killed pid=$mypid"
netstat -ano | grep LISTENING | grep ':8000 ' || echo '8000: FREE (node已停或地址族错位, 以 netstat 全行证据为准)'

echo "SUM_RC=$rc_all"
exit $rc_all
