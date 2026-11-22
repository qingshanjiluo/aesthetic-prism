# 08 全项目验收标准（ACCEPTANCE）

> 本文是图片审美评分系统（Aesthetic Prism，0%→200% 八段推进）的**唯一验收依据**。
> 后续每段集成批次的 QA 报告 `blackbox` 小节必须**逐条引用本文条目 ID**（格式 `S<段号>-<序号>`，如 `S3-01`），
> 不得自造判定标准；发现本文与 `docs/00_PRD.md` 指标冲突时，以 00_PRD 为准并触发本文修订（见 S0-05）。

## 通用约定

- 执行环境（钉死）：「判定命令或方法」列原文一律交 Git 自带的 sh 执行——短命令用 `sh -c "<原文>"`；原文含双引号/`$()`/反引号时用等价落盘法 `printf '%s' '<原文>' > qa/evidence/<条目ID>.sh && sh qa/evidence/<条目ID>.sh`。Git 的 sh 实测 curl/grep/test/tee/wc/python 全可用；**禁止 pwsh/cmd 直跑**（pwsh 的 curl/tee 别名与 `test/$()` 语法会假失败）。S1-01 的后台 `&`/`$!`/`kill -0` 与 S8-01 的 `&`/`kill %1` 仅 sh 语法有效，必须整段 sh 包裹（各条目命令已按落盘法给出）。
- 工作目录：所有命令默认在项目根 `aesthetic-prism/` 下执行（bash 语法；`make dev`/`pytest`/`docker compose` 环境）。
- 服务基址：`http://127.0.0.1:8000`（`make dev` 启动后的契约端口）。
- 证据目录：`qa/evidence/S<段号>/`（QA 所有，实现方只读）；每条命令的输出须 `tee` 或 `-o` 到该条目的证据文件。
- 判定语义：命令退出码 `0` = 通过；非 0 = 失败。断言阈值以本文为准，与 00_PRD 不一致时见 S0-05。
- `/score` 响应 schema（五键已裁决定名，最终对齐依据 = `contracts/` 与 `docs/00_PRD.md`，见 S0-05）：
  `{"total": <float 0–100>, "composition": <float 0–100>, "light": <float 0–100>, "creativity": <float 0–100>, "story": <float 0–100>, "model": "<str>"}`，
  四维 = 构图 / 光影 / 创意 / 故事性（composition / light / creativity / story，与 HAP-Net 四分支同名）。
- 错误响应 schema（全项目统一错误语义）：HTTP 状态码 4xx/5xx，body 为
  `{"error": {"code": "<str 非空>", "message": "<str 非空>"}}`。
- 标注 `[人工复核]` 的条目没有可执行命令，必须按下表“判定命令或方法”列给出的**人工复核步骤**逐步执行并在证据文件记录结论。

## 验收标准

