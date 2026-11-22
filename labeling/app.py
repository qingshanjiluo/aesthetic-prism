# labeling/app.py: segment-2 labeling platform, STANDALONE entry (labeling/ is DATA
# territory; never touches src/aesthetic_prism/serve/* - that is SERVE's). Port 8100,
# not 8000. s6a ships the W9-safe session route; pair/rate/gold/export arrive s6b.
#
# W9 audit map (grep rater_id): every path built from rater_id is listed here and
# each one MUST sit behind _validate_rater_id -> ValueError becomes HTTP 400.
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .security import _validate_rater_id

ROOT = Path(__file__).resolve().parents[1]  # project root: labeling/ -> up 1
ANNOT_DIR = ROOT / "data" / "annotations"


def _error(status: int, code: str, message: str) -> tuple[int, dict]:
    return status, {"error": {"code": code, "message": message}}


class _Handler(BaseHTTPRequestHandler):
    server_version = "Labeling/0.2"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:  # keep console quiet
        pass

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(*_error(400, "bad_json", "request body is not json"))
            return
        if self.path != "/api/session":
            self._send(*_error(404, "not_found", f"no route {self.path}"))
            return
        try:
            rid = _validate_rater_id(data.get("rater_id", ""))  # W9 gate, first
        except ValueError as exc:
            self._send(*_error(400, "bad_request", str(exc)))
            return
        # PATH POINT 1/1 (W9): sessions dir built from rater_id - validated above.
        sdir = ANNOT_DIR / "sessions" / rid
        sdir.mkdir(parents=True, exist_ok=True)
        self._send(200, {"ok": True, "rater_id": rid, "dir": str(sdir.relative_to(ROOT))})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Aesthetic Prism labeling platform (standalone).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args(argv)
    ANNOT_DIR.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"labeling platform on http://{args.host}:{args.port} (standalone, not serve/)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
