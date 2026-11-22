# q2 白盒实测取证：①8 行三参 assert 真验 ②sessions 三 rater 独立性实测 ③label_quality 生成器溯源 ④gold 四维题机制 grep
mkdir -p qa/evidence/S2
echo '=== A) 8 行三参 assert 真验（按条目 ID 抽命令列 python -c 体逐个 ast.parse）==='
python - <<'PY'
import re, ast, pathlib, sys
t = pathlib.Path('docs/08_ACCEPTANCE.md').read_text(encoding='utf-8')
focus = ['S0-03','S1-03','S2-03','S3-03','S4-01','S6-03','S6-06','S8-02']
ok = fail = 0
for fid in focus:
    rows = [l for l in t.splitlines() if re.match(r'^\| ' + fid + r' \|', l)]
    assert rows, fid
    row = rows[0].replace('\\|', '\x00')          # 表格转义管道还原
    cells = re.split(r'(?<!\\)\|', row)
    cell = cells[3] if len(cells) > 3 else ''
    srcs = re.findall(r'python -c "((?:[^"\\]|\\.)*)"', cell)
    for i, s in enumerate(srcs):
        src = s.replace('\\"', '"').replace("\\'", "'")
        try:
            ast.parse(src); ok += 1; verdict = 'OK'
        except SyntaxError as e:
            fail += 1; verdict = f'FAIL line{e.lineno} {e.msg}'
        # 三参 assert 检测（真 AST 级）
        tree = ast.parse('pass')
        try:
            tr = ast.parse(src)
            threes = [n for n in ast.walk(tr) if isinstance(n, ast.Assert) and len(n.msg.args) if isinstance(n.msg, ast.Tuple) and len(n.msg.elts) > 1] if False else []
            tr2 = ast.parse(src)
            for n in ast.walk(tr2):
                if isinstance(n, ast.Assert) and isinstance(n.msg, ast.Tuple):
                    verdict += '|THREE-ARG-MSG-TUPLE'
        except Exception:
            pass
        print(f'  {fid}[{i}] {verdict} :: {src[:70]}...')
print('ast_ok=', ok, 'ast_fail=', fail)
PY
echo "A_EXIT=$?"

echo '=== B) sessions 三 rater 同题独立性实测（种子 r01/r02/r03: 分值应抖动非复制）==='
python - <<'PY'
import json, glob, collections, itertools, statistics as st
files = sorted(glob.glob('data/annotations/sessions/*/rd_001.jsonl'))
print('session_files=', files)
by_sid = collections.defaultdict(dict)
for f in files:
    for line in open(f, encoding='utf-8'):
        if not line.strip(): continue
        r = json.loads(line)
        by_sid.setdefault(r['sample_id'], {})[r['rater_id']] = r['scores']
identical_pairs = 0; total_pairs = 0; diffs = []
for sid, per in by_sid.items():
    if len(per) < 3: continue
    for a, b in itertools.combinations(sorted(per), 2):
        for k in ('composition','light','creativity','story'):
            total_pairs += 1
            d = abs(per[a][k] - per[b][k]); diffs.append(d)
            if d == 0.0: identical_pairs += 1
print('samples=', len(by_sid), 'pairs=', total_pairs, 'identical_pairs=', identical_pairs,
      'diff_min=', min(diffs), 'diff_mean=', round(st.mean(diffs), 2), 'diff_max=', max(diffs))
print('VERDICT_SEEDS_INDEP=', identical_pairs == 0 and min(diffs) > 0)
PY
echo "B_EXIT=$?"

echo '=== C) label_quality.json 生成器溯源 ==='
grep -rn 'label_quality' labeling/ scripts/ src/ tests/ Makefile 2>/dev/null | head -10 || echo 'NOT_FOUND_in_code_dirs'

echo '=== D) 四维黄金题机制（04 s2 要求 >=2 道）grep annotate ==='
grep -n 'gold' labeling/annotate.py | head -20
echo '--- rate 记录是否带 is_gold ---'
grep -cn '"is_gold": True' labeling/annotate.py || true
grep -n 'kind.*rate' labeling/annotate.py | head -3

echo '=== E) 聚合 w_r 加权（04 s3.1/3.2）grep annotate ==='
grep -n 'w_r\|q_r\|acc_r\|mad\|downweight' labeling/annotate.py || echo 'NO_WR_IN_AGGREGATE'
grep -n 'sum(v - med' labeling/annotate.py

echo '=== F) split 单实现（全树 split_of 定义点）==='
grep -rn 'def split_of\|sha256.*% 20\|%20' src/ labeling/ tests/ --include='*.py' | grep -v '__pycache__' | head -10
