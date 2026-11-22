import ast
import sys
from pathlib import Path

p = Path(sys.argv[1])
src = p.read_text(encoding="utf-8-sig")
t = ast.parse(src)
fn = {n.name for n in t.body if isinstance(n, ast.FunctionDef)}
want = [
    "act_serve", "act_stop", "act_score", "act_demo", "act_reproduce",
    "act_status", "act_selfcheck", "act_open_ui", "act_open_dir", "act_cfg",
    "act_log", "act_tests", "act_lint", "act_typecheck", "act_coverage",
    "act_checkenv", "act_help", "act_gate_log", "act_open_logs", "act_export",
    "act_fill", "act_search", "act_maintain", "act_load", "act_health",
    "act_learn", "render_menu", "main", "stale_procs", "parse_val",
    "load_cfg", "save_cfg", "dwidth", "dpad", "port_up", "cfg_snapshot",
    "dataset_count", "checkpoint_rows", "onnx_paths",
]
miss = sorted(w for w in want if w not in fn)
print("AST_OK")
print("FUNCS=" + str(len(fn)))
print("MISSING=" + repr(miss))
print("ALL_PRESENT=" + str(not miss))