### 段0（0%）文档契约

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S0-01 | 9 份 docs 文档齐全（00_PRD ~ 08_ACCEPTANCE） | `n=$(ls docs/*.md 2>/dev/null \| wc -l); echo "docs count=$n" \| tee qa/evidence/S0/S0-01.log; test "$n" -ge 9` | `n ≥ 9` 且退出码 0 | `qa/evidence/S0/S0-01.log` |
| S0-02 | 9 份 docs 每份均含“## 验收标准”小节 | `grep -L "## 验收标准" docs/*.md > qa/evidence/S0/S0-02.log; test ! -s qa/evidence/S0/S0-02.log` | 缺失清单为空（0 份缺失） | `qa/evidence/S0/S0-02.log` |
| S0-03 | 三份强制契约（00_PRD + 契约索引登记的 API 契约、数据契约）各含四要素：输入/输出/错误语义/验收命令 | `python -c "import re,pathlib,sys;prd=pathlib.Path('docs/00_PRD.md').read_text(encoding='utf-8');m=re.search(r'##\s*契约索引(.+?)(?=\n## \|\Z)',prd,re.S);files=['docs/00_PRD.md']+(re.findall(r'docs/[\w\-/]+\.md',m.group(1)) if m else []);assert len(files)>=3,files;missing=[f for f in files[:3] if not all(k in pathlib.Path(f).read_text(encoding='utf-8') for k in ('输入','输出','错误语义','验收'))];print('checked=',files[:3],'missing=',missing);sys.exit(1 if missing else 0)" 2>&1 \| tee qa/evidence/S0/S0-03.log` | 三份文件四要素齐全，退出码 0 | `qa/evidence/S0/S0-03.log` |
| S0-04 | 本文自检：条目总数 ≥40、每段（段0–8）≥3 条 | `python -c "import re,sys;t=open('docs/08_ACCEPTANCE.md',encoding='utf-8').read();ids=re.findall(r'^\| (S\d-\d+) \|',t,re.M);segs={s:sum(1 for i in ids if i.startswith('S'+s+'-')) for s in '012345678'};print('total',len(ids),segs);sys.exit(0 if len(ids)>=40 and all(v>=3 for v in segs.values()) else 1)" \| tee qa/evidence/S0/S0-04.log` | 总数 ≥40 且每段 ≥3 | `qa/evidence/S0/S0-04.log` |
| S0-05 | [人工复核] 本文暂定值与 `docs/00_PRD.md`、`contracts/`（API/数据契约）逐项对齐（冲突以 00_PRD/contracts 为准并修订本文）。步骤：①核对暂定清单：端口 8000、/score 五键（total/composition/light/creativity/story）、四维中文名（构图/光影/创意/故事性）、错误体 `{"error":{code,message}}`、P50≤150ms、P95≤500ms、pairwise≥0.68、Pearson≥0.70、四子分 MAE≤5.0、n_test≥20（源=03 §7.2/7.4）、QPS≥5、覆盖率≥80%、路径（data/synthetic/index.json、data/annotations/schema.json、reports/figs、artifacts/*.onnx、tests/load/locustfile.py、qa/reports/FINAL_ACCEPTANCE.md）；②逐项标“一致/不一致”（阈值类事实源=00_PRD，CW-S0-02 已对齐 P50≤150/P95≤500/pairwise≥0.68）；③不一致项登记修订工单发 ARCH 并回写本文。 | 人工复核步骤如左 | 暂定清单全部一致，或不一致项均有修订工单编号 | `qa/evidence/S0/S0-05.md` |

### 段1（25%）骨架：make dev、/health、/score mock、pytest、CI

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S1-01 | `make dev` 可一键拉起开发服务 | `mkdir -p qa/evidence/S1; printf '%s' 'mkdir -p qa/evidence/S1; (make dev > qa/evidence/S1/dev.log 2>&1 & echo $! > qa/evidence/S1/dev.pid); sleep 20; kill -0 $(cat qa/evidence/S1/dev.pid)' > qa/evidence/S1/S1-01.sh && sh qa/evidence/S1/S1-01.sh` | 20 秒后进程仍存活（未崩溃、未报错退出）；`&`/`$!`/`kill -0` 仅 sh 语法，必须 sh 包裹执行 | `qa/evidence/S1/dev.log` |
| S1-02 | `GET /health` 健康检查 | `curl -s -w '\n%{http_code}' http://127.0.0.1:8000/health \| tee qa/evidence/S1/S1-02.log; test "$(tail -1 qa/evidence/S1/S1-02.log)" = "200" && grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' qa/evidence/S1/S1-02.log` | HTTP 200 且 `status=="ok"` | `qa/evidence/S1/S1-02.log` |
| S1-03 | `POST /score` mock 模式符合 schema（total+四维均 0–100 数值） | `curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score \| tee qa/evidence/S1/S1-03.json; python -c "import json,sys;d=json.load(open('qa/evidence/S1/S1-03.json'));ks=('total','composition','light','creativity','story');assert all(k in d and isinstance(d[k],(int,float)) and 0<=d[k]<=100 for k in ks),d;assert 'mock' in str(d.get('model','')).lower(),d"` | 字段齐全、5 项均 ∈[0,100]、model 标识含 mock | `qa/evidence/S1/S1-03.json` |
| S1-04 | pytest 测试套件存在且全绿 | `pytest -q \| tee qa/evidence/S1/S1-04.log` | 退出码 0（0 failed） | `qa/evidence/S1/S1-04.log` |
| S1-05 | CI 配置存在且包含 lint+test 门禁 | `grep -qE "pytest\|make test" .github/workflows/*.yml && grep -qE "ruff\|flake8\|make lint" .github/workflows/*.yml && echo CI-GATES-OK \| tee qa/evidence/S1/S1-05.log` | 两类门禁均在 workflow 中 | `qa/evidence/S1/S1-05.log` |

### 段2（50%）数据标注闭环：合成 ≥200 样本、完成 10 次标注并导出过 schema

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S2-01 | 合成样本 ≥200 | `mkdir -p qa/evidence/S2; python -c "import json;d=json.load(open('data/synthetic/index.json'));n=len(d['samples']);print('samples=',n);assert n>=200,n" 2>&1 \| tee qa/evidence/S2/S2-01.log` | `n ≥ 200` | `qa/evidence/S2/S2-01.log` |
| S2-02 | 完成 10 次标注并导出（全部 export_*.json 累计标注条目 ≥10、导出文件 ≥1） | `mkdir -p qa/evidence/S2; printf '%s' 'import json,glob,sys;fs=glob.glob("data/annotations/export_*.json");d=[json.load(open(f)) for f in fs];cnt=lambda x: len(x) if isinstance(x,list) else sum(len(v) for v in x.values() if isinstance(v,list));tot=sum(cnt(x) for x in d);print("files=",len(fs),"entries=",tot);sys.exit(0 if len(fs)>=1 and tot>=10 else 1)' > qa/evidence/S2/S2-02.py && python qa/evidence/S2/S2-02.py 2>&1 \| tee qa/evidence/S2/S2-02.log` | 文件数 ≥1 且累计条目 ≥10（cnt 无回退分支：空 samples 的 export 计 0，防刷过——W10 修；条目语义对齐 04_LABELING §5.1 Σlen(samples)） | `qa/evidence/S2/S2-02.log` |
| S2-03 | 每次导出均通过标注 schema 校验 | `mkdir -p qa/evidence/S2; python -c "import json,glob,jsonschema as js;sch=json.load(open('data/annotations/schema.json'));fs=sorted(glob.glob('data/annotations/export_*.json'));assert len(fs)>=1,fs;[js.validate(json.load(open(f)),sch) for f in fs];print('validated',len(fs))" 2>&1 \| tee qa/evidence/S2/S2-03.log` | 全部 export 文件（≥1 个）逐个 validate 无异常 | `qa/evidence/S2/S2-03.log` |
| S2-04 | 全部合成图像可 100% 解码 | `python -c "exec('def ok(p):\n    try:\n        Image.open(p).verify()\n        return True\n    except Exception:\n        return False');import json,sys;from PIL import Image;d=json.load(open('data/synthetic/index.json'));bad=[s['image_path'] for s in d['samples'] if not ok(s['image_path'])];print('bad=',bad);sys.exit(1 if bad else 0)" 2>&1 \| tee qa/evidence/S2/S2-04.log` | 解码失败数 = 0 | `qa/evidence/S2/S2-04.log` |
| S2-05 | [人工复核] 标注质量抽查。步骤：①从全部导出文件的标注条目中随机抽 10 条；②打开原图人工核对四维标注值是否与画面观感相符（偏差 >30 分记为不合格）；③记录抽样清单与合格数。 | 人工复核步骤如左 | 合格 ≥9/10 | `qa/evidence/S2/S2-05.md` |
| S2-06 | split 防泄漏黑盒断言 | `mkdir -p qa/evidence/S2; printf '%s' 'import json,glob,sys,hashlib;from collections import defaultdict;sp=lambda i:("train" if (v:=int(hashlib.sha256(i.encode()).hexdigest()[:8],16)%20)<16 else ("val" if v<18 else "test"));recs=[(s["id"],s.get("image_sha256"),s.get("split")) for s in json.load(open("data/synthetic/index.json"))["samples"]];recs+=[(o["id"],o.get("image_sha256"),o.get("split")) for f in glob.glob("data/exports/*.jsonl") for o in map(json.loads,filter(None,open(f,encoding="utf-8").read().splitlines()))];mism=[r[0] for r in recs if r[2] is not None and r[2]!=sp(r[0])];sets={k:{r[0] for r in recs if sp(r[0])==k} for k in ("train","val","test")};pairs=[(a,b) for a in sets for b in sets if a<b and sets[a]&sets[b]];m=defaultdict(set);[m[r[1]].add(sp(r[0])) for r in recs if r[1]];cross=[s for s,ks in m.items() if len(ks)>1];leak=len(mism)+len(pairs)+len(cross);print("n=%d stored_mismatch=%d pair_overlap=%d sha_cross=%d leak=%d"%(len(recs),len(mism),len(pairs),len(cross),leak));sys.exit(0 if leak==0 and recs else 1)' > qa/evidence/S2/S2-06.py && python qa/evidence/S2/S2-06.py 2>&1 \| tee qa/evidence/S2/S2-06.log` | 泄漏 0 处、退出码 0（n≥1；stored_mismatch=标注侧 split 字段与复算一致、pair_overlap=0、sha_cross=0 同图不跨 split；W6 承载；split_of=C-DATA-01 §2.2 唯一实现，QA 黑盒按契约算法复算不依赖 src） | `qa/evidence/S2/S2-06.log` |
| S2-07 | SOURCES.csv 版权白名单覆盖率 100% | `mkdir -p qa/evidence/S2; python -c "import csv,glob,sys,os,hashlib;exts=('.jpg','.jpeg','.png','.bmp','.webp');files=[f for f in glob.glob('data/raw/**/*',recursive=True) if f.lower().endswith(exts)];p='data/raw/SOURCES.csv';rows=list(csv.reader(open(p,encoding='utf-8-sig'))) if os.path.exists(p) else [];shas={r[0].strip() for r in rows[1:] if len(r)>=3 and all(x.strip() for x in r[:3])};cov=[f for f in files if hashlib.sha256(open(f,'rb').read()).hexdigest() in shas];print('covered=%d total=%d'%(len(cov),len(files)));sys.exit(0 if files and len(cov)==len(files) else 1)" 2>&1 \| tee qa/evidence/S2/S2-07.log` | 覆盖率=100%（CSV 列序 sha256,许可,URL 按 06_RISK R5 字面序，三列均非空才算覆盖；CSV 缺失 / data/raw 无图 / 覆盖<100% 即 FAIL） | `qa/evidence/S2/S2-07.log` |
| S2-08 | 复标一致率达标且样本量齐 | `mkdir -p qa/evidence/S2; printf '%s' 'import json,sys;d=json.load(open("reports/label_quality.json"));num=lambda x:isinstance(x,(int,float));g=lambda dd,k:(dd.get(k) if isinstance(dd,dict) and num(dd.get(k)) else None);rate=next((r for r in [g(d,"agreement"),g(d,"relabel_agreement"),g(d.get("metric"),"agreement"),g(d.get("metric"),"acc"),g(d.get("relabel_agreement"),"agreement")] if r is not None),None);n=next((x for x in [d.get("n"),d.get("sample_n"),d.get("n_relabel")] if x is not None),None);print("agreement=",rate,"n=",n);assert rate is not None,rate;assert float(rate)>=0.70,rate;assert n is not None,n;assert int(n)>0,n' > qa/evidence/S2/S2-08.py && python qa/evidence/S2/S2-08.py 2>&1 \| tee qa/evidence/S2/S2-08.log` | 一致率字段存在且 ≥0.70 且 n>0（06_RISK R3：复标一致率 <70% 批次回炉；n 缺失即 FAIL；字段名兼容 agreement / relabel_agreement / metric.agreement，样本量 n / sample_n / n_relabel；**RW-S2-QA-01 QA 自改**：原三参 assert SyntaxError + 字段链未适配 metric=字段名指针结构 → 拆双参断言+落盘法，阈值语义 0.70/n>0 不变） | `qa/evidence/S2/S2-08.log` |

