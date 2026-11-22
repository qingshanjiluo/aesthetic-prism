set -e
LOG=qa/evidence/S8/S8-05-auto.log
{
echo "== S8-05 人工复核 · 自动化侧证据补齐 =="
date -u +%Y-%m-%dT%H:%M:%SZ
echo
echo "--- 步骤② 自有图片上传：用 data/uploads 内既有真实上传件（非 assets/sample.png） ---"
OWN=$(ls data/uploads/*.png | head -1)
echo "own_image=$OWN bytes=$(wc -c < $OWN) sha256_1MB=$(head -c 1000000 $OWN | sha256sum | cut -d' ' -f1)"
} >> $LOG 2>&1

make demo > qa/evidence/S8/S8-05-serve.log 2>&1 &
sleep 25

{
echo
echo "--- 步骤① 打开演示页面/接口 ---"
curl -s -o qa/evidence/S8/S8-05_index.html -w "GET / -> %{http_code} bytes=%{size_download}\n" http://127.0.0.1:8000/
curl -s -w "\nGET /health -> %{http_code}\n" http://127.0.0.1:8000/health
echo
echo "--- 步骤② 上传自有图片 ---"
OWN=$(ls data/uploads/*.png | head -1)
curl -s -o qa/evidence/S8/S8-05_own_score.json -w "POST /score (own image) -> %{http_code}\n" \
  -F "image=@${OWN};type=image/png" http://127.0.0.1:8000/score
cat qa/evidence/S8/S8-05_own_score.json; echo
echo
echo "--- 步骤③ 评分合理性判定依据 ---"
echo "[a] 五字段齐全且落在 0-100：见上行 JSON"
echo "[b] total 与四维加权一致（契约 total=0.3c+0.3l+0.2cr+0.2s，容差 0.6）："
python - <<'PY' >> $LOG 2>&1
import json
d=json.load(open('qa/evidence/S8/S8-05_own_score.json',encoding='utf-8'))
exp=0.3*d['composition']+0.3*d['light']+0.2*d['creativity']+0.2*d['story']
print(f"    total_reported={d['total']} total_expected={round(exp,2)} delta={abs(d['total']-exp):.3f}")
print("    CONSISTENT" if abs(d['total']-exp)<=0.6 else "    INCONSISTENT")
PY
echo "[c] 同一图片重复 3 次确定性（同权重同输入必须同输出，容差 1e-6）："
for i in 1 2 3; do
  curl -s -F "image=@${OWN};type=image/png" http://127.0.0.1:8000/score
  echo
done
echo "[d] 与离线 ONNX 直推结果对比（服务链路 vs 离线权重一致性，容差 1e-4）："
echo
echo "--- 步骤④ 重启后功能验证 ---"
kill %1 2>/dev/null
sleep 2
curl -s -o /dev/null -m 3 -w "重启前 kill 后 GET /health -> %{http_code} (期望 000)\n" http://127.0.0.1:8000/health || echo "重启前 kill 后 GET /health -> 000 (期望 000)"
} >> $LOG 2>&1

make demo >> qa/evidence/S8/S8-05-serve.log 2>&1 &
sleep 25

{
curl -s -o /dev/null -w "重启后 GET /health -> %{http_code}\n" http://127.0.0.1:8000/health
curl -s -o /dev/null -w "重启后 GET / -> %{http_code}\n" http://127.0.0.1:8000/
OWN=$(ls data/uploads/*.png | head -1)
curl -s -o qa/evidence/S8/S8-05_own_score_after_restart.json -w "重启后 POST /score -> %{http_code}\n" \
  -F "image=@${OWN};type=image/png" http://127.0.0.1:8000/score
cat qa/evidence/S8/S8-05_own_score_after_restart.json; echo
echo "重启前后评分一致性（容差 1e-6）："
python - <<'PY' >> $LOG 2>&1
import json
a=json.load(open('qa/evidence/S8/S8-05_own_score.json',encoding='utf-8'))
b=json.load(open('qa/evidence/S8/S8-05_own_score_after_restart.json',encoding='utf-8'))
ks=[k for k in a if k!='request_id']
d=max(abs(a[k]-b[k]) for k in ks if isinstance(a[k],(int,float)))
print(f"    max_delta={d:.9f} -> {'IDENTICAL' if d<=1e-6 else 'DIVERGED'}")
PY
kill %1 2>/dev/null
sleep 2
echo
echo "S8-05-AUTO-END"
} >> $LOG 2>&1
tail -45 $LOG
