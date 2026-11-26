# Aesthetic Prism 部署指南

## 1. 本地一键启动（源码）

```powershell
cd G:\皮皮\编程项目\aesthetic-prism
python serve_entry.py
```

- 端口探测：8000 → 8010 → 8001（被占自动 fallback）
- 可用 `AP_PORT=8001 python serve_entry.py` 指定
- 浏览器自动打开 `http://127.0.0.1:PORT/`
- 日志：`data/serve.log`（追加）

## 2. 裸 uvicorn（服务器/容器）

```bash
export PYTHONPATH=src
uvicorn aesthetic_prism.serve.app:app --host 0.0.0.0 --port 8000
```

- 数据目录：`./data/`（uploads、annotations.db、auth.db、assets_meta.json）
- 模型：`./models/`（teacher.onnx / student.onnx）
- 环境变量：
  - `AP_AUTH_DB` 认证库路径（默认 `auth.db`）
  - `AP_AUTH_SECRET` JWT 签名密钥（**生产必改**）
  - `AP_PORT` 入口端口

## 3. PyInstaller 单文件（Windows 桌面）

```powershell
pyinstaller --onefile serve_entry.py
# 产物：dist/serve_entry.exe（需 models/ 与 data/ 同目录或打包进 _MEIPASS）
```

双击 exe → 起服务 → 开浏览器。

## 4. 冒烟验证

```powershell
AP_PORT=8001 python scripts/_smoke_deploy.py
# 期望：health OK / GET×3 / POST / DELETE 全 200 → SMOKE_PASS
```

## 5. 商业化计费（PLAN）

| 动作 | 积分 |
|---|---|
| 评分 /score | 10 |
| 批量评分 /score-batch | 5/张 |
| 上传 /upload | 2 |
| 训练 /train | 100 |
| 样本生成 /samples/generate | 3/张 |
| 标注保存 /annotations POST | 1 |
| 标注导出 /annotations/export | 2 |

- 注册赠送 100 积分（`SIGNUP_BONUS`）
- 无 token = 单机模式全放行；带 token 余额不足 = 402
- 模型商城价格见 `auth.MODEL_PRICES`

## 6. 多用户数据隔离

- `annotations` 表：`user_id` 字段（0=单机），UNIQUE(user_id, path)
- 素材/训练任务：当前为共享目录（单机定位），如需租户隔离后续加 owner 字段
- 认证：`auth.db`（users/wallets/ledger/purchases），JWT 7 天

## 7. 回归

```powershell
$env:AP_MODE="mock"; python -m pytest tests -q
# 期望 79/79 通过
```
