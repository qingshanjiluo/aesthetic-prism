import glob, os, sys

checks = [
    ('data/synthetic/index.json', 'T-2-01 index'),
    ('data/annotations', 'T-2-01 annotations dir'),
    ('data/raw/SOURCES.csv', 'T-2-04 SOURCES'),
    ('reports/data_bias.json', 'T-2-04 data_bias'),
    ('reports/label_quality.json', 'T-2-06 label_quality'),
    ('data/annotations/pairs.jsonl', '04 s1.3 pairs'),
    ('data/annotations/gold.jsonl', '04 s2 gold'),
    ('data/annotations/schema.json', '08 S2-03 schema'),
    ('data/exports', '02 data/exports jsonl dir'),
]
missing = 0
for p, name in checks:
    ex = os.path.exists(p)
    print(('EXISTS ' if ex else 'MISSING ') + name + ' -> ' + p)
    if not ex:
        missing += 1
exps = sorted(glob.glob('data/annotations/export_*.json'))
print('export_files=', len(exps), exps)
jsonls = sorted(glob.glob('data/exports/*.jsonl'))
print('exports_jsonl=', len(jsonls), jsonls)
sys.exit(1 if missing else 0)
