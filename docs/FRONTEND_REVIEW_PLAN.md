# Aesthetic Prism 前端全面审查与开发规划

审查时间 2026-11-27 · 审查范围 `frontend/`（index.html 699 行 / app.js 335 / app2.js 930 / api.js 77 / tutorial.js 88）
方法：design-taste-frontend（anti-slop 检查表）+ web-layout-creative（slop-scan 量化）+ CDP 实拍截图 24 张 + DOM 探针

---

## 0. 量化结论（slop-scan）

```
85/100 GOOD
[15] 无非常规技法 (-10)   → 命中 1 项（sticky 编排），需 ≥2
[16] 无动效降级 (-5)      → 缺 @media (prefers-reduced-motion: reduce)
版心档数 2 · 节间距种类 0 · 圆角种类 2 · 字族声明 12
```

85 分已 GOOD，但要冲 90+ 需补 2 项非常规技法 + reduced-motion 分支。

---

## 1. 致命缺陷（P0，切 tab 白屏/错位）

**现象**：CDP 探针实测——点「数据标注」tab 后：
- `view-annotate.hidden=false`、`display=block`、`height=338px` ✅ 视图本身渲染正常
- 但 `view-annotate` 的 `getBoundingClientRect().top=1403px`，**在视口外 1400px 深处**
- 首页 `#view-home` 是裸 `<main id="view-home">`（无 `.view` class），CSS 规则 `.view[hidden]{display:none}` 不匹配它，**home 永远可见**
- 9 个视图容器在 DOM 里全量堆叠（home 双列 + library + compare + annotate + score + wallet + shop + space + compute），scrollH=1802px
- 切 tab 后 scroll 位置停在原处，新视图在 1400px 外 → 用户看到空白/错位

**根因**：`switchView` 只翻转 `hidden` 属性，但 home 容器无 `.view` class 导致隐藏失效；多视图全量堆叠未做 display 互斥。

**修复**：
1. `#view-home` 加 `class="view"`（与其余 8 个一致）
2. `switchView` 切 tab 后 `window.scrollTo({top:0,behavior:'instant'})`
3. 可选：给 `.view` 加 `:target`/`display` 互斥兜底

**验证**：CDP 探针复测 `annotTop<200`、`homeDisp=none`、`scrollH≈视图自身高度`。

---

## 2. 设计缺陷（P1，瑞典主义一致性）

| 项 | 现状 | 目标 |
|---|---|---|
| 非常规技法 | 仅 sticky 1 项 | 补 1 项：评分结果卡加 `view-transition-name`（评分切换时数字滚动过渡）或对比表 `container-type` 响应 |
| reduced-motion | 全无 | 所有 transition/animation 加 `@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}` |
| 字族声明 12 | `--mono` 5 族 + `--sans` 7 族 | 收敛：`--mono` 留 3（Cascadia Code/Consolas/JetBrains Mono），`--sans` 留 3（Inter/system-ui/sans-serif），删 PingFang/MSYaHei 冗余 |
| 圆角种类 2 | `--r-sm/md/lg` 已收敛 ✅ | 保持 |
| 版心档数 2 | main 1240 + footer 1240 共用 | 加 `--content-prose` 档（标注备注/教程正文 65ch） |
| 触控目标 | `.ann-row button` 32×26 < 44×44 | 扩到 44×44 或加 padding |
| 对比度 | `--muted:#8a867b` 对 `--bg:#f6f5f1` ≈ 3.1:1（低于 4.5） | muted 加深到 `#6b6860`（≈4.6:1） |

---

## 3. 功能完善度缺口（P1）

| 视图 | 缺口 | 补法 |
|---|---|---|
| 首页评分 | 单图模式，缺「对比前图/后图」 | 评分结果加 `对比上次评分` delta 列（存 localStorage 上次 total） |
| 素材库 | 无拖拽排序、无批量下载 | 加 `下载选中`（fetch blob 拼接 zip） |
| 比对 | 随机抽固定 4 张不可配 | `cmp-random` 读 `lib-random-n` 值 |
| 标注 | 无进度条、无标注完成度 | 工具栏加 `已标 X / 总 Y` + 进度条 |
| 标注 | 质量标签无图标 | 4 标签加 SVG 图标（对勾/叉/问号/水印） |
| 批量评分 | 进度文本无百分比 | `sc-progress` 加 `n/total` |
| 钱包 | 流水无分页、无筛选 | 加 kind 筛选 select |
| 商城 | 已购不可下载 | 购买后加 `下载模型` 按钮（fetch 模型文件） |
| 算力 | 结果只 JSON 文本 | 加 `复制 JSON` 按钮 |
| 教程 | 只 5 步遮罩，缺标注/比对步骤 | STEPS 加 6-9（比对/标注/导出/训练） |
| 登录 | 无「记住我」、无忘记密码 | 加 checkbox（token 永存 vs 7 天） |