### 段3（75%）模型训练：HAP-Net 四分支、20 step loss 下降、四维 0–100

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S3-01 | dataloader 输出形状正确 | `pytest -q tests/test_data.py::test_dataloader_shape \| tee qa/evidence/S3/S3-01.log` | 退出码 0；断言 `x.shape == (B,3,224,224)`、label `(B,4)` 且 label ∈[0,100] | `qa/evidence/S3/S3-01.log` |
| S3-02 | 前向/反向传播形状正确 | `pytest -q tests/test_model.py::test_forward_backward_shapes \| tee qa/evidence/S3/S3-02.log` | 退出码 0；输出 `(B,4)`、四分支梯度非 None 且 finite | `qa/evidence/S3/S3-02.log` |
| S3-03 | 训练 20 step loss 下降 | `python -m src.train --steps 20 --loss-log qa/evidence/S3/loss.json && python -c "import json,statistics as st,json as j;L=j.load(open('qa/evidence/S3/loss.json'));assert len(L)>=20,len(L);assert st.mean(L[-5:])<st.mean(L[:5]),(L[:5],L[-5:])" 2>&1 \| tee qa/evidence/S3/S3-03.log` | 20 条 loss 记录，后 5 步均值 < 前 5 步均值 | `qa/evidence/S3/S3-03.log`、`qa/evidence/S3/loss.json` |
| S3-04 | checkpoint 可存可取且恢复一致 | `pytest -q tests/test_model.py::test_checkpoint_roundtrip \| tee qa/evidence/S3/S3-04.log` | 退出码 0；save→load 后 state_dict 键集合与参数数值全等（atol=0） | `qa/evidence/S3/S3-04.log` |
| S3-05 | 模型四维输出恒在 0–100 | `pytest -q tests/test_model.py::test_output_range \| tee qa/evidence/S3/S3-05.log` | 退出码 0；随机 100 批前向输出全部 ∈[0,100]（含 clamp/sigmoid 后） | `qa/evidence/S3/S3-05.log` |
| S3-06 | 数据可学性断言（learnability probe） | `python -c "import json,sys;d=json.load(open('data/synthetic/learnability_probe.json',encoding='utf-8'));c=[d['label_feature_correlation'][k]['pearson_r'] for k in ('composition','light','creativity','story')];p=d['pixel_diff_pass15'];ok=(p>=14 and max(c)>=0.30 and min(c)>=0.02);print('pixel_diff_pass15',p,'max_corr',max(c),'min_corr',min(c));sys.exit(0 if ok else 1)" 2>&1 \| tee qa/evidence/S3/S3-06.log` | 退出码 0；pixel_diff_pass15 ≥14/15（真值 15）、max(corr 四维) ≥0.30（story 真值 .448）、min(corr 四维) ≥0.02（light 真值 .029）；破线 → RW-3-xx 退 DATA | `qa/evidence/S3/S3-06.log`、`data/synthetic/learnability_probe.json` |

