mkdir -p qa/evidence/S1
(make dev > qa/evidence/S1/dev.log 2>&1 & echo $! > qa/evidence/S1/dev.pid)
sleep 20
kill -0 $(cat qa/evidence/S1/dev.pid)
rc=$?
echo "S1-01_ALIVE=$rc pid=$(cat qa/evidence/S1/dev.pid)"
curl -s -o /dev/null -w 'health_during=%{http_code}\n' http://127.0.0.1:8000/health
tail -3 qa/evidence/S1/dev.log
exit $rc
