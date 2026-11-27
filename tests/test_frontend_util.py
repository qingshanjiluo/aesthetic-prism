# 前端 util.js 纯函数单测：写临时 node 脚本跑断言，零依赖。
import os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UTIL = ROOT / "frontend" / "util.js"
assert UTIL.exists(), "util.js 缺失"

TEST_JS = r"""
const U = require(process.argv[2]);
function eq(a, b, m) {
  if (JSON.stringify(a) !== JSON.stringify(b))
    throw new Error(m + ': ' + JSON.stringify(a) + ' != ' + JSON.stringify(b));
}
// escHtml
eq(U.escHtml('<img src=x onerror=alert(1)>'), '&lt;img src=x onerror=alert(1)&gt;', 'escHtml basic');
eq(U.escHtml('a&b"c\'d'), 'a&amp;b&quot;c&#39;d', 'escHtml all 5 chars');
eq(U.escHtml(null), '', 'escHtml null');
eq(U.escHtml(5), '5', 'escHtml number');
// annTotal
eq(U.annTotal(6, 5, 7, 4), 5.5, 'annTotal avg');
eq(U.annTotal(0, 0, 0, 0), 0, 'annTotal zero');
eq(U.annTotal(8, 8, 8, 8), 8, 'annTotal all 8');
eq(U.annTotal('a', 'b', 'c', 'd'), 0, 'annTotal non-numeric');
// sortByTotalDesc
eq(U.sortByTotalDesc([{ total: 5 }, { total: 9 }, { path: 'x' }, { total: 2 }])
   .map(function (i) { return i.total != null ? i.total : -1; }),
   [9, 5, 2, -1], 'sort desc null=-1');
eq(U.sortByTotalDesc([]), [], 'sort empty');
// pct
eq(U.pct(3, 10), 30, 'pct 3/10');
eq(U.pct(15, 10), 100, 'pct cap 100');
eq(U.pct(0, 0), 0, 'pct zero total');
console.log('FRONTEND_UTIL_OK');
"""

with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
    f.write(TEST_JS)
    tmp = f.name
try:
    r = subprocess.run(["node", tmp, str(UTIL)], capture_output=True, text=True, cwd=str(ROOT))
finally:
    os.unlink(tmp)
assert "FRONTEND_UTIL_OK" in r.stdout, f"node util test fail:\n{r.stdout}\n{r.stderr}"
print("FRONTEND_UTIL_PASS")