### 段4（100%）功能：单图总分+四维、ONNX 误差 <1e-3

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S4-01 | 真实模型单图评分：总分+四维 | `mkdir -p qa/evidence/S4; curl -s -X POST -F image=@assets/sample.png http://127.0.0.1:8000/score \| tee qa/evidence/S4/S4-01.json; python -c "import json;d=json.load(open('qa/evidence/S4/S4-01.json'));ks=('total','composition','light','creativity','story');assert all(isinstance(d.get(k),(int,float)) and 0<=d[k]<=100 for k in ks),d;assert 'mock' not in str(d.get('model','')).lower(),d"` | 5 项齐全 ∈[0,100]，model 非 mock | `qa/evidence/S4/S4-01.json` |
| S4-02 | ONNX vs PyTorch 误差 <1e-3 | `python -m src.export.compare --onnx artifacts/model.onnx --tol 1e-3 --report qa/evidence/S4/S4-02.log 2>&1 \| tee -a qa/evidence/S4/S4-02.log` | `max_abs_diff < 1e-3`（32 个随机输入） | `qa/evidence/S4/S4-02.log` |
| S4-03 | 错误语义统一（非法路径/非图像/超大文件 → 4xx + error schema） | `for c in "nosuch.png:404\|400" "notimage.txt:400\|415" "huge.png:413"; do f=${c%%:*}; exp=${c##*:}; code=$(curl -s -o /tmp/e.json -w '%{http_code}' -X POST -F image=@qa/fixtures/$f http://127.0.0.1:8000/score); echo "$f -> $code $(cat /tmp/e.json)"; python -c "import json,sys;d=json.load(open('/tmp/e.json'))['error'];assert d['code'] and d['message']"; case "$code" in 4??) ;; *) exit 1;; esac; done 2>&1 \| tee qa/evidence/S4/S4-03.log` | 3 个用例全部 4xx 且 error.code/message 非空 | `qa/evidence/S4/S4-03.log` |
| S4-04 | [人工复核] 分数合理性人眼抽查。步骤：①取 6 张风格/构图差异明显的图（含 1 张明显废片、1 张高质量图）；②逐张调用 /score；③人工核对总分排序与直觉一致（高质量图显著高于废片）。 | 人工复核步骤如左 | 6 张中排序矛盾 0 处 | `qa/evidence/S4/S4-04.md` |

