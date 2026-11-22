# 04 标注方案（DATA：标注流程 · 标注平台 · 导出对齐）

| 项 | 值 |
|---|---|
| 文档 ID | D-LABEL-04 |
| 归属 | DATA 起草，lead 批准；段 2 标注闭环照单执行 |
| 状态 | 草案 |
| 关联契约 | C-DATA-01 §3.2/§3.3（五键+rater_count、JSON Schema）、08_ACCEPTANCE S2-02/S2-03/S2-05、docs/02_DATA.md、docs/00_PRD.md US5 |
| 关联裁决 | A=五键同名 `total`/`composition`/`light`/`creativity`/`story`；C=qa/ 归 QA（本文只读）；D=命令走 sh -c；R3=黄金题判别与一致性加权规则 |

## 1. ① 标注流程（成对 Bradley-Terry 素材 · 四维评分 0–100）

### 1.1 轮次模型与状态机

- 一次**会话（round）** = 标注者的一轮任务序列：**四维评分 ≥4 张 + 成对选择 ≥12 组**（其中黄金题见 §2，≥8 组/轮）。S2-02 的"10 次标注"= 全部 `export_*.json` 累计**标注条目 ≥10**（条目 = 一个完成聚合的样本，见 §5 计数语义）。
- 样本状态机：`pending`(0 人已标) → `annotating`(1–2 人) → `ready`(有效人数 ≥3，可入库) → `exported`(进入某批次 `export_*.json`)。不足 3 人的样本**不导出**，继续挂 `annotating` 凑数；已导出样本再收到的新标注**不回写**该批次（攒入下一批次，避免批次间漂移）。

### 1.2 四维评分操作界面语义（0–100 滑条）

| 界面元素（中文） | 提交键名（五键之一） | 提示语 | 域 | 步长 | 默认值 |
|---|---|---|---|---|---|
| 构图 | `composition` | 主体位置、画面平衡、留白取舍 | 0–100 | 1 | 50 |
| 光影 | `light` | 明暗关系、对比强弱、光感是否舒服 | 0–100 | 1 | 50 |
| 创意 | `creativity` | 是否新颖、不落俗套、有想法 | 0–100 | 1 | 50 |
| 故事性 | `story` | 有无线索、情绪与想象空间 | 0–100 | 1 | 50 |

- **`total` 不让标注者直接打**：由入库四维按 `round(0.3·composition + 0.3·light + 0.2·creativity + 0.2·story, 1)` 计算，权重与 C-DATA-01 §5.1 示例逐字一致，杜绝"总分与子分自相矛盾"。
- 提交校验：四滑条**全部被触碰过**才可提交（四维全 50 → 400 `all_default`，防懒提交）；提交即以追加方式写 `data/annotations/sessions/{rater_id}/{round_id}.jsonl`（UTF-8/LF，一行一条原始打分，含 rater/图 id/时间戳）。

### 1.3 成对选择 → Bradley-Terry 素材构造

- 界面：双图并排（左右顺序**随机化**防位置偏差），快捷键 `1`=左优 `2`=右优 `3`=难分。`3` 弃权**不进** BT 素材。
- 配对策略：同一批标注池内随机配对，**度数均衡**——维护每图已配对次数，优先配"配对次数最少"的两张，保证每图成对 ≥2 次，避免孤立节点导致 BT 解退化。
- 记录结构（一行一条，落 `data/annotations/pairs.jsonl`，**不放** `export_*.json`，防 S2-02 计数膨胀）：

```json
{"pair_id": "p_000042", "left_id": "syn_000017", "right_id": "syn_000104", "winner": "left", "rater_id": "r01", "round_id": "rd_003", "is_gold": false, "ts": "2026-11-08T04:10:00+08:00"}
```

- `winner ∈ {"left","right"}`；`is_gold=true` 的记录同时带服务端保管的 `gold_answer`（仅落库，不下发前端）。消费方：ranking 头（Bradley-Terry）的成对一致率训练/评测素材——**归 MODEL，路径若与 03_TRAINING 约定不同须经 lead 裁决**，DATA 不改训练侧。
- BT 素材有效性自检（导出时跑）：每图度数 ≥2、`left_id ≠ right_id`、winner 值域合法，违例记录进 `qc` 清单不入对。

