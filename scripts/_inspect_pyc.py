import marshal
import sys
import pathlib

P = pathlib.Path(r"G:\pipi\proj\aesthetic-prism\__pycache__\launcher.cpython-313.pyc")
if not P.is_file():
    cand = list(pathlib.Path(r"G:\pipi\proj\aesthetic-prism\__pycache__").glob("launcher.cpython-313.pyc"))
    if not cand:
        print("MISSING", P)
        sys.exit(2)
    P = cand[0]

with P.open("rb") as fh:
    head = fh.read(16)
    co = marshal.load(fh)

print("PATH", P)
print("CODE_SIZE", len(co.co_code))
print("NAMES", co.co_names)
print("CONSTS_STR", [c for c in co.co_consts if isinstance(c, str)])
funcs = [c.co_name for c in co.co_consts if hasattr(c, "co_name")]
print("FUNCS", funcs)
print("FUNC_COUNT", len(funcs))