### 段5（125%）工程化：docker compose、lint/typecheck/test、覆盖率

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S5-01 | docker compose 一键构建并起服务 | `mkdir -p qa/evidence/S5; docker compose up --build -d 2>&1 \| tee qa/evidence/S5/S5-01.log; sleep 15; curl -sf http://127.0.0.1:8000/health \| tee -a qa/evidence/S5/S5-01.log` | compose up 退出码 0 且容器内 `/health` 返回 200 | `qa/evidence/S5/S5-01.log` |
| S5-02 | `make lint` 零告警 | `make lint 2>&1 \| tee qa/evidence/S5/S5-02.log` | 退出码 0，0 error 0 warning | `qa/evidence/S5/S5-02.log` |
| S5-03 | `make typecheck` 零错误 | `make typecheck 2>&1 \| tee qa/evidence/S5/S5-03.log` | 退出码 0，mypy/pyright 0 error | `qa/evidence/S5/S5-03.log` |
| S5-04 | `make test` 全绿 | `make test 2>&1 \| tee qa/evidence/S5/S5-04.log` | 退出码 0（0 failed） | `qa/evidence/S5/S5-04.log` |
| S5-05 | 测试覆盖率达标 | `mkdir -p qa/evidence/S5; make coverage 2>&1 \| tee qa/evidence/S5/S5-05.log; grep -E "TOTAL" qa/evidence/S5/S5-05.log \| tail -1 \| awk '{v=$NF;gsub("%","",v);exit !(v+0>=80)}'` | TOTAL 行覆盖率 ≥ 80%（取最后一列百分比，防列错位） | `qa/evidence/S5/S5-05.log` |