## 2. ② 黄金题（gold pair）比例与判别规则（R3）

- **来源（服务端保管，永不下发正答）**：黄金题复用合成数据 §2 的"对照兄弟对"——同 family、同画布参数、只扰动单维参数、`total` 差 ≥25 分的两张图（差越大题越"送分"）。答案由 `data/synthetic/index.json` 的标签函数确定：`winner = left_id` 当且仅当 `left.total ≥ right.total`。
- **比例（硬下限）**：**≥8 组/轮**成对黄金题 + **≥2 道**四维黄金题（黄金四维 = 直接复用合成标签，标注者打分与其绝对差 >30 记错）；黄金题混入正式题流（洗牌后按 1/N 间隔插入，标注者不可辨识）。黄金记录带 `is_gold:true`，独立存 `data/annotations/gold.jsonl`，不入 `pairs.jsonl`、不入 `export_*.json`。
- **判别规则（批次级，R3）**：

| 批次/轮 黄金题通过率 acc | 判定 | 动作 |
|---|---|---|
| acc ≥ 80% | 有效 | 该批 `quality = "pass"`，权重 1.0，正常入库聚合 |
| acc < 80% | 降权 | 该批 `quality = "downweighted"`，该标注者全部有效打分权重 ×0.5；若降权后样本有效人数 <3 → 样本回落 `annotating`，不导出 |
| acc < 60% 或单轮 ≥4 题连错 | 作废 | 该轮整轮丢弃（raw 保留审计），标注者置 `probation`，下一轮题量减半复测 |

- 每份 `export_*.json` 的 `meta.gold` 记录 `{asked, passed, acc, verdict}`，QA 可直接复算 `acc = passed/asked`。

## 3. ③ 标注者一致性加权与入库聚合（R3 + C-DATA-01 §3.2）

### 3.1 单标注者权重

对标注者 r（其黄金题通过率 `acc_r`、与同批他人中位数的平均绝对偏差 `mad_r`）：

```text
q_r   = 0.7·acc_r + 0.3·(1 − min(1, mad_r/30))        # 质量分 q∈[0,1]
w_r   = q_r × (0.5 if 该批 downweighted else 1.0)       # 有效权重
```

### 3.2 聚合公式（中位数锚定 + 加权修正，入库唯一步骤）

```text
median_d = median({s_r(d) : r ∈ 有效标注者})            # 锚：单人极端值打不飞
label_d  = round( clip( median_d + Σ_r w_r·(s_r(d) − median_d) / Σ_r w_r, 0, 100 ), 1 )
total    = round(0.3·composition + 0.3·light + 0.2·creativity + 0.2·story, 1)
```

- 有效性门禁（C-DATA-01 §3.2）：**聚合样本必须 `rater_count ≥ 3`**（`rater_count` = 参与聚合的有效标注人数，域 1–100，本流程实际取 3..100）；`rater_count < 3` 不导出（E5 会拦截）。
- **SD>15 处理**：四维中任一维 `stdev(有效打分) > 15` → 该维自动追加 **2 名**应急标注者重新聚合；重标后仍 `SD>15` → 样本标记 `contested:true`，`quality="contested"` 随导出上报（`rater_count` 记实际有效人数），聚合仍走 3.2 中位数锚定（不静默丢弃）。
- 聚合输出即 §5 的 `labels` 五键 + `rater_count`，经 `validate_dataset_sample`（R1/R2 语义）通过后才允许写入 `export_*.json`。

## 4. ④ 标注平台最小闭环功能清单

### 4.1 段 2 门禁必做四件套（S2 闭环，缺一即门禁 FAIL）

| # | 功能 | 最小实现 | 端点/产物（labeling/ 内，端口 127.0.0.1:8001，与 SERVE 的 8000 分离） |
|---|---|---|---|
| 1 | **成对** | 双图并排 + 快捷键 1/2/3 + 随机化左右 + 度数均衡配对 | `POST /api/pair/next`（取题）、`POST /api/pair/submit` → 追加 `pairs.jsonl` |
| 2 | **四维** | 图 + 4 条 0–100 滑条（构图/光影/创意/故事性）+ 未触碰校验 + `total` 服务端算 | `POST /api/rate/submit` → 追加 `sessions/{rater}/{round}.jsonl` |
| 3 | **黄金题** | ≥8 组/轮成对 + ≥2 道四维混入题流、正答不下发、服务端判分与降权（§2） | `POST /api/rate/submit`、`POST /api/pair/submit` 内 `is_gold` 分流 → `gold.jsonl` + `meta.gold` |
| 4 | **导出** | 聚合（§3）→ `validate_dataset_sample` → 落 `export_*.json`（字段见 §5，累计条目 ≥10、文件 ≥1 = S2-02） | `POST /api/export`、`GET /api/export/preview` |

