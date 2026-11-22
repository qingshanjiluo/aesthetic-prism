import json, urllib.request, uuid
import mimetypes

repo = r"G:\皮皮\编程项目\aesthetic-prism"
img_path = repo + r"\data\synthetic\syn_000001.png"
boundary = uuid.uuid4().hex
with open(img_path, "rb") as f:
    img_bytes = f.read()
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="image"; filename="syn_000001.png"\r\n'
    f"Content-Type: image/png\r\n\r\n"
).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/score", data=body, method="POST",
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
)
with urllib.request.urlopen(req, timeout=30) as r:
    score = json.loads(r.read())
health = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10).read())
out = {"health": health, "score": score}
with open(repo + r"\qa\evidence\S4\S4-02-serve.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps(out, indent=2))
