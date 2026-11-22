# Aesthetic Prism 商业化改造规划（COMMERCIAL.md）

> 目标：单机工具 → 登录+鉴权+积分的商业化服务。
> 部署：单机 SQLite（免外部数据库），FastAPI 后端 + 前端 SPA + PyInstaller 桌面壳。
> 计费：所有付费端点先鉴权再扣积分，余额不足 402/积分不足。

## 一、分层架构

```
桌面应用 (PyInstaller exe)
  └─ 内嵌浏览器壳 / 或起本地服务 + 打开默认浏览器
       └─ 前端 SPA（登录/工作台/商城/空间/算力/钱包）
            └─ FastAPI 后端 (serve/app.py)
                 ├─ 鉴权层（JWT + 密码哈希）
                 ├─ 计费引擎（扣积分 + 流水）
                 └─ 业务（评分/上传/训练/生成/模型/算力）
                      └─ SQLite (auth.db)
```

## 二、数据模型（SQLite）

- `users`: id, username, password_hash, created_at
- `wallets`: user_id, balance(积分), space_bytes(云端空间配额), updated_at
- `ledger`: id, user_id, amount(±), kind(充值/消费/赠送), item, ts
- `orders`: id, user_id, item, kind(模型/空间/算力/充值), amount, ts
- `purchases`: user_id, model_id, ts （模型商城已购）

## 三、计费价目（初始，可配置）

| 功能 | 消耗积分 |
|------|---------|
| 评分 /score | 10 |
| 批量评分 /score-batch (每图) | 5 |
| 上传 /upload | 2 |
| 批量上传 /assets/upload-batch (每文件) | 2 |
| 训练 /train | 100 |
| 自动生成 /samples/generate (每图) | 3 |
| 模型下载 /models/download | 按模型定价 |
| 空间扩容 1GB | 200 |
| 云端算力 API /compute | 按调用档 |

## 四、认证流程

1. 注册 `POST /auth/register` {username,password} → 建用户 + 钱包(赠送 100 积分)
2. 登录 `POST /auth/login` → 校验密码 → 返回 JWT token
3. 鉴权：`Authorization: Bearer <token>` → 依赖 get_current_user 解析 JWT → 载入用户+钱包
4. 受保护端点先鉴权，计费端点再扣积分

## 五、桌面应用

- PyInstaller 打包：`pyinstaller --onefile serve_entry.py`（起 uvicorn + 开浏览器）
- 或 Electron 壳内嵌（重，暂缓）；优先 PyInstaller + 双击.bat/exe 起本地服务 + 开默认浏览器

## 六、实现顺序

1. 后端：auth（users/wallet/JWT）+ 计费引擎（charge+ledger）
2. 后端：受保护端点接入鉴权+计费（评分/上传/训练/生成/批量）
3. 后端：模型商城 + 空间扩容 + 算力 API
4. 前端：登录页 + 钱包/商城/空间/算力视图 + 请求带 token
5. 桌面打包：PyInstaller + 双击启动
6. 测试 + 起服实测 + 提交推送