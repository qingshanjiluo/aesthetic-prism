mkdir -p qa/evidence/S1
(make dev > qa/evidence/S1/dev_s102.log 2>&1 & echo $! > qa/evidence/S1/dev_s102.pid)
i=0
while [ $i -lt 40 ]; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null)
  [ "$code" = "200" ] && break
  sleep 1; i=$((i+1))
done
echo "boot_wait=$i code=$code"
echo '=== S1-02 ==='
curl -s -w '\n%{http_code}' http://127.0.0.1:8000/health | tee qa/evidence/S1/S1-02.log
r2=0
test "$(tail -1 qa/evidence/S1/S1-02.log)" = "200" || r2=1
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' qa/evidence/S1/S1-02.log || r2=1
echo "S1-02_EXIT=$r2"
echo '=== S1-03 ==='
curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score | tee qa/evidence/S1/S1-03.json
r3=0
python -c "import json,sys;d=json.load(open('qa/evidence/S1/S1-03.json'));ks=('total','composition','light','creativity','story');assert all(k in d and isinstance(d[k],(int,float)) and 0<=d[k]<=100 for k in ks),d;assert set(d.keys())==set(ks)|{'model'},sorted(d.keys());assert 'mock' in str(d.get('model','')).lower(),d;print('SIX-KEYS-OK',sorted(d.keys()))" || r3=1
echo "S1-03_EXIT=$r3"
kill $(cat qa/evidence/S1/dev_s102.pid) 2>/dev/null
sleep 2
echo "R2=$r2 R3=$r3"
exit $((r2+r3))
