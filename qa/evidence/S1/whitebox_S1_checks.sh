# 段1 白盒机械核验：W2 语法级 + S2-07/08 互核 + configs + make + 契约接线点
echo '=== W2: 07_PLAN 任务行 sh -c 内容 sh -n 语法级（只验语法不执行）==='
python - <<'PY'
import re, subprocess, pathlib, sys
t = pathlib.Path('docs/07_PLAN.md').read_text(encoding='utf-8')
rows = [l for l in t.splitlines() if re.match(r'^\| T-[0-8]-\d\d \|', l)]
print('task_rows=', len(rows))
fails = []
for l in rows:
    tid = l.split('|')[1].strip()
    m = re.search(r'sh -c "(.*)"', l)
    if not m:
        fails.append((tid, 'NO_sh_c_row', l[:60])); continue
    inner = m.group(1)
    p = subprocess.run(['sh', '-n', '-c', inner], capture_output=True, text=True, errors='replace')
    if p.returncode != 0:
        fails.append((tid, (p.stderr.strip().splitlines() or [''])[0][:90], inner[:70]))
print('syntax_FAIL=', len(fails))
for f in fails: print('  FAIL', f[0], '|', f[1], '|', f[2])
# python -c 体能否 parse（能抽出 python -c <body> 的行）
pfails = []
for l in rows:
    tid = l.split('|')[1].strip()
    m = re.search(r'sh -c "(.*)"', l)
    if not m: continue
    inner = m.group(1)
    pm = re.search(r'python -c ("?)(.+)\1?$', inner)
    if pm:
        body = pm.group(2)
        # 去掉引号包裹情形
        if body.startswith('"') and body.endswith('"'): body = body[1:-1]
        r = subprocess.run([sys.executable, '-c', 'import ast,sys;ast.parse(sys.argv[1])', body], capture_output=True, text=True, errors='replace')
        if r.returncode != 0:
            pfails.append((tid, body[:80]))
print('python_ast_FAIL=', len(pfails))
for f in pfails: print('  PYFAIL', f[0], '|', f[1])
sys.exit(0 if not fails else 1)
PY
echo "W2_EXIT=$?"
echo '=== S2-07/08 引用互核 ==='
grep -n 'S2-07\|S2-08' docs/07_PLAN.md | head -8
grep -n '^| S2-07\|^| S2-08' docs/08_ACCEPTANCE.md | sed 's/\(.\{160\}\).*/\1.../'
echo '--- 07 引用的证据路径 ---'
grep -o 'qa/evidence/S2/S2-0[78][^ |`]*' docs/07_PLAN.md | sort -u
grep -o 'qa/evidence/S2/S2-0[78][^ |`]*' docs/08_ACCEPTANCE.md | sort -u
echo '--- S 条目引用总数 vs 08 实有 ---'
grep -o 'S[0-8]-[0-9][0-9]' docs/07_PLAN.md | sort -u > qa/evidence/S1/plan_ids.txt
grep -oE '^\| S[0-9]-[0-9]+' docs/08_ACCEPTANCE.md | tr -d '| ' | sort -u > qa/evidence/S1/acc_ids.txt
echo "plan_unique=$(wc -l < qa/evidence/S1/plan_ids.txt) acc_total=$(wc -l < qa/evidence/S1/acc_ids.txt)"
echo 'in_acc_not_in_plan:'; comm -13 qa/evidence/S1/plan_ids.txt qa/evidence/S1/acc_ids.txt | tr '\n' ' '; echo
echo 'in_plan_not_in_acc:'; comm -23 qa/evidence/S1/plan_ids.txt qa/evidence/S1/acc_ids.txt | tr '\n' ' '; echo
echo '=== configs yaml 可解析 ==='
python -c "import yaml,glob;fs=glob.glob('configs/**/*.yaml',recursive=True);[yaml.safe_load(open(f,encoding='utf-8')) for f in fs];print('yaml_ok',len(fs),fs)"
echo "yaml_exit=$?"
echo '=== make 七目标语法（-n 干跑）==='
for tgt in dev test lint typecheck coverage demo reproduce; do
  make -n $tgt > /dev/null 2>qa/evidence/S1/make_$tgt.err; echo "make -n $tgt => $?"
done
echo '=== 契约接线点 ==='
echo "-- SCORE_TIMEOUT_MS 使用点:"; grep -rn 'SCORE_TIMEOUT_MS' src/ | grep -v 'import' || echo NONE
echo "-- fail_after/wait_for 超时包裹:"; grep -rn 'fail_after\|wait_for\|move_on_after' src/ || echo NONE
echo "-- _CachedRequest/wrapped_receive 定义:"; grep -rn 'class _CachedRequest\|wrapped_receive *=' src/ || echo NONE
echo "-- 前端轮询周期契约对照(05_DEPLOY 应 5s):"; grep -n 'setInterval(pollHealth' frontend/app.js; grep -n '每 5 s\|每5秒\|5 s 轮询' docs/05_DEPLOY.md || grep -n '5 s' docs/05_DEPLOY.md | head -2
echo '=== 六档映射表齐备（service 类 → 状态码）==='
grep -nE 'super\(\).__init__\((400|404|405|413|415|429|500)' src/aesthetic_prism/serve/service.py
echo '=== 端口清理 ==='
echo done
