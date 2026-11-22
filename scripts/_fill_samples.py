# 补齐合成样本到 >=200（复用 synthetic.generate，跳过已有 id）
import json
import pathlib
import sys

ROOT = pathlib.Path(".").resolve()
sys.path.insert(0, str(ROOT / "src"))

from aesthetic_prism.data import synthetic as syn

out_dir = ROOT / "data" / "synthetic"
out_dir.mkdir(parents=True, exist_ok=True)

# 读已有 id
existing = set()
idx_file = out_dir / "index.json"
if idx_file.is_file():
    try:
        idx = json.loads(idx_file.read_text(encoding="utf-8"))
        for s in idx.get("samples", []):
            existing.add(s["id"])
    except (OSError, ValueError):
        pass

# 生成到 200 个
TARGET = 200
new_samples = []
nxt = 1
while len(new_samples) + len(existing) < TARGET and nxt <= 1000000:
    sid = f"syn_{nxt:06d}"
    nxt += 1
    if sid in existing:
        continue
    rec = syn.generate(syn.SEED, sid, out_dir)
    new_samples.append(rec)

if new_samples:
    if idx_file.is_file():
        try:
            idx = json.loads(idx_file.read_text(encoding="utf-8"))
            idx["samples"] = idx.get("samples", []) + new_samples
            idx["meta"]["n"] = len(idx["samples"])
        except (OSError, ValueError):
            idx = {"meta": {"n": len(new_samples), "seed": syn.SEED, "gen_version": "rw-s2-03", "labels": list(syn.KEYS)}, "samples": new_samples}
    else:
        idx = {"meta": {"n": len(new_samples), "seed": syn.SEED, "gen_version": "rw-s2-03", "labels": list(syn.KEYS)}, "samples": new_samples}
    idx_file.write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

pngs = list(out_dir.glob("*.png"))
print(f"new_generated={len(new_samples)} total_index={len(idx['samples'])} png_files={len(pngs)}")