最小前端三页（labeling/ 静态页，无框架亦可）：`index.html`（登录=rater_id 输入 + 题流）、`rate.html`（四维）、`pair.html`（成对）；导出走按钮/CLI `python -m labeling.export`。

### 4.2 段 4 增量（本轮不做，列入 04 的范围外清单）

多人会话并发与锁（同图多 rater 同时取题防撞题）、断点续标（会话进度快照 + 续标路由）、导出聚合批处理（多轮合并、增量批次、`data/exports/*.jsonl` 汇编）、rater 管理后台。段 2 只保证单机串行四件套闭环。

## 5. ⑤ 导出 JSON 与 DatasetSample §3.3 schema 逐字段对齐

### 5.1 `export_*.json` 物理格式

- 路径：`data/annotations/export_<YYYYMMDD-HHMMSS>.json`（≥1 份 = S2-02 文件数）；UTF-8、LF。
- 内容 = **两键对象**：`{"meta": {...批次信息...}, "samples": [DatasetSample, ...]}`——顶层不是裸 DatasetSample，也不是裸数组。

**计数语义（S2-02 判定依据，写死）**：**累计标注条目 = 各 `export_*.json` 的 `samples` 数组长度之和**；"完成 10 次标注" = `Σ len(samples) ≥ 10` 且 `len(export_*.json) ≥ 1`。条目即已聚合入库的样本；成对记录/黄金记录/session 原始行**均不算**条目。计数器与 08_ACCEPTANCE S2-02 的 `cnt` 函数语义一致（list 取 `len`，对 dict 值中的 list 求和）。

### 5.2 逐字段对齐表（导出条目 = C-DATA-01 §3.1/§3.2/§3.3 一个对象，无新增顶层键）

