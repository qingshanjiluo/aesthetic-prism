import re, ast, pathlib, sys
t = pathlib.Path('docs/08_ACCEPTANCE.md').read_text(encoding='utf-8')
focus = ['S0-03', 'S1-03', 'S2-03', 'S3-03', 'S4-01', 'S6-03', 'S6-06', 'S8-02']
ok = fail = three = 0
for fid in focus:
    rows = [l for l in t.splitlines() if re.match(r'^\| ' + fid + r' \|', l)]
    if not rows:
        print(fid, 'ROW_MISSING'); fail += 1; continue
    row = rows[0].replace('\\|', '\x01')          # markdown表格转义管道 -> 哨兵
    cells = row.split('|')
    cell = cells[3] if len(cells) > 3 else ''
    srcs = re.findall(r'python -c "((?:[^"\\]|\\.)*)"', cell)
    if not srcs:
        print(fid, 'NO_PYTHON_SRC'); fail += 1; continue
    for i, s in enumerate(srcs):
        src = s.replace('\\"', '"').replace('\x01', '|')
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            fail += 1
            print(fid, i, 'SYNTAX_FAIL', e.msg)
            continue
        ok += 1
        bad3 = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Assert):
                # 三参 assert 病：msg 位置放了 BinOp/Call（如 float(rate)>=0.70）而非单表达式
                m = n.msg
                if isinstance(m, (ast.BinOp, ast.Compare, ast.Call, ast.BoolOp)):
                    bad3.append(type(m).__name__)
        if bad3:
            three += 1
            print(fid, i, 'THREE_ARG_SUSPECT', bad3)
        else:
            print(fid, i, 'OK')
print('ast_ok=', ok, 'ast_fail=', fail, 'three_arg_suspect=', three)
sys.exit(0 if fail == 0 and three == 0 else 1)
