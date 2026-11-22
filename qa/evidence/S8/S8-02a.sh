{
echo ""
echo "== S8-02 repeat run A (server confirmed up: /health 200) =="
date -u +%Y-%m-%dT%H:%M:%SZ
} >> qa/evidence/S8/S8-02.log
PYTHONUTF8=1 locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv qa/evidence/S8/qps >> qa/evidence/S8/S8-02.log 2>&1
python -c "import csv;r=list(csv.DictReader(open('qa/evidence/S8/qps_stats.csv')))[-1];q=float(r['Requests/s']);f=int(r['Failure Count']);print('runA qps=',q,'fail=',f);assert q>=5 and f==0,(q,f)" >> qa/evidence/S8/S8-02.log 2>&1
echo "runA exit=$?"
tail -2 qa/evidence/S8/S8-02.log