| 字段 | 来源（本文档/平台侧） | 类型/域 | 对齐契约 | 备注 |
|---|---|---|---|---|
| `id` | 导出时分配，正则 `^(syn\|img)_[0-9]{6}$` | string | §3.1 | 同图复用既有 id（02 §4 防泄漏：`sha256→id` 注册表），新图取未占用 `img_` 号 |
| `image_path` | 标注池原图相对路径 | POSIX，无 `\`，`.jpg/.jpeg/.png`，≤260 | §3.1 | 从 `data/synthetic/index.json` 原样带出 |
| `image_sha256` | 平台入库时重算 | `^[0-9a-f]{64}$` | §3.1 | 导出前重算比对，不一致拒导 |
| `bytes` | 文件 `stat().st_size` | 1..10,000,000 | §3.1 | 导出时现取 |
| `width` / `height` | PIL `Image.open().size` | 16..8192 | §3.1 | 同上 |
| `source` | 恒 `"labeled"` | enum | §3.1 | 导出批次内全为 labeled（合成批在 02） |
| `labels` | §3.2 聚合结果（四维 + total + rater_count） | object/null | §3.2 | labeled 批**不得为 null**（R1） |
| `labels.total` | §3 公式计算，1 位小数 | 0..100 | §3.2 | 键名逐字 `total` |
| `labels.composition` | 聚合四维之一 | 0..100 | §3.2 | 界面"构图"提交键 |
| `labels.light` | 聚合四维之一 | 0..100 | §3.2 | 界面"光影"提交键 |
| `labels.creativity` | 聚合四维之一 | 0..100 | §3.2 | 界面"创意"提交键 |
| `labels.story` | 聚合四维之一 | 0..100 | §3.2 | 界面"故事性"提交键 |
| `labels.rater_count` | 有效标注人数 | int 1..100（本流程 ≥3） | §3.2 条件必填 | R1：source=labeled 必填 |
| `meta.*`（`schema_version`/`exported_at`/`gold{}`/`quality`/`counts`） | 平台批次信息 | object | **不在** DatasetSample | 仅存于 export 顶层，不进条目（条目 `additionalProperties:false`） |

- **校验双闸**：① 每条目过 `validate_dataset_sample`（§3.3 schema + R1/R2）；② 整份过 `data/annotations/schema.json`（S2-03，`jsonschema.validate`）。任一失败 → 该批拒导、报错给 lead（E5/E6 语义，不静默降级）。
- **五键锁**：条目 `labels` 键集合恒 = `{total, composition, light, creativity, story, rater_count}`；历史键名全链路禁用（裁决 A，0 命中）。

## 验收标准（可执行检查，裁决 D：一律 `sh -c`；工作目录=项目根 `aesthetic-prism/`；证据 `qa/evidence/S2/`）

> 判定语义逐条引用 08_ACCEPTANCE **S2-02 / S2-03 / S2-05 原命令**（原文含双引号按 08 通用约定本走落盘法；下列为可直接 `sh -c` 的等价式，阈值不变）。命令 4 = 本文档自检，现在即可跑；1–3 为段 2 门禁（标注导出落地后跑，S2-05 的人工半段见 08 原文步骤）。

```bash
# 1) S2-02：导出文件 ≥1 且累计标注条目 ≥10（引 08_ACCEPTANCE S2-02 原判定 cnt 函数语义；python 源全单引号，外层 sh 双引号转义成对）
sh -c "mkdir -p qa/evidence/S2; python -c \"import json,glob,sys;fs=glob.glob('data/annotations/export_*.json');d=[json.load(open(f)) for f in fs];cnt=lambda x: len(x) if isinstance(x,list) else (sum(len(v) for v in x.values() if isinstance(v,list)) or len(x));tot=sum(cnt(x) for x in d);print('files=',len(fs),'entries=',tot);sys.exit(0 if len(fs)>=1 and tot>=10 else 1)\" 2>&1 | tee qa/evidence/S2/S2-02.log"

# 2) S2-03：全部 export_*.json 逐个过 data/annotations/schema.json（引 08_ACCEPTANCE S2-03 原判定 jsonschema.validate）
sh -c "mkdir -p qa/evidence/S2; python -c \"import json,glob,jsonschema as js;sch=json.load(open('data/annotations/schema.json'));fs=sorted(glob.glob('data/annotations/export_*.json'));assert len(fs)>=1,fs;[js.validate(json.load(open(f)),sch) for f in fs];print('validated',len(fs))\" 2>&1 | tee qa/evidence/S2/S2-03.log"

# 3) S2-05 步骤①：从全部导出条目随机抽 10 条落盘抽样清单（步骤②③人工核对按 08_ACCEPTANCE S2-05 原文执行，合格 ≥9/10）
sh -c "mkdir -p qa/evidence/S2; python -c \"import json,glob,random;random.seed(0);fs=sorted(glob.glob('data/annotations/export_*.json'));e=[s for f in fs for s in json.load(open(f))['samples']];r=random.sample(e,min(10,len(e)));open('qa/evidence/S2/S2-05_sample.txt','w',encoding='utf-8').write('\n'.join(x['id']+' '+x['image_path'] for x in r));print('sampled',len(r))\" 2>&1 | tee qa/evidence/S2/S2-05.log"

# 4) 本文自检：五键（键级）齐备 + 三历史键名零残留（模式括号自避，不与本文自匹配）
sh -c "grep -q '\`total\`' docs/04_LABELING.md && grep -q '\`composition\`' docs/04_LABELING.md && grep -q '\`light\`' docs/04_LABELING.md && grep -q '\`creativity\`' docs/04_LABELING.md && grep -q '\`story\`' docs/04_LABELING.md && ! grep -qE 'colo[u]r|light[in]g|det[a]il' docs/04_LABELING.md"
```

判定：命令 1（条目 ≥10、文件 ≥1）、2（validate 无异常）退出码 0 = S2-02/S2-03 过；3 只生成抽样清单，S2-05 最终判定 = 人工核对合格 ≥9/10 并记入 `qa/evidence/S2/S2-05.md`；4 = 本文档键名合规。全部证据落 `qa/evidence/S2/`（QA 所有，DATA 只读，裁决 C）。