### 段6（150%）性能：学生模型 <10M、P50/P95、pairwise accuracy 与 Pearson

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S6-01 | 学生模型参数量 <10M | `python -c "import onnx,math;m=onnx.load('artifacts/student.onnx');n=sum(math.prod(p.dims) for p in m.graph.initializer if p.dims);print('params=',n);assert n<10_000_000,n" 2>&1 \| tee qa/evidence/S6/S6-01.log` | `params < 10_000_000` | `qa/evidence/S6/S6-01.log` |
| S6-02 | P50/P95 推理延迟报告 | `python -m src.bench --n 200 --out qa/evidence/S6/latency.json && python -c "import json;d=json.load(open('qa/evidence/S6/latency.json'));print(d['p50_ms'],d['p95_ms']);assert d['p50_ms']<=150 and d['p95_ms']<=500,d" 2>&1 \| tee qa/evidence/S6/S6-02.log` | 样本 ≥200；P50≤150ms、P95≤500ms（阈值事实源=00_PRD G4/AC8，修订 CW-S0-02） | `qa/evidence/S6/S6-02.log`、`qa/evidence/S6/latency.json` |
| S6-03 | pairwise accuracy 与 Pearson 已报告且达标 | `python -c "import json,sys;m=json.load(open('reports/metrics.json'));n=m.get('n_test');assert n is not None and int(n)>=20,('n_test',n);pa=m['pairwise_accuracy'];pe=m['pearson'];print('n=',n,'pairwise=',pa,'pearson=',pe);assert pa>=0.68 and pe>=0.70,m" 2>&1 \| tee qa/evidence/S6/S6-03.log` | pairwise accuracy ≥0.68（事实源=00_PRD AC3，修订 CW-S0-02）且 Pearson ≥0.70；n_test ≥20（03_TRAINING §7.2/7.4：n<20 判 FAIL 不出达标结论，W7 修） | `qa/evidence/S6/S6-03.log` |
| S6-04 | 指标可复算一致（防手改报告） | `python -m src.eval --recheck --against reports/metrics.json 2>&1 \| tee qa/evidence/S6/S6-04.log` | 退出码 0（复算值与报告逐键一致，容差 1e-6） | `qa/evidence/S6/S6-04.log` |
| S6-05 | [人工复核] 压测/评测环境记录完整。步骤：①核对 `reports/metrics.json` 同目录 README 或报告是否记录 CPU/GPU 型号、并发数、warmup 次数、数据集切分；②缺任一项记不合格。 | 人工复核步骤如左 | 4 项信息齐全 | `qa/evidence/S6/S6-05.md` |
| S6-06 | 四子分 MAE ≤5.0 @0–100 且复算一致 | `python -c "import json,sys;m=json.load(open('reports/metrics.json'));n=m.get('n_test');assert n is not None and int(n)>=20,('n_test',n);mae=m.get('mae_per_dim',m.get('mae'));assert mae is not None,list(m.keys());vals=list(mae.values()) if isinstance(mae,dict) else list(mae);mx=max(float(v) for v in vals);print('n=',n,'mae_max=',mx,mae);assert mx<=5.0,mx" 2>&1 \| tee qa/evidence/S6/S6-06.log && python -m src.eval --recheck --against reports/metrics.json 2>&1 \| tee -a qa/evidence/S6/S6-06.log` | `mae_per_dim`（或 `mae`）四维最大值 ≤5.0（0–100 量纲），复算与报告逐键一致（1e-6）；n_test ≥20（03 §7.4，W7 修） | `qa/evidence/S6/S6-06.log` |

