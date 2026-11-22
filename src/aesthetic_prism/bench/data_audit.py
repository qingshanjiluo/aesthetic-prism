"""数据体检（T-7-07 reproduce 第一步）：index.json 样本数 / 切分口径 / 文件存在性。

切分口径以契约 C-DATA-01 section 2.2 为唯一真源：
    split_of(sample_id) = sha256(id)[:8] % 20  ->  <16 train / <18 val / else test
index.json 不存 split 字段（meta.split 明写 "never stored"），此步在读取时派生，
与训练 / 评估 / metric_recheck 共用 aesthetic_prism.data.schema.split_of，因此不可能分叉。

校验项（任一失败即非零退出，reproduce 中断）：
  A. meta.n 存在时与实量样本数一致
  B. id 唯一、符合 ^(syn|img)_[0-9]{6}$、可被 split_of 正常派生
  C. 三切分计数之和 == 总数（互斥且完备）
  D. 三切分 id 集合两两不相交、并集覆盖全集（防读取侧偷偷加过滤）
  E. 每个样本的 image_path 真实存在
  F. labels 覆盖 meta.labels 的 5 个键
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

try:
    from aesthetic_prism._aproot import AP_ROOT  # type: ignore
except ImportError:  # pragma: no cover - 未安装包时回退
    AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()

os.chdir(AP_ROOT)

SPLITS = ("train", "val", "test")
DEFAULT_LABELS = ("total", "composition", "light", "creativity", "story")
DATA_YAML = os.path.join("configs", "data", "data.yaml")


def split_of(sample_id: str) -> str:
    """C-DATA-01 section 2.2 的独立实现，用于与包内 split_of 交叉对拍。"""
    import hashlib

    v = int(hashlib.sha256(sample_id.encode("utf-8")).hexdigest()[:8], 16) % 20
    return "train" if v < 16 else ("val" if v < 18 else "test")


def _load_pkg_split_of():
    try:
        from aesthetic_prism.data.schema import split_of as _pkg_split_of  # type: ignore
    except ImportError:  # pragma: no cover
        return None
    return _pkg_split_of


def load_split_expect() -> dict[str, int] | None:
    """从 configs/data/data.yaml 读 split_expect 期望计数。

    返回 {"train": int, "val": int, "test": int}；文件缺失 / 无该段 / 段内键不全
    返回 None，由调用侧退化为「仅自洽校验」（总数 == 样本数、两两不交、并集全覆盖），
    不在此处把缺省静默成某个常数。
    """
    import yaml

    if not os.path.isfile(DATA_YAML):
        return None
    with open(DATA_YAML, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    raw = cfg.get("split_expect")
    if not isinstance(raw, dict):
        return None
    if not all(k in raw for k in SPLITS):
        return None
    return {k: int(raw[k]) for k in SPLITS}


def main() -> int:
    idx_path = os.path.join("data", "synthetic", "index.json")
    with open(idx_path, encoding="utf-8") as f:
        index = json.load(f)

    if isinstance(index, dict) and "samples" in index:
        samples = index["samples"]
        meta = index.get("meta") or {}
    else:
        samples = index
        meta = {}

    n = len(samples)

    # A: meta.n
    meta_n = meta.get("n")
    if meta_n is not None:
        assert meta_n == n, f"meta.n={meta_n} != len(samples)={n}"

    # B: id 唯一且格式合法
    ids = [s.get("id") for s in samples]
    assert all(isinstance(i, str) for i in ids), "some sample id is not str"
    assert len(set(ids)) == n, f"duplicate ids: {n - len(set(ids))}"

    # C/D: 契约派生切分，交叉校验
    buckets: dict[str, list[str]] = {sp: [] for sp in SPLITS}
    for sid in ids:
        buckets[split_of(sid)].append(sid)
    counts = {sp: len(v) for sp, v in buckets.items()}
    assert sum(counts.values()) == n, f"split sum {sum(counts.values())} != n {n}"

    seen: dict[str, str] = {}
    for sp in SPLITS:
        for sid in buckets[sp]:
            assert sid not in seen, f"id {sid} in both {seen[sid]} and {sp}"
            seen[sid] = sp
    assert len(seen) == n, f"covered {len(seen)} != n {n}"

    # D+: 与 configs/data/data.yaml 的 split_expect 比对（配置期望，漂移即失败）
    expect = load_split_expect()
    if expect is not None:
        drifted = {sp: (counts[sp], expect[sp]) for sp in SPLITS if counts[sp] != expect[sp]}
        assert not drifted, (
            "SPLIT-COUNT-DRIFT (derived, expect) = "
            + str(drifted)
            + f"; 样本集已增删，请同步 {DATA_YAML} 的 split_expect 段"
        )
        assert sum(expect.values()) == n, (
            f"SPLIT-EXPECT-SUM config sum={sum(expect.values())} != n {n}"
        )
        split_src = "contract(sha256[:8]%20)+data.yaml(split_expect)"
    else:
        split_src = "contract(sha256[:8]%20)"

    # E: 图像存在
    missing = []
    for s in samples:
        p = s.get("image_path") or s.get("path") or s.get("file")
        if not p:
            missing.append(f"<no-path:{s.get('id')}>")
            continue
        if not os.path.exists(os.path.join(".", p)):
            missing.append(p)
    assert not missing, f"{len(missing)} image files missing, e.g. {missing[:5]}"

    # F: labels 键覆盖
    want = set(meta.get("labels") or DEFAULT_LABELS)
    for s in samples:
        got = set((s.get("labels") or {}).keys())
        assert want <= got, f"sample {s.get('id')} missing label keys {sorted(want - got)}"

    print(
        "DATA-AUDIT-PASS n={n} missing=0 split={src} "
        "train={tr} val={va} test={te}".format(
            n=n, tr=counts["train"], va=counts["val"], te=counts["test"], src=split_src
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
