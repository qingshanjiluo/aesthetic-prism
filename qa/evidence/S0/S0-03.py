import re, pathlib, sys
prd = pathlib.Path('docs/00_PRD.md').read_text(encoding='utf-8')
m = re.search(r'##\s*契约索引(.+?)(?=\n## |\Z)', prd, re.S)
files = re.findall(r'docs/[\w\-/]+\.md', m.group(1)) if m else []
files = ['docs/00_PRD.md'] + files
assert len(files) >= 3, files
missing = [f for f in files[:3] if not pathlib.Path(f).exists() or not all(k in pathlib.Path(f).read_text(encoding='utf-8') for k in ('输入', '输出', '错误语义', '验收'))]
print('indexed=', files, 'checked=', files[:3], 'missing=', missing)
sys.exit(1 if missing else 0)
