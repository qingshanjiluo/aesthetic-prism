// Aesthetic Prism 增强视图主控（标签切换 + 素材库 + 多图比对 + 批量上传评分）
// 依赖 api.js；兼容现有 app.js（只操作 view-home，不冲突）。
"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var VIEWS = ["home", "library", "compare", "score"];
  var cmpPaths = [];      // 比对视图已载入路径
  var cmpPicked = [];     // 比对标记优的路径
  var libSel = {};        // 素材库多选 {path:1}

  function switchView(name) {
    VIEWS.forEach(function (v) {
      var el = document.getElementById("view-" + v);
      if (el) el.hidden = (v !== name);
    });
    var tabs = document.querySelectorAll("#app-tabs .tab");
    Array.prototype.forEach.call(tabs, function (t) {
      t.classList.toggle("active", t.getAttribute("data-view") === name);
    });
    if (name === "library") loadLibrary();
    if (name === "compare") renderCompare();
  }

  function bindTabs() {
    var tabs = document.querySelectorAll("#app-tabs .tab");
    Array.prototype.forEach.call(tabs, function (t) {
      t.addEventListener("click", function () { switchView(t.getAttribute("data-view")); });
    });
  }

  /* ===== 素材库 ===== */
  function loadLibrary() {
    var q = document.getElementById("lib-search").value;
    var sort = document.getElementById("lib-sort").value;
    var order = document.getElementById("lib-order").value;
    var params = { limit: 500, sort: sort, order: order };
    if (q) params.q = q;
    API.assets(params).then(function (d) {
      var grid = document.getElementById("lib-grid");
      grid.innerHTML = "";
      document.getElementById("lib-count").textContent = "共 " + d.total + " 个素材";
      d.items.forEach(function (it) {
        var c = document.createElement("div");
        c.className = "card" + (libSel[it.path] ? " selected" : "");
        var img = document.createElement("img");
        img.src = assetUrl(it.path);
        img.loading = "lazy";
        img.onerror = function () { this.style.background = "#222"; };
        var m = document.createElement("div"); m.className = "meta";
        var b = document.createElement("b"); b.textContent = it.filename; b.title = it.path;
        var s = document.createElement("div"); s.textContent = fmtSize(it.bytes) + " · " + it.mime.split("/")[1];
        m.appendChild(b); m.appendChild(s);
        if (it.tags && it.tags.length) { var tg = document.createElement("div"); tg.textContent = "#" + it.tags.join(" #"); tg.style.color = "var(--cyan)"; m.appendChild(tg); }
        c.appendChild(img); c.appendChild(m);
        c.addEventListener("click", function (e) {
          if (e.ctrlKey || e.metaKey) { libSel[it.path] = libSel[it.path] ? 0 : 1; c.classList.toggle("selected", !!libSel[it.path]); }
          else { openLightbox(it.path, it.filename); }
        });
        grid.appendChild(c);
      });
    }).catch(function (e) { toast(e.code + ": " + e.message); });
  }

  function fmtSize(n) {
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
    return n + " B";
  }

  /* ===== 灯箱预览 ===== */
  function openLightbox(path, name) {
    var ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.88);display:flex;align-items:center;justify-content:center;";
    var img = document.createElement("img");
    img.src = assetUrl(path); img.style.maxWidth = "88vw"; img.style.maxHeight = "86vh"; img.style.borderRadius = "8px";
    var cap = document.createElement("div");
    cap.textContent = name + "  ·  " + path;
    cap.style.cssText = "position:fixed;bottom:24px;left:0;right:0;text-align:center;color:#fff;font-size:13px;";
    ov.appendChild(img); ov.appendChild(cap);
    ov.addEventListener("click", function () { ov.remove(); });
    document.body.appendChild(ov);
  }

  /* ===== 多图比对 ===== */
  function addComparePaths(paths) {
    paths.forEach(function (p) { if (cmpPaths.indexOf(p) < 0) cmpPaths.push(p); });
    renderCompare();
  }
  function renderCompare() {
    var g = document.getElementById("cmp-grid");
    g.innerHTML = "";
    document.getElementById("cmp-count").textContent = "已载 " + cmpPaths.length + " 图 · 标记优 " + cmpPicked.length;
    cmpPaths.forEach(function (p, i) {
      var c = document.createElement("div");
      c.className = "cmp" + (cmpPicked.indexOf(p) >= 0 ? " pick" : "");
      c.style.position = "relative";
      var img = document.createElement("img"); img.src = assetUrl(p);
      var t = document.createElement("div"); t.className = "t"; t.textContent = p.split("/").pop(); t.title = p;
      var rank = document.createElement("span"); rank.className = "rank"; rank.textContent = cmpPicked.indexOf(p) >= 0 ? (cmpPicked.indexOf(p) + 1) : (i + 1);
      c.appendChild(img); c.appendChild(t); c.appendChild(rank);
      c.addEventListener("click", function () {
        var k = cmpPicked.indexOf(p);
        if (k >= 0) cmpPicked.splice(k, 1); else cmpPicked.push(p);
        renderCompare();
      });
      g.appendChild(c);
    });
    var r = document.getElementById("cmp-result");
    if (cmpPicked.length >= 2) {
      r.innerHTML = "你标记的优先级：" + cmpPicked.map(function (p) { return "<code>" + p.split("/").pop() + "</code>"; }).join(" → ");
    } else { r.innerHTML = ""; }
  }

  /* ===== 批量上传评分 ===== */
  function runBatch(files) {
    if (!files || !files.length) return;
    var st = document.getElementById("sc-state");
    var prog = document.getElementById("sc-progress");
    var grid = document.getElementById("sc-grid");
    grid.innerHTML = "";
    st.textContent = "上传 " + files.length + " 文件...";
    API.assetsUploadBatch(files).then(function (up) {
      prog.textContent = "上传完成 ok=" + up.ok + " fail=" + up.fail;
      var paths = up.results.filter(function (r) { return r.ok; }).map(function (r) { return r.path; });
      if (!paths.length) { st.textContent = "无有效图片"; return; }
      st.textContent = "评分 " + paths.length + " 图...";
      return API.scoreBatch(paths);
    }).then(function (sc) {
      if (!sc) return;
      st.textContent = "评分完成 平均 " + sc.avg_total;
      sc.items.forEach(function (it) {
        var c = document.createElement("div"); c.className = "card";
        var img = document.createElement("img"); img.src = assetUrl(it.path);
        var m = document.createElement("div"); m.className = "meta";
        var b = document.createElement("b"); b.textContent = it.path.split("/").pop();
        var sc2 = document.createElement("span"); sc2.className = "score";
        sc2.textContent = it.total != null ? it.total.toFixed(1) : (it.error || "err");
        m.appendChild(b);
        c.appendChild(img); c.appendChild(m); c.appendChild(sc2);
        grid.appendChild(c);
      });
    }).catch(function (e) { st.textContent = e.code + ": " + e.message; });
  }

  /* ===== toast ===== */
  function toast(msg) {
    var t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;bottom:18px;right:18px;z-index:10001;padding:10px 16px;border-radius:8px;background:#1a1f2c;border:1px solid var(--red);color:#ffc2c8;font-size:13px;max-width:420px;";
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  }

  function init() {
    bindTabs();
    var si = document.getElementById("lib-search");
    var ss = document.getElementById("lib-sort");
    var so = document.getElementById("lib-order");
    if (si) si.addEventListener("input", debounce(loadLibrary, 300));
    if (ss) ss.addEventListener("change", loadLibrary);
    if (so) so.addEventListener("change", loadLibrary);
    var rf = document.getElementById("lib-refresh"); if (rf) rf.addEventListener("click", loadLibrary);
    var cl = document.getElementById("cmp-load"); if (cl) cl.addEventListener("click", function () {
      var inp = document.getElementById("cmp-input");
      var paths = [];
      Array.prototype.forEach.call(inp.files, function (f) {
        var p = prompt("该文件已本地，需先上传以参与比对。输入已存在素材路径或留空跳上传：");
        if (p) paths.push(p);
      });
      if (paths.length) addComparePaths(paths);
    });
    var cc = document.getElementById("cmp-clear"); if (cc) cc.addEventListener("click", function () { cmpPaths = []; cmpPicked = []; renderCompare(); });
    var sg = document.getElementById("sc-go"); if (sg) sg.addEventListener("click", function () { runBatch(document.getElementById("sc-dir").files); });
    var sc = document.getElementById("sc-clear"); if (sc) sc.addEventListener("click", function () { document.getElementById("sc-dir").value = ""; document.getElementById("sc-grid").innerHTML = ""; });
    toast("增强面板已就绪：素材库 / 多图比对 / 批量评分");
  }

  function debounce(fn, ms) {
    var t = null;
    return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); };
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", init); } else { init(); }
})();
