import os, subprocess, sys, time
repo = r"G:\皮皮\编程项目\aesthetic-prism"
env = dict(os.environ)
env["PYTHONPATH"] = repo + r"\src"
env["AP_MODE"] = "onnx"
env["AP_MODEL_PATH"] = repo + r"\artifacts\student.onnx"
p = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "aesthetic_prism.serve.app:app",
     "--host", "0.0.0.0", "--port", "8000"],
    cwd=repo, env=env,
    stdout=open(repo + r"\reports\serve_s4.log", "w"),
    stderr=subprocess.STDOUT,
)
print("PID=", p.pid)
time.sleep(10)
print(open(repo + r"\reports\serve_s4.log", encoding="utf-8", errors="replace").read()[-1500:])
