# E2E: 标注全链路（POST → GET filter → DELETE → export）
import json, urllib.request, urllib.parse

BASE = "http://127.0.0.1:8001"

def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method)
    if body:
        r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())

# 1. 存 3 条标注（单机模式 user_id=0）
for i in range(3):
    p = f"uploads/e2e_annotate_test_{i}.jpg"
    d = req("POST", "/annotations", {
        "path": p,
        "composition": 6 + i,
        "light": 5 + i,
        "creativity": 7,
        "story": 4,
        "quality": "可用" if i < 2 else "模糊",
        "note": f"e2e test {i}",
        "annotator": "e2e",
    })
    assert d["total"] == round(((6+i)+(5+i)+7+4)/4, 2), d
    assert d["id"] >= 1
    assert d["user_id"] == 0, f"user_id should be 0 in local mode, got {d['user_id']}"
    print(f"[POST] {p} total={d['total']} quality={d['quality']} user_id={d['user_id']}")

# 2. GET 过滤
d = req("GET", "/annotations?quality=%E5%8F%AF%E7%94%A8")
assert d["total"] == 2, f"quality filter failed: {d['total']}"
d = req("GET", "/annotations?min_total=6.5")
assert d["total"] >= 1, f"min_total filter failed: {d['total']}"
print(f"[GET] quality filter total={req('GET', '/annotations?quality=%E5%8F%AF%E7%94%A8')['total']}")

# 3. export
d = req("GET", "/annotations/export?fmt=csv")
assert "path" in d["text"], "csv export missing header"
d = req("GET", "/annotations/export?fmt=jsonl")
assert d["count"] >= 3
print(f"[EXPORT] csv OK, jsonl count={d['count']}")

# 4. DELETE
for i in range(3):
    p = f"uploads/e2e_annotate_test_{i}.jpg"
    d = req("DELETE", "/annotations?" + urllib.parse.urlencode({"path": p}))
    assert d["deleted"] == 1
print("[DELETE] all cleaned up")

d = req("GET", "/annotations?path=e2e_annotate_test")
assert d["total"] == 0
print("ALL_PASS")