---

## 4. 代码质量（P2）

| 项 | 现状 | 补法 |
|---|---|---|
| 全局变量泄漏 | app.js 顶层 `const` 污染全局；app2.js 用 IIFE 但 `toast/modal` 未导出 | app.js 包 IIFE + 导出 `window.APP` |
| 重复 fetch | app.js 裸 fetch，app2.js 走 `API`，两套封装 | 统一走 `API`（api.js） |
| 轮询无退避 | `pollHealth` 5s 固定；`pollJob` 1.5s 固定 | 指数退避（4s/8s/16s cap 30s） |
| 错误体 | `bodyError` 只认 `body.error`，不认 FastAPI `detail` 数组 | 加 `detail` 兼容 |
| XSS 面 | `cmp-verdict`/`ann-list` 用 `innerHTML` 拼用户数据（path/note） | path 做 `encodeURIComponent` 转义，note 用 `textContent` |
| 图片懒加载 | grid img 无 `loading=lazy`（标注卡有，素材卡漏） | 统一 `loading=lazy` |
| 内存 | `URL.createObjectURL` 只 revoke 上一次的 | 列表化 revoke |
| 无单测 | 前端零测试 | 加 vitest 核心逻辑（`annRecalcTotal`/`renderCompare` 排序/`debounce`） |

---

## 5. 响应式（P1）

实拍 390/768/1024 截图 + 探针：
- 390：`.ann-work` 单列 ✅；`.ann-row` 5 列挤压（`1fr 72 72 44 40`）→ 改 2 行布局
- 768：home 双列已断成单列（`@media(max-width:960px)`）✅；toolbar 按钮换行 ✅
- 1024：正常
- 缺：`#app-tabs` 9 tab 在 390 下 `flex-wrap` 占 3 行，吸顶后吃 120px → 改 `overflow-x:auto` 单行 + `scroll-snap`（补 1 项非常规技法，一举两得）

---

## 6. 分阶段开发计划

### 阶段 A · P0 致命（0.5 天）
1. `#view-home` 加 `class="view"` + `switchView` 加 `scrollTo(0,0)`
2. CDP 探针回归（annotTop<200）
3. 提交

### 阶段 B · P1 设计一致性（1 天）
1. reduced-motion 全局分支
2. 字族收敛 12→6、muted 对比度加深
3. `#app-tabs` 单行 overflow-x + scroll-snap（补技法）
4. 评分结果 `view-transition-name`（补技法）
5. 触控目标 44px
6. 提交

### 阶段 C · P1 功能补缺（2 天）
1. 标注进度条 + 质量图标 + 对比 N 可配
2. 商城下载 + 算力复制 + 钱包筛选
3. 教程扩 4 步
4. 素材库批量下载
5. 提交

### 阶段 D · P2 代码质量（1.5 天）
1. app.js IIFE 化 + 统一 API + 错误体 detail 兼容
2. 轮询退避 + XSS 转义 + 懒加载统一
3. vitest 核心逻辑单测
4. 提交

### 阶段 E · 验收（0.5 天）
1. slop-scan 复跑目标 90+
2. 24 张截图复拍对比
3. 全量 pytest + 冒烟 + E2E
4. 提交 + 推送

---

## 7. 验收清单（对照 design-taste + web-layout-creative）

- [ ] P0：切 9 tab 全部视口顶部渲染（CDP annotTop<200）
- [ ] slop-scan ≥90（补 2 技法 + reduced-motion）
- [ ] 390 无横向滚动、tab 单行、标注行 2 行布局
- [ ] 触控目标 ≥44×44
- [ ] muted 对比度 ≥4.5:1
- [ ] 字体 ≤6 族
- [ ] 轮询退避（无 5s 死循环）
- [ ] innerHTML 拼接处 path/note 转义
- [ ] vitest 核心 3 函数过
- [ ] 全量 pytest 79/79 + 冒烟 SMOKE_PASS + E2E ALL_PASS
- [ ] 24 张截图无空白/错位

当前: 前端全面审查 / 结果: 规划文档 docs/FRONTEND_REVIEW_PLAN.md（P0 致命 tab 错位 + P1 设计/功能/响应式 + P2 代码质量 + 5 阶段排期 + 10 项验收） / 下一步: 阶段 A 修 P0（view-home 加 .view class + scrollTo）+ CDP 回归