### 段7（175%）实验可视化：图表/模型卡/数据卡/一键复现

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S7-01 | reports/ 图表齐全且非空 | `mkdir -p qa/evidence/S7; n=$(ls reports/figs/*.png 2>/dev/null \| wc -l); k=$(find reports/figs -name '*.png' -size +10k 2>/dev/null \| wc -l); echo "figs=$n big=$k" \| tee qa/evidence/S7/S7-01.log; test "$n" -ge 4 && test "$k" -ge 4` | PNG ≥4 张且每张 >10KB（含 loss 曲线、指标对比、延迟分布、评分分布） | `qa/evidence/S7/S7-01.log` |
| S7-02 | 模型卡存在且含必要小节 | `grep -qE "^#+ .*用途" reports/MODEL_CARD.md && grep -qE "^#+ .*指标" reports/MODEL_CARD.md && grep -qE "^#+ .*局限" reports/MODEL_CARD.md && grep -qE "^#+ .*复现" reports/MODEL_CARD.md && echo MODEL-CARD-OK \| tee qa/evidence/S7/S7-02.log` | 含 用途/数据或训练/指标/局限/复现 ≥4 必要小节 | `qa/evidence/S7/S7-02.log` |
| S7-03 | 数据卡存在且含必要小节 | `grep -qE "^#+ .*来源" reports/DATA_CARD.md && grep -qE "^#+ .*构成" reports/DATA_CARD.md && grep -qE "^#+ .*标注" reports/DATA_CARD.md && grep -qE "^#+ .*局限" reports/DATA_CARD.md && echo DATA-CARD-OK \| tee qa/evidence/S7/S7-03.log` | 含 来源/构成/标注流程/局限 ≥4 必要小节 | `qa/evidence/S7/S7-03.log` |
| S7-04 | 一键复现命令可复跑且结果一致 | `make reproduce > qa/evidence/S7/S7-04.log 2>&1 && python -m src.eval --recheck --against reports/metrics.json >> qa/evidence/S7/S7-04.log 2>&1` | `make reproduce` 退出码 0，且复算指标与 reports/metrics.json 一致（1e-6） | `qa/evidence/S7/S7-04.log` |

### 段8（200%）生产级：一键 demo、压测 QPS、验收报告、已知限制 ≥5

