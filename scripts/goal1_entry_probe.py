from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "aesthetic_prism"


def show(path: pathlib.Path) -> None:
    print("=" * 70)
    print(path.relative_to(ROOT))
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print("  unreadable:", exc)
        return
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"add_argument|def main|ArgumentParser|__main__|description=", line):
            print(f"{i:>4}: {line.strip()}")


def main() -> int:
    targets = [
        SRC / "score.py",
        SRC / "distill.py",
        SRC / "serve" / "service.py",
        SRC / "train" / "cli.py",
        SRC / "data" / "synthetic.py",
        SRC / "export" / "onnx_export.py",
    ]
    for t in targets:
        if t.exists():
            show(t)
        else:
            for hit in SRC.rglob(t.name):
                show(hit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
