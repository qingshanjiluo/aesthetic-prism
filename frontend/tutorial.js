// Aesthetic Prism 全流程可视化教程（原生 JS 零依赖零构建）
// 分步遮罩引导：clip-path 镂空高亮目标卡片 + 讲解气泡。
"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var STEPS = [
    { title: "1. 素材上传", body: "把 JPEG/PNG 拖进左侧框或点选，单张不超过 10MiB。", note: "POST /upload", card: 0 },
    { title: "2. 运行评分", body: "点「运行评分」，服务端用模型打分，右侧出五维条与总分。", note: "POST /score", card: 1 },
    { title: "3. 触发训练", body: "填步数(1-10000)点「触发训练」，进度条实时刷新。", note: "POST /train", card: 2 },
    { title: "4. 服务状态", body: "看就绪/模型/设备/运行时长，右上灯绿=就绪 黄=降级 红=异常。", note: "GET /health", card: 3 },
    { title: "5. 接口速查", body: "前端所有操作都走这些接口，字段见契约文档。", note: "C-SERVE-01", card: 5 },
    { title: "6. 多图比对", body: "切「多图比对」tab，随机抽 N 张或自选，点「评分对比」看四维度明细表与「哪张更好 + 训练建议」结论。", note: "POST /score-batch", card: 0 },
    { title: "7. 数据标注", body: "切「数据标注」tab，随机抽 N 张待标注，拖滑块打 4 维分 + 选质量标签，保存入库。", note: "POST /annotations", card: 0 },
    { title: "8. 导出与训练", body: "标注页点「导出 CSV/JSONL」下载标注集；「导入训练集」用已标注图启动批量训练。", note: "GET /annotations/export", card: 0 },
    { title: "9. 素材库", body: "切「素材库」tab 浏览全量素材，Ctrl+点击多选，加入比对或批量删除；卡片显示「✓已标注/待标注」。", note: "GET /assets", card: 0 }
  ];
  var idx = 0;
  var ov = null, pop = null, mask = null;
  function build() {
    if (ov) return;
    mask = document.createElement("div");
    mask.id = "tour-mask";
    mask.style.cssText = "position:fixed;inset:0;z-index:9998;background:rgba(6,8,12,.6);display:none;pointer-events:none;";
    ov = document.createElement("div");
    ov.id = "tour-overlay";
    ov.style.cssText = "position:fixed;inset:0;z-index:9997;display:none;";
    pop = document.createElement("div");
    pop.id = "tour-pop";
    pop.style.cssText = "position:fixed;z-index:9999;width:min(380px,90vw);padding:16px 18px;background:#171c27;border:1px solid #2d3549;border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.55);color:#e8ebf3;font:14px/1.6 inherit;display:none;";
    document.body.appendChild(mask);
    document.body.appendChild(ov);
    document.body.appendChild(pop);
    ov.addEventListener("click", off);
  }
  function on() {
    build();
    idx = 0;
    show();
  }
  function off() {
    if (ov) ov.style.display = "none";
    if (pop) pop.style.display = "none";
    if (mask) mask.style.display = "none";
  }
  function show() {
    var c = STEPS[idx];
    var cards = document.querySelectorAll("section.card");
    var el = cards[c.card];
    var r = el ? el.getBoundingClientRect() : null;
    ov.style.display = "block";
    mask.style.display = "block";
    if (r) {
      var p = 8;
      var cpath = "polygon("
        + "0px 0px," + window.innerWidth + "px 0px," + window.innerWidth + "px " + window.innerHeight + "px,0px " + window.innerHeight + "px,"
        + "0px 0px," + "0px 0px," + r.left + "px " + r.top + "px," + r.right + "px " + r.top + "px," + r.right + "px " + r.bottom + "px," + r.left + "px " + r.bottom + "px)";
      mask.style.clipPath = cpath;
    }
    var title = document.createElement("h3");
    title.textContent = c.title;
    var body = document.createElement("p");
    body.textContent = c.body;
    var note = document.createElement("div");
    note.textContent = c.note;
    var nav = document.createElement("div");
    var bprev = document.createElement("button"); bprev.textContent = "上一步"; bprev.className = "btn";
    var bnext = document.createElement("button"); bnext.textContent = "下一步"; bnext.className = "btn primary";
    var bexit = document.createElement("button"); bexit.textContent = "退出"; bexit.className = "btn";
    nav.appendChild(bprev); nav.appendChild(bnext); nav.appendChild(bexit);
    bprev.onclick = function () { if (idx > 0) { idx--; show(); } };
    bnext.onclick = function () { if (idx < STEPS.length - 1) { idx++; show(); } else { off(); } };
    bexit.onclick = off;
    pop.innerHTML = "";
    pop.appendChild(title); pop.appendChild(body); pop.appendChild(note); pop.appendChild(nav);
    var pw = pop.offsetWidth || 360;
    var px = r ? Math.max(8, Math.min(r.left + r.width / 2 - pw / 2, window.innerWidth - pw - 8)) : 20;
    var top = r ? Math.min(r.bottom + 14, window.innerHeight - 180) : 60;
    pop.style.left = px + "px";
    pop.style.top = top + "px";
    pop.style.display = "block";
  }
  function addBtn() {
    var hud = document.querySelector(".hud");
    if (!hud || document.getElementById("tour-start")) return;
    var b = document.createElement("button");
    b.id = "tour-start"; b.className = "btn"; b.type = "button";
    b.textContent = "教程";
    b.addEventListener("click", on);
    hud.insertBefore(b, hud.firstChild);
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", addBtn); } else { addBtn(); }
})();