| 条目ID | 验收项 | 判定命令或方法 | 通过阈值 | 证据文件路径 |
|---|---|---|---|---|
| S8-01 | `make demo` 一键拉起端到端演示 | `mkdir -p qa/evidence/S8; printf '%s' 'mkdir -p qa/evidence/S8; make demo > qa/evidence/S8/S8-01.log 2>&1 & sleep 30; curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/score -X POST -F image=@assets/sample.png >> qa/evidence/S8/S8-01.log; kill %1; tail -1 qa/evidence/S8/S8-01.log' > qa/evidence/S8/S8-01.sh && sh qa/evidence/S8/S8-01.sh \| tee -a qa/evidence/S8/S8-01.log; grep -q "200" qa/evidence/S8/S8-01.log` | 单命令起全链路，`/score` 返回 200；`&`/`kill %1` 仅 sh 语法，必须 sh 包裹执行 | `qa/evidence/S8/S8-01.log` |
| S8-02 | 压测吞吐 QPS 达标（locust 2.47 已装） | `locust -f tests/load/locustfile.py --headless -u 8 -t 30s --csv qa/evidence/S8/qps > qa/evidence/S8/S8-02.log 2>&1; python -c "import csv;r=list(csv.DictReader(open('qa/evidence/S8/qps_stats.csv')))[-1];q=float(r['Requests/s']);f=int(r['Failure Count']);print('qps=',q,'fail=',f);assert q>=5 and f==0,(q,f)" 2>&1 \| tee -a qa/evidence/S8/S8-02.log` | QPS ≥5 且失败请求 =0（单实例 CPU 默认阈值，可由 00_PRD 对齐） | `qa/evidence/S8/S8-02.log`、`qa/evidence/S8/qps_stats.csv` |
| S8-03 | 最终验收报告存在且结构完整 | `test -f qa/reports/FINAL_ACCEPTANCE.md && grep -q "## 验收结论" qa/reports/FINAL_ACCEPTANCE.md && grep -q "## 已知限制" qa/reports/FINAL_ACCEPTANCE.md && grep -q "## 遗留风险" qa/reports/FINAL_ACCEPTANCE.md && echo REPORT-OK \| tee qa/evidence/S8/S8-03.log` | 3 个必要小节齐全 | `qa/evidence/S8/S8-03.log` |
| S8-04 | 已知限制 ≥5 条 | `python -c "import re,sys;t=open('qa/reports/FINAL_ACCEPTANCE.md',encoding='utf-8').read();sec=re.search(r'## 已知限制(.+?)(?=\n## \|\Z)',t,re.S).group(1);items=[l for l in sec.splitlines() if re.match(r'\s*([-*]\|\d+\.)\s+\S',l)];print('limitations=',len(items));sys.exit(0 if len(items)>=5 else 1)" 2>&1 \| tee qa/evidence/S8/S8-04.log` | 限制条数 ≥5 | `qa/evidence/S8/S8-04.log` |
| S8-05 | [人工复核] demo 端到端人验。步骤：①`make demo` 后按 README 打开演示页面/接口；②上传 1 张自有图片；③确认返回总分+四维并展示合理；④确认重启容器后功能仍正常；⑤逐条记录结论。 | 人工复核步骤如左 | 5 步全部通过 | `qa/evidence/S8/S8-05.md` |

### 条目统计

| 段 | 条目数 | 其中 [人工复核] |
|---|---|---|
| 段0 | 5 | 1 |
| 段1 | 5 | 0 |
| 段2 | 8 | 1 |
| 段3 | 6 | 0 |
| 段4 | 4 | 1 |
| 段5 | 5 | 0 |
| 段6 | 6 | 1 |
| 段7 | 4 | 0 |
| 段8 | 5 | 1 |
| **合计** | **48** | **5** |

统计口径：`grep -cE '^\| S[0-9]-[0-9]+ \|' docs/08_ACCEPTANCE.md` = 48（≥40 ✅）；每段 ≥3（✅）。

---

## QA 报告模板（每批固定三步，独立成节）

QA（独立审查方）对每个集成批次执行以下三步，缺一不可；实现子智能体（DATA/MODEL/SERVE/ARCH）不得自审。
黑盒验证**只按本文件“验收标准”逐条执行命令，不看实现代码**。

1. **①黑盒验证**：只按契约和门禁命令跑，不看实现代码，记录通过/失败清单 + 证据命令与输出摘录；条目 ID 必须引用本文件（如 `S3-03`）。
2. **②白盒审查**：读实现代码找契约未覆盖的边界（空输入/超大输入/并发/异常路径），**必须找出至少一个具体问题**；找不到就写：
   `未发现缺陷，但以下 N 项需人工复核：[具体项]`。
3. **③回归验证**：上一段已通过的测试本段是否仍通过，逐条列出并给通过/失败。

输出格式（粘贴以下模板，`{批次号}` 形如 `S3` 或 `S3-S4`）：

```
<qa_report batch="{批次号}">
  blackbox: 逐条门禁，通过/失败 + 证据命令与输出摘录
  whitebox: 至少一个具体问题，或“三项人工复核”+具体项
  regression: 上一段测试清单，逐条通过/失败
  verdict: PASS / FAIL / PASS_WITH_RISK（附风险项）
</qa_report>
```

- `FAIL` 必须附**返工工单编号**（格式 `RW-<批次>-<序号>`，如 `RW-S3-01`）并退回对应子智能体；
  `PASS_WITH_RISK` 必须列出风险项与残留影响；证据一律落盘 `qa/evidence/`。
