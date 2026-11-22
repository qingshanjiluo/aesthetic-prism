# W-2-03 gate：S2-06 语法双验 + 命中计数 + S2-05 原样 + S0-04 重跑 + 回读
mkdir -p qa/evidence/S2 qa/evidence/S0
python - <<'PY'
import re, ast, subprocess, sys, pathlib, hashlib, io
t = pathlib.Path('docs/08_ACCEPTANCE.md').read_text(encoding='utf-8')
rows = re.findall(r'^\| S2-06 \|.*$', t, re.M)
print('id_row_count=', len(rows))
assert len(rows) == 1, rows
row = rows[0]
cells = re.split(r'(?<!\\)\|', row)             # 只按未转义 | 切（命令内 \| 保留）
assert len(cells) >= 6, len(cells)
cell = cells[3].strip()
assert cell.startswith('`') and cell.endswith('`'), cell[:60]
inner = cell[1:-1].replace('\\|', '|')          # 表格转义还原
open('qa/evidence/S2/S2-06_cmd.sh', 'w', encoding='utf-8', newline='\n').write(inner + '\n')
p = subprocess.run(['sh', '-n', 'qa/evidence/S2/S2-06_cmd.sh'], capture_output=True, text=True, errors='replace')
print('sh -n ->', 'OK' if p.returncode == 0 else 'FAIL', (p.stderr.strip() or '')[:120])
m = re.search(r"printf '%s' '(.*)' > qa/evidence/S2/S2-06\.py", inner, re.S)
assert m, 'printf payload not found'
payload = m.group(1)
assert "'" not in payload, 'payload contains single quote (breaks printf)'
try:
    ast.parse(payload)
    print('payload ast.parse -> OK', 'payload_bytes=', len(payload.encode('utf-8')))
except SyntaxError as e:
    print('payload ast.parse -> FAIL', e); sys.exit(1)
open('qa/evidence/S2/S2-06_payload.py', 'w', encoding='utf-8', newline='\n').write(payload + '\n')
r = subprocess.run([sys.executable, '-m', 'py_compile', 'qa/evidence/S2/S2-06_payload.py'], capture_output=True, text=True, errors='replace')
print('py_compile ->', 'OK' if r.returncode == 0 else 'FAIL', (r.stderr.strip() or '')[:120])
print('S2-06 id grep =', len(re.findall(r'^\| S2-06 \|', t, re.M)), '; S2-06 mentions =', t.count('S2-06'))
s205 = [l for l in re.findall(r'^\| S2-05 \|.*$', t, re.M)]
orig5 = '| S2-05 | [人工复核] 标注质量抽查。步骤：①从全部导出文件的标注条目中随机抽 10 条；②打开原图人工核对四维标注值是否与画面观感相符（偏差 >30 分记为不合格）；③记录抽样清单与合格数。 | 人工复核步骤如左 | 合格 ≥9/10 | `qa/evidence/S2/S2-05.md` |'
print('S2-05 intact =', s205 == [orig5])
ids = re.findall(r'^\| (S\d-\d+) \|', t, re.M)
print('all_ids =', len(ids), 'unique =', len(set(ids)))
bad = re.findall(r'[▶▷■￼�\uFFFD]', t)
print('badchars =', bad, 'bytes =', len(t.encode('utf-8')))
sys.exit(0 if p.returncode == 0 and not bad and len(set(ids)) == len(ids) == 47 else 1)
PY
echo "GATE1_EXIT=$?"
echo '--- S0-04 rerun ---'
python qa/evidence/S0/S0-04.py 2>&1 | tee qa/evidence/S0/S0-04.log
echo "S04_EXIT=$?"
echo '--- S2-06 mentions ---'
grep -c 'S2-06' docs/08_ACCEPTANCE.md
echo '--- 08 bytes ---'
wc -c < docs/08_ACCEPTANCE.md
