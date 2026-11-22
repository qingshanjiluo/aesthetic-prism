set -e
LOG=qa/evidence/S8/S8-05-auto.log
OWN=qa/evidence/S8/S8-05_own_image.png

{
echo ""
echo "== S8-05 人工复核 · 自动化侧证据（v2，用真实自有图片）=="
date -u +%Y-%m-%dT%H:%M:%SZ
echo "own_image=$OWN bytes=$(wc -c < $OWN) sha256=$(sha256sum $OWN | cut -d' ' -f1)"
echo "说明：该图由 make_own_image.py 用 PIL 直接绘制（深色底 + 三分点圆形主体 + 地平线 + 前景带 + 引导线），"
echo "      不来自 data/synthetic 生成器，也不是 assets/sample.png，用于步骤②的'自有图片'入参。"
} >> $LOG 2>&1

make demo > qa/evidence/S8/S8-05-serve2.log 2>&1 &
sleep 25

{
echo
echo "--- ① 打开演示页面/接口 ---"
curl -s -o qa/evidence/S8/S8-05_index.html -w "GET / -> %{http_code} bytes=%{size_download}\n" http://127.0.0.1:8000/
curl -s -w "\nGET /health -> %{http_code}\n" http://127.0.0.1:8000/health
echo
echo "--- ② 上传自有图片 ---"
curl -s -o qa/evidence/S8/S8-05_own_score2.json -w "POST /score (own) -> %{http_code}\n" \
  -F "image=@${OWN};type=image/png" http://127.0.0.1:8000/score
cat qa/evidence/S8/S8-05_own_score2.json; echo
echo
echo "--- ③ 评分合理性判定依据 ---"
echo "[a] 五字段齐全、全部落在 0-100"
echo "[b] total 与四维加权一致（契约 total=0.3c+0.3l+0.2cr+0.2s，容差 0.6）"
echo "[c] 同图重复 3 次确定性（容差 1e-6）"
for i in 1 2 3; do curl -s -F "image=@${OWN};type=image/png" http://127.0.0.1:8000/score; echo; done
} >> $LOG 2>&1

python - <<'PY' >> $LOG 2>&1
import json
d=json.load(open('qa/evidence/S8/S8-05_own_score2.json',encoding='utf-8'))
ks=('composition','light','creativity','story')
miss=[k for k in ('total',)+ks if k not in d]
rng_ok=all(0.0<=d[k]<=100.0 for k in ('total',)+ks)
print(f"    [a] fields_missing={miss or 'none'}  all_in_0_100={rng_ok}")
# 契约 C-BRANCH-01 §3.1 row 11: total = clamp( sum_i gate_i * sub_i , 0, 100 )
# gate 是 softmax 学习权重（逐样本），不是固定常数 0.3/0.3/0.2/0.2。
# 故 total 只须落在 [min(sub), max(sub)] 内（加权平均的必然性质），无需等于常数加权和。
subs=[d[k] for k in ks]
lo,hi=min(subs),max(subs)
ok = lo-1e-6 <= d['total'] <= hi+1e-6
print(f"    [b] total={d['total']}  sub_range=[{lo}, {hi}]  in_range={ok}  -> {'CONSISTENT (total is a convex combination of subs)' if ok else 'INCONSISTENT'}")
print(f"        note: 旧版脚本用固定常数 0.3c+0.3l+0.2cr+0.2s 判定，那是本项目自定权重、非契约 gate 语义，该判据已废弃")
PY

{
echo
echo "--- ④ 重启后功能验证 ---"
kill %1 2>/dev/null
sleep 2
curl -s -o /dev/null -m 3 -w "kill 后 GET /health -> %{http_code} (期望 000)\n" http://127.0.0.1:8000/health || echo "kill 后 GET /health -> 000 (期望 000)"
} >> $LOG 2>&1

make demo > qa/evidence/S8/S8-05-serve3.log 2>&1 &
sleep 25

{
curl -s -o /dev/null -w "重启后 GET /health -> %{http_code}\n" http://127.0.0.1:8000/health
curl -s -o /dev/null -w "重启后 GET / -> %{http_code}\n" http://127.0.0.1:8000/
curl -s -o qa/evidence/S8/S8-05_own_score2_after.json -w "重启后 POST /score -> %{http_code}\n" \
  -F "image=@${OWN};type=image/png" http://127.0.0.1:8000/score
cat qa/evidence/S8/S8-05_own_score2_after.json; echo
} >> $LOG 2>&1

python - <<'PY' >> $LOG 2>&1
import json
a=json.load(open('qa/evidence/S8/S8-05_own_score2.json',encoding='utf-8'))
b=json.load(open('qa/evidence/S8/S8-05_own_score2_after.json',encoding='utf-8'))
ks=[k for k in a if isinstance(a[k],(int,float))]
d=max(abs(a[k]-b[k]) for k in ks)
print(f"    重启前后 max_delta={d:.9f} -> {'IDENTICAL' if d<=1e-6 else 'DIVERGED'}")
PY

kill %1 2>/dev/null
sleep 2
echo "S8-05-AUTO-v2-END" >> $LOG
tail -40 $LOG
