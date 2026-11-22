# S3-06 门令补跑（落盘法：sh printf 写 python 脚本 → 跑 → tee 证据）
mkdir -p qa/evidence/S3
printf '%s' 'import json,sys;d=json.load(open("data/synthetic/learnability_probe.json",encoding="utf-8"));c=[d["label_feature_correlation"][k]["pearson_r"] for k in ("composition","light","creativity","story")];p=d["pixel_diff_pass15"];ok=(p>=14 and max(c)>=0.30 and min(c)>=0.02);print("pixel_diff_pass15",p,"max_corr",max(c),"min_corr",min(c));sys.exit(0 if ok else 1)' > qa/evidence/S3/S3-06.py
python qa/evidence/S3/S3-06.py 2>&1 | tee qa/evidence/S3/S3-06.log
rc=$?
echo "S3-06_EXIT=$rc"
exit $rc
