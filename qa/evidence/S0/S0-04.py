import re, sys
t = open("docs/08_ACCEPTANCE.md", encoding="utf-8").read()
ids = re.findall(r"^\| (S\d-\d+) \|", t, re.M)
segs = {s: sum(1 for i in ids if i.startswith("S" + s + "-")) for s in "012345678"}
bad = re.findall(r"[▶▷■￼�\uFFFD]", t)
manual = len(re.findall(r"^\| S\d-\d+ \| \[人工复核\]", t, re.M))
checks = {
    "p50_150": "p50_ms']<=150" in t,
    "p95_500": "<=500,d" in t,
    "pa_068": "pa>=0.68" in t,
    "mae_row": "| S6-06 |" in t,
    "n_test_20": "int(n)>=20" in t,
    "no_or_len_fallback": "or len(x)" not in t,
    "s2_06": "| S2-06 |" in t,
    "s2_06_evidence": "qa/evidence/S2/S2-06.log" in t,
    "s2_06_split_algo": "sha256" in t and ("%20" in t or "% 20" in t),
    "s2_07": "| S2-07 |" in t,
    "s2_08": "| S2-08 |" in t,
    "stats_seg2_8": "| 段2 | 8 | 1 |" in t,
    "stats_seg6_6": "| 段6 | 6 | 1 |" in t,
    "total_48": "| **合计** | **48** | **5** |" in t,
    "stats_seg3_6": "| 段3 | 6 | 0 |" in t,
    "s3_06_row": "| S3-06 |" in t,
    "old_100_300_gone": "P50≤100ms、P95≤300ms" not in t,
    "old_pa_070_gone": "pairwise accuracy ≥0.70" not in t,
    "heading_literal": "## 验收标准\n" in t,
    "sh_c": "sh -c" in t or "S2-06" in t,
    "s701_ge4": 'test "$k" -ge 4' in t,
}
print("bytes=", len(t.encode("utf-8")), "lines=", t.count("\n") + (0 if t.endswith("\n") else 1))
print("badchars=", bad)
print("total", len(ids), segs, "manual=", manual)
for k, v in checks.items():
    print(("OK " if v else "FAIL ") + k)
ok = (
    len(ids) >= 40
    and all(v >= 3 for v in segs.values())
    and len(ids) == 48
    and segs["2"] == 8
    and segs["3"] == 6
    and not bad
    and all(checks.values())
)
print("SELF-CHECK", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
