# 片2 机械核验脚本：W2 语法级 + S2-07/08 互核 + configs/make
mkdir -p qa/evidence/S1
echo '=== W2: 07_PLAN 任务行 sh -c 语法级（只验语法不执行）==='
python - > qa/evidence/S1/W2_syntax.log 2>&1 <<'PY'
import re, subprocess, pathlib, sys
t = pathlib.Path('docs/07_PLAN.md').read_text(encoding='utf-8')
rows = [l for l in t.splitlines() if re.match(r'^\| T-[0-8]-\d\d \|', l)]
print('task_rows=', len(rows))
ok = 0; fails = []
for idx, l in enumerate(rows, 1):
    tid = l.split('|')[1].strip()
    m = re.search(r'sh -c "(.*)"', l)
    if not m:
        fails.append((idx, tid, 'NO_sh_c_row', '')); continue
    inner = m.group(1)
    p = subprocess.run(['sh', '-n', '-c', inner], capture_output=True, text=True, errors='replace')
    if p.returncode == 0: ok += 1
    else:
        err = (p.stderr.strip().splitlines() or [''])[0][:100]
        fails.append((idx, tid, err, inner[:70]))
print('syntax_ok=', ok, 'syntax_fail=', len(fails))
for f in fails: print('  FAIL', f[0], f[1], '|', f[2], '|', f[3])
print('--- focus: e7 5 rows + T-0-01/02 ---')
for focus in ('T-2-01','T-2-03','T-2-05','T-6-01','T-6-02','T-0-01','T-0-02'):
    row = next((l for l in rows if l.split('|')[1].strip() == focus), None)
    if row is None: print('  FOCUS', focus, 'MISSING'); continue
    m = re.search(r'sh -c "(.*)"', row)
    if not m: print('  FOCUS', focus, 'NO_CMD'); continue
    p = subprocess.run(['sh','-n','-c',m.group(1)], capture_output=True, text=True, errors='replace')
    print('  FOCUS', focus, 'syntax=', 'OK' if p.returncode == 0 else 'FAIL')
sys.exit(0 if not fails else 1)
PY
echo "W2_EXIT=$?"
cat qa/evidence/S1/W2_syntax.log
echo '=== S2-07/08 引用互核 ==='
grep -n 'S2-07\|S2-08' docs/07_PLAN.md | cut -c1-190
grep -n '^| S2-0[78] ' docs/08_ACCEPTANCE.md | cut -c1-150
grep -o 'qa/evidence/S2/S2-0[78][A-Za-z0-9._]*' docs/07_PLAN.md | sort -u > qa/evidence/S1/paths_plan.txt
grep -o 'qa/evidence/S2/S2-0[78][A-Za-z0-9._]*' docs/08_ACCEPTANCE.md | sort -u > qa/evidence/S1/paths_acc.txt
diff qa/evidence/S1/paths_plan.txt qa/evidence/S1/paths_acc.txt && echo PATHS-IDENTICAL || echo PATHS-DIFF
grep -o 'S[0-8]-[0-9][0-9]' docs/07_PLAN.md | sort -u > qa/evidence/S1/plan_ids.txt
grep -oE '^\| S[0-9]-[0-9]+' docs/08_ACCEPTANCE.md | tr -d '| ' | sort -u > qa/evidence/S1/acc_ids.txt
echo "plan_unique=$(wc -l < qa/evidence/S1/plan_ids.txt) acc_total=$(wc -l < qa/evidence/S1/acc_ids.txt)"
echo -n 'in_acc_not_in_plan: '; comm -13 qa/evidence/S1/plan_ids.txt qa/evidence/S1/acc_ids.txt | tr '\n' ' '; echo
echo -n 'in_plan_not_in_acc: '; comm -23 qa/evidence/S1/plan_ids.txt qa/evidence/S1/acc_ids.txt | tr '\n' ' '; echo
echo '=== configs yaml ==='
python -c "import yaml,glob;fs=sorted(glob.glob('configs/**/*.yaml',recursive=True));[yaml.safe_load(open(f,encoding='utf-8')) for f in fs];print('yaml_ok',len(fs),fs)"
echo "yaml_exit=$?"
echo '=== make 七目标 ==='
for tgt in dev test lint typecheck coverage demo reproduce; do
  make -n $tgt > /dev/null 2>qa/evidence/S1/make_$tgt.err; echo "make -n $tgt => $?"
done
echo '=== 前端轮询 vs 05_DEPLOY ==='
grep -n 'setInterval(pollHealth' frontend/app.js
grep -n '轮询' docs/05_DEPLOY.md | head -3
echo '=== SCORE_TIMEOUT_MS 终核 ==='
grep -rn 'SCORE_TIMEOUT_MS' src/ || echo NONE
grep -rn 'fail_after\|wait_for\|move_on_after' src/ || echo 'no-timeout-wrapper'
echo '=== 端口探查 ==='
netstat -ano | grep LISTENING | grep ':8000 ' || echo '8000 FREE'
