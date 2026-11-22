LOG=qa/evidence/S8/S8-01.log
{
echo ""
echo "== S8-01 RERUN (clean port) =="
date -u +%Y-%m-%dT%H:%M:%SZ
make demo &
sleep 30
echo "-- /health --"
curl -s -o /dev/null -w "health_http=%{http_code}\n" http://127.0.0.1:8000/health
echo "-- / --"
curl -s -o /dev/null -w "index_http=%{http_code}\n" http://127.0.0.1:8000/
echo "-- /score --"
CODE=$(curl -s -o qa/evidence/S8/S8-01_score_body.json -w "%{http_code}" -F "image=@assets/sample.png;type=image/png" http://127.0.0.1:8000/score)
echo "score_http=$CODE"
cat qa/evidence/S8/S8-01_score_body.json
echo
kill %1 2>/dev/null
sleep 2
curl -s -o /dev/null -m 3 -w "after_kill_http=%{http_code}\n" http://127.0.0.1:8000/health || echo "after_kill: server down (expected)"
echo "S8-01-RERUN-VERDICT: score_http=$CODE"
} >> $LOG 2>&1
tail -18 $LOG