"""Thin shim so the 08 S3-03 verbatim command works from the project root:

    python -m src.train --steps 20 --loss-log <path>

`src` resolves as a namespace package (no src/__init__.py needed); this file
only injects the src/ directory onto sys.path and delegates to the real CLI in
aesthetic_prism.train. Implementation lives under src/aesthetic_prism/train/
per 01_ARCH section 5 tree; do not add logic here (keep the shim thin).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent  # <root>/src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aesthetic_prism.train import main  # noqa: E402  (shim: sys.path injected above on purpose)

if __name__ == "__main__":
    raise SystemExit(main())
