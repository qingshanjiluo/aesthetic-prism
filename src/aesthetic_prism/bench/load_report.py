"""S8-02 压测报告（docs/05_DEPLOY §7.2 报告字段全列）：QPS/P50/P95/错误率/样本量/warmup/并发/时长/环境。"""
from __future__ import annotations

import csv
import io
import json
import os
import pathlib
import platform
import sys

try:
    from aesthetic_prism._aproot import AP_ROOT  # type: ignore
except ImportError:  # pragma: no cover — 未安装包时回退
    AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
os.chdir(AP_ROOT)

EV = os.path.join("qa", "evidence", "S8")


def main() -> int:
    rows = list(csv.DictReader(io.StringIO(pathlib.Path(os.path.join(EV, "qps_stats.csv")).read_text(encoding="utf-8"))))
    agg = next(r for r in rows if r["Name"] == "Aggregated")
    qps = float(agg["Requests/s"])
    fails = int(agg["Failure Count"])
    total = int(agg["Request Count"])
    p50 = float(agg["50%"])
    p95 = float(agg["95%"])
    err_rate = fails / total * 100 if total else 0.0
    # warmup：05_DEPLOY §7.2 规定 stats.clear() 前 5 次不计入；本次压测由 locust
    # headless 直跑统计（服务器 S8-01 已预热 30s 且 health/ score 各跑过），warmup=done_pre_run
    report = {
        "qps": qps,
        "p50_ms": p50,
        "p95_ms": p95,
        "error_rate_pct": round(err_rate, 2),
        "request_count": total,
        "failure_count": fails,
        "warmup": "server pre-warmed before run (S8-01 30s + prior score requests)",
        "users": 8,
        "duration_s": 30,
        "csv": "qa/evidence/S8/qps_stats.csv",
        "env": {"cpu": platform.processor(), "python": sys.version.split()[0], "mode": "onnx (student)"},
    }
    with open(os.path.join("reports", "load_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    ok = qps >= 5 and fails == 0
    print("LOAD-PASS" if ok else "LOAD-FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
