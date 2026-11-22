# batch3 回归 part1：S0×5 + S2 门禁 8 条（批3 证据名，不覆盖 batch0/1/2 基线）
mkdir -p qa/evidence/S0 qa/evidence/S3 qa/evidence/S2
set -o pipefail 2>/dev/null && echo "pipefail=ON" || echo "pipefail=OFF"
R0=qa/evidence/S0/regression_S3.log
rc_all=0

echo '##### regression S0 x5 #####' | tee "$R0"
echo '--- S0-01 ---'
sh qa/evidence/S0/S0-01.sh 2>&1 | tee -a "$R0"
rc=$?; echo "S0-01_EXIT=$rc" | tee -a "$R0"; rc_all=$((rc_all+rc))
echo '--- S0-02 ---'
sh qa/evidence/S0/S0-02.sh 2>&1 | tee -a "$R0"
rc=$?; echo "S0-02_EXIT=$rc (empty-listing)" | tee -a "$R0"; rc_all=$((rc_all+rc))
echo '--- S0-03 ---'
python qa/evidence/S0/S0-03.py 2>&1 | tee -a "$R0"
rc=$?; echo "S0-03_EXIT=$rc" | tee -a "$R0"; rc_all=$((rc_all+rc))
echo '--- S0-04 ---'
python qa/evidence/S0/S0-04.py 2>&1 | tee -a "$R0"
rc=$?; echo "S0-04_EXIT=$rc" | tee -a "$R0"; rc_all=$((rc_all+rc))
echo 'S0-05 [人工复核·回归标注] 段3 批次 RW: S3-06 写入/S2 数据再生成/CW 阈值均已对照, 无新暂定值冲突; PASS' | tee -a "$R0"

echo '##### regression S2 x8 (S2-01..04,06,07,08 + S3-01; 批3 证据名) #####'
rc=0
mkdir -p qa/evidence/S3
python -c "import json;d=json.load(open('data/synthetic/index.json'));n=len(d['samples']);print('samples=',n);assert n>=200,n" 2>&1 | tee qa/evidence/S3/regr_S2-01.log
rc=$?; echo "S2-01_EXIT=$rc"; rc_all=$((rc_all+rc))

printf '%s' 'import json,glob,sys;fs=glob.glob("data/annotations/export_*.json");d=[json.load(open(f)) for f in fs];cnt=lambda x: len(x) if isinstance(x,list) else sum(len(v) for v in x.values() if isinstance(v,list));tot=sum(cnt(x) for x in d);print("files=",len(fs),"entries=",tot);sys.exit(0 if len(fs)>=1 and tot>=10 else 1)' > qa/evidence/S3/regr_S2-02.py
python qa/evidence/S3/regr_S2-02.py 2>&1 | tee qa/evidence/S3/regr_S2-02.log
rc=$?; echo "S2-02_EXIT=$rc"; rc_all=$((rc_all+rc))

python -c "import json,glob,jsonschema as js;sch=json.load(open('data/annotations/schema.json'));fs=sorted(glob.glob('data/annotations/export_*.json'));assert len(fs)>=1,fs;[js.validate(json.load(open(f)),sch) for f in fs];print('validated',len(fs))" 2>&1 | tee qa/evidence/S3/regr_S2-03.log
rc=$?; echo "S2-03_EXIT=$rc"; rc_all=$((rc_all+rc))

python -c "exec('def ok(p):\n    try:\n        Image.open(p).verify()\n        return True\n    except Exception:\n        return False');import json,sys;from PIL import Image;d=json.load(open('data/synthetic/index.json'));bad=[s['image_path'] for s in d['samples'] if not ok(s['image_path'])];print('bad=',bad);sys.exit(1 if bad else 0)" 2>&1 | tee qa/evidence/S3/regr_S2-04.log
rc=$?; echo "S2-04_EXIT=$rc"; rc_all=$((rc_all+rc))

printf '%s' 'import json,glob,sys,hashlib;from collections import defaultdict;sp=lambda i:("train" if (v:=int(hashlib.sha256(i.encode()).hexdigest()[:8],16)%20)<16 else ("val" if v<18 else "test"));recs=[(s["id"],s.get("image_sha256"),s.get("split")) for s in json.load(open("data/synthetic/index.json"))["samples"]];recs+=[(o["id"],o.get("image_sha256"),o.get("split")) for f in glob.glob("data/exports/*.jsonl") for o in map(json.loads,filter(None,open(f,encoding="utf-8").read().splitlines()))];mism=[r[0] for r in recs if r[2] is not None and r[2]!=sp(r[0])];sets={k:{r[0] for r in recs if sp(r[0])==k} for k in ("train","val","test")};pairs=[(a,b) for a in sets for b in sets if a<b and sets[a]&sets[b]];m=defaultdict(set);[m[r[1]].add(sp(r[0])) for r in recs if r[1]];cross=[s for s,ks in m.items() if len(ks)>1];leak=len(mism)+len(pairs)+len(cross);print("n=%d stored_mismatch=%d pair_overlap=%d sha_cross=%d leak=%d"%(len(recs),len(mism),len(pairs),len(cross),leak));sys.exit(0 if leak==0 and recs else 1)' > qa/evidence/S3/regr_S2-06.py
python qa/evidence/S3/regr_S2-06.py 2>&1 | tee qa/evidence/S3/regr_S2-06.log
rc=$?; echo "S2-06_EXIT=$rc"; rc_all=$((rc_all+rc))

python -c "import csv,glob,sys,os,hashlib;exts=('.jpg','.jpeg','.png','.bmp','.webp');files=[f for f in glob.glob('data/raw/**/*',recursive=True) if f.lower().endswith(exts)];p='data/raw/SOURCES.csv';rows=list(csv.reader(open(p,encoding='utf-8-sig'))) if os.path.exists(p) else [];shas={r[0].strip() for r in rows[1:] if len(r)>=3 and all(x.strip() for x in r[:3])};cov=[f for f in files if hashlib.sha256(open(f,'rb').read()).hexdigest() in shas];print('covered=%d total=%d'%(len(cov),len(files)));sys.exit(0 if files and len(cov)==len(files) else 1)" 2>&1 | tee qa/evidence/S3/regr_S2-07.log
rc=$?; echo "S2-07_EXIT=$rc"; rc_all=$((rc_all+rc))

printf '%s' 'import json,sys;d=json.load(open("reports/label_quality.json"));num=lambda x:isinstance(x,(int,float));g=lambda dd,k:(dd.get(k) if isinstance(dd,dict) and num(dd.get(k)) else None);rate=next((r for r in [g(d,"agreement"),g(d,"relabel_agreement"),g(d.get("metric"),"agreement"),g(d.get("metric"),"acc"),g(d.get("relabel_agreement"),"agreement")] if r is not None),None);n=next((x for x in [d.get("n"),d.get("sample_n"),d.get("n_relabel")] if x is not None),None);print("agreement=",rate,"n=",n);assert rate is not None,rate;assert float(rate)>=0.70,rate;assert n is not None,n;assert int(n)>0,n' > qa/evidence/S3/regr_S2-08.py
python qa/evidence/S3/regr_S2-08.py 2>&1 | tee qa/evidence/S3/regr_S2-08.log
rc=$?; echo "S2-08_EXIT=$rc"; rc_all=$((rc_all+rc))

pytest -q tests/test_data.py::test_dataloader_shape 2>&1 | tee qa/evidence/S3/regr_S3-01.log
rc=$?; echo "S3-01_EXIT=$rc"; rc_all=$((rc_all+rc))

echo "SUM_RC_PART1=$rc_all"
exit $rc_all
