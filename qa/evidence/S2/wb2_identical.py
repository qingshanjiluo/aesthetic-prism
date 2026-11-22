import json, glob, collections, itertools, statistics as st, sys

files = sorted(glob.glob('data/annotations/sessions/*/rd_001.jsonl'))
print('session_files=', len(files), files)
by = collections.defaultdict(dict)
for f in files:
    for line in open(f, encoding='utf-8'):
        if line.strip():
            r = json.loads(line)
            by.setdefault(r['sample_id'], {})[r['rater_id']] = r['scores']

identical = []
diffs = []
for sid, per in sorted(by.items()):
    for a, b in itertools.combinations(sorted(per), 2):
        for k in ('composition', 'light', 'creativity', 'story'):
            d = abs(per[a][k] - per[b][k])
            diffs.append(d)
            if d == 0.0:
                identical.append((sid, a, b, k, per[a][k]))
print('samples=', len(by), 'pairs_diff=', len(diffs),
      'diff_min=', min(diffs), 'diff_mean=', round(st.mean(diffs), 2), 'diff_max=', max(diffs))
for rec in identical:
    clip = 'CLIP(0/100)' if rec[4] in (0.0, 100.0) else 'RAW_EQUAL'
    print('identical:', rec, clip)
n_raw = sum(1 for rec in identical if rec[4] not in (0.0, 100.0))
print('identical_total=', len(identical), 'raw_equal=', n_raw)
print('VERDICT_SEEDS_INDEP=', n_raw == 0 and min(diffs) > 0)
sys.exit(0)
