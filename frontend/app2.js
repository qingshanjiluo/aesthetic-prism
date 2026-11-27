// Aesthetic Prism 增强视图主控（标签切换 + 素材库 + 多图比对 + 批量上传评分）
// 依赖 api.js；兼容现有 app.js（只操作 view-home，不冲突）。
"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var VIEWS = ["home", "library", "compare", "score", "wallet", "shop", "space", "compute", "annotate"];
  var cmpPaths = [];      // 比对视图已载入路径
  var cmpPicked = [];     // 比对标记优的路径
  var cmpScores = {};     // 比对评分缓存 {path: {total, composition, light, creativity, story}}
  var libSel = {};        // 素材库多选 {path:1}
  var libPage = 0;       // 素材库当前页（0-based）
  var libPageSize = 20;  // 每页张数
  var libAllItems = [];   // 全量列表缓存（用于随机抽与分页）
  var libAllTotal = 0;    // 全量 total
  var annMap = {};         // 素材库标注状态 {path: {total,...}}
  var annPending = [];     // 标注工作台当前待标注图 [{path,name}]
  var annBound = false;    // 标注页按钮是否已绑定

  function switchView(name) {
    VIEWS.forEach(function (v) {
      var el = document.getElementById("view-" + v);
      if (el) el.hidden = (v !== name);
    });
    var tabs = document.querySelectorAll("#app-tabs .tab");
    Array.prototype.forEach.call(tabs, function (t) {
      t.classList.toggle("active", t.getAttribute("data-view") === name);
    });
    window.scrollTo({ top: 0, behavior: "instant" });
    if (name === "library") loadLibrary();
    if (name === "compare") renderCompare();
    if (name === "annotate") initAnnotate();
    if (name === "wallet") renderWallet();
    if (name === "shop") renderShop();
    if (name === "space") renderSpace();
    if (name === "compute") renderCompute();
  }

  function bindTabs() {
    var tabs = document.querySelectorAll("#app-tabs .tab");
    Array.prototype.forEach.call(tabs, function (t) {
      t.addEventListener("click", function () { switchView(t.getAttribute("data-view")); });
    });
  }

  /* ===== 素材库（分页）===== */
  function loadLibrary(page) {
    if (page !== undefined) libPage = page;
    var q = document.getElementById("lib-search").value;
    var sort = document.getElementById("lib-sort").value;
    var order = document.getElementById("lib-order").value;
    var offset = libPage * libPageSize;
    var params = { limit: libPageSize, offset: offset, sort: sort, order: order };
    if (q) params.q = q;
    // 加载素材 + 已标注 path 集合（并行）
    var pAssets = API.assets(params);
    var pAnn = API.annotations({ limit: 5000 });
    Promise.all([pAssets, pAnn]).then(function (res) {
      var d = res[0], ad = res[1];
      annMap = {};
      (ad.items || []).forEach(function (a) { annMap[a.path] = a; });
      var grid = document.getElementById("lib-grid");
      grid.innerHTML = "";
      var totalPages = Math.max(1, Math.ceil(d.total / libPageSize));
      if (libPage > totalPages - 1) { libPage = totalPages - 1; loadLibrary(libPage); return; }
      document.getElementById("lib-count").textContent = "共 " + d.total + " 个素材";
      document.getElementById("lib-page-info").textContent = "第 " + (libPage + 1) + " / " + totalPages + " 页 · 本页 " + d.items.length + " 张";
      document.getElementById("lib-prev").disabled = libPage <= 0;
      document.getElementById("lib-next").disabled = libPage >= totalPages - 1;
      d.items.forEach(function (it) {
        var c = document.createElement("div");
        c.className = "card" + (libSel[it.path] ? " selected" : "");
        var img = document.createElement("img");
        img.src = assetUrl(it.path);
        img.loading = "lazy";
        img.onerror = function () { this.style.background = "var(--bg2)"; };
        var m = document.createElement("div"); m.className = "meta";
        var b = document.createElement("b"); b.textContent = it.filename; b.title = it.path;
        var s = document.createElement("div"); s.textContent = fmtSize(it.bytes) + " · " + it.mime.split("/")[1];
        m.appendChild(b); m.appendChild(s);
        if (it.tags && it.tags.length) { var tg = document.createElement("div"); tg.textContent = "#" + it.tags.join(" #"); tg.style.color = "var(--accent)"; m.appendChild(tg); }
        if (annMap[it.path]) { var am = document.createElement("div"); am.textContent = "✓ 已标注 " + annMap[it.path].total.toFixed(1); am.style.cssText = "font-size:10.5px;color:var(--green);margin-top:3px"; m.appendChild(am); }
        else { var pm = document.createElement("div"); pm.textContent = "待标注"; pm.style.cssText = "font-size:10.5px;color:var(--muted);margin-top:3px"; m.appendChild(pm); }
        c.appendChild(img); c.appendChild(m);
        c.addEventListener("click", function (e) {
          if (e.ctrlKey || e.metaKey) { libSel[it.path] = libSel[it.path] ? 0 : 1; c.classList.toggle("selected", !!libSel[it.path]); }
          else { openLightbox(it.path, it.filename); }
        });
        grid.appendChild(c);
      });
    }).catch(function (e) { toast(e.code + ": " + e.message); });
  }

  function fetchAllAssets() {
    var sort = document.getElementById("lib-sort").value;
    var order = document.getElementById("lib-order").value;
    var q = document.getElementById("lib-search").value;
    var params = { limit: 5000, sort: sort, order: order };
    if (q) params.q = q;
    return API.assets(params).then(function (d) {
      libAllItems = d.items;
      libAllTotal = d.total;
      return d;
    });
  }

  /* ===== 随机抽取 N 张 → 比对 ===== */
  function randomDrawToCompare(n) {
    fetchAllAssets().then(function (d) {
      var pool = d.items;
      if (pool.length < 2) { toast("素材库不足 2 张，无法随机抽取"); return; }
      // Fisher-Yates 部分洗牌取前 n
      var arr = pool.slice();
      var take = Math.min(n, arr.length);
      for (var i = 0; i < take; i++) {
        var j = i + Math.floor(Math.random() * (arr.length - i));
        var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
      }
      var picked = arr.slice(0, take);
      var paths = picked.map(function (it) { return it.path; });
      // 清掉旧的比对缓存再载入
      cmpPaths = paths;
      cmpPicked = [];
      cmpScores = {};
      switchView("compare");
      toast("已从 " + libAllTotal + " 张中随机抽 " + take + " 张");
    }).catch(function (e) { toast("抽取失败: " + e.message); });
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

  /* ===== 素材库批量操作 ===== */
  function selPaths() {
    var out = [];
    Object.keys(libSel).forEach(function (p) { if (libSel[p]) out.push(p); });
    return out;
  }
  function delSelectedLibrary() {
    var paths = selPaths();
    if (!paths.length) { toast("请先用 Ctrl+点击 选择要删除的素材"); return; }
    confirmDialog("确定删除 " + paths.length + " 个素材？此操作不可恢复").then(function (ok) {
      if (!ok) return;
      API.assetsDelete(paths).then(function (d) {
        toast("已删除 " + d.deleted + " 个素材");
        libSel = {};
        loadLibrary();
      }).catch(function (e) { toast("删除失败: " + e.message); });
    });
  }
  function addSelectedToCompare() {
    var paths = selPaths();
    if (!paths.length) { toast("请先用 Ctrl+点击 选择要加入比对的素材"); return; }
    addComparePaths(paths);
    switchView("compare");
    toast("已加入 " + paths.length + " 图到比对");
  }

   /* ===== 数据标注 ===== */
  var ANN_DIMS = [
    { key: "composition", label: "构图" },
    { key: "light", label: "光效" },
    { key: "creativity", label: "创意" },
    { key: "story", label: "叙事" }
  ];
  var ANN_QUALITY = ["可用", "不可用", "模糊", "水印"];

  function initAnnotate() {
    if (!annBound) { bindAnnotate(); annBound = true; }
    renderAnnList();
  }

  function bindAnnotate() {
    var rn = document.getElementById("ann-random");
    if (rn) rn.addEventListener("click", function () {
      var n = parseInt(document.getElementById("ann-random-n").value, 10) || 4;
      annRandomPending(n);
    });
    var ec = document.getElementById("ann-export");
    if (ec) ec.addEventListener("click", function () { annExport("csv"); });
    var ej = document.getElementById("ann-export-jsonl");
    if (ej) ej.addEventListener("click", function () { annExport("jsonl"); });
    var tr = document.getElementById("ann-train");
    if (tr) tr.addEventListener("click", annImportToTrain);
    document.addEventListener("keydown", function (e) {
      var view = document.getElementById("view-annotate");
      if (!view || view.hidden) return;
      if (document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA")) return;
      var cards = document.querySelectorAll("#ann-work .ann-card");
      if (!cards.length) return;
      var cur = document.querySelector("#ann-work .ann-card.focus") || cards[0];
      if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        var it = annPending[Array.from(cards).indexOf(cur)];
        if (it) annSave(it, cur);
      } else if (e.key === "Escape") {
        e.preventDefault();
        var idx = Array.from(cards).indexOf(cur);
        if (idx >= 0) { annPending.splice(idx, 1); renderAnnWork(); }
      }
    });
  }

  function annRandomPending(n) {
    API.assets({ limit: 5000, sort: "mtime", order: "desc" }).then(function (d) {
      var ann = new Set();
      var prefill = {};
      API.annotations({ limit: 5000 }).then(function (ad) {
        (ad.items || []).forEach(function (a) { ann.add(a.path); prefill[a.path] = a; });
        var unannotated = d.items.filter(function (it) { return !ann.has(it.path); });
        if (unannotated.length === 0) { toast("全部素材已标注"); return; }
        var pool = unannotated.slice();
        var take = Math.min(n, pool.length);
        for (var i = 0; i < take; i++) {
          var j = i + Math.floor(Math.random() * (pool.length - i));
          var tmp = pool[i]; pool[i] = pool[j]; pool[j] = tmp;
        }
        annPending = pool.slice(0, take).map(function (it) {
          var obj = { path: it.path, name: it.filename };
          if (prefill[it.path]) obj.existing = prefill[it.path];
          return obj;
        });
        renderAnnWork();
        toast("已抽 " + take + " 张待标注");
      });
    }).catch(function (e) { toast("抽取失败: " + e.message); });
  }

  function renderAnnWork() {
    var w = document.getElementById("ann-work");
    w.innerHTML = "";
    if (!annPending.length) { w.innerHTML = '<div class="ann-empty">暂无待标注图，点「随机抽 N 张待标注」开始</div>'; return; }
    annPending.forEach(function (it, idx) {
      var card = document.createElement("div");
      card.className = "ann-card";
      var img = document.createElement("img");
      img.src = assetUrl(it.path);
      img.loading = "lazy";
      img.onerror = function () { this.style.background = "var(--bg2)"; };
      card.appendChild(img);
      var body = document.createElement("div");
      body.className = "ann-body";
      var title = document.createElement("div");
      title.className = "ann-title";
      title.textContent = it.name;
      title.title = it.path;
      body.appendChild(title);

      var dims = document.createElement("div");
      dims.className = "ann-dims";
      ANN_DIMS.forEach(function (dm) {
        var row = document.createElement("div");
        row.className = "ann-dim";
        var lb = document.createElement("label");
        lb.textContent = dm.label;
        var slider = document.createElement("input");
        slider.type = "range";
        slider.className = "ann-slider";
        slider.min = "0";
        slider.max = "10";
        slider.step = "0.5";
        var initVal = it.existing ? (it.existing[dm.key] || 0) : 0;
        slider.value = String(initVal);
        slider.dataset.dim = dm.key;
        var val = document.createElement("span");
        val.className = "ann-val";
        val.textContent = Number(initVal).toFixed(1);
        slider.addEventListener("input", function () {
          val.textContent = Number(slider.value).toFixed(1);
          annRecalcTotal(card);
        });
        row.appendChild(lb);
        row.appendChild(slider);
        row.appendChild(val);
        dims.appendChild(row);
      });
      body.appendChild(dims);

      var q = document.createElement("div");
      q.className = "ann-quality";
      ANN_QUALITY.forEach(function (ql) {
        var b = document.createElement("button");
        b.textContent = ql;
        if (it.existing && it.existing.quality === ql) b.classList.add("on");
        b.addEventListener("click", function () {
          q.querySelectorAll("button").forEach(function (x) { x.classList.remove("on"); });
          b.classList.add("on");
        });
        q.appendChild(b);
      });
      body.appendChild(q);

      var note = document.createElement("textarea");
      note.className = "ann-note";
      note.placeholder = "备注（可选）";
      if (it.existing && it.existing.note) note.value = it.existing.note;
      body.appendChild(note);

      var acts = document.createElement("div");
      acts.className = "ann-actions";
      var save = document.createElement("button");
      save.className = "btn primary";
      save.textContent = "保存标注";
      save.addEventListener("click", function () { annSave(it, card); });
      var skip = document.createElement("button");
      skip.className = "btn ghost";
      skip.textContent = "跳过";
      skip.addEventListener("click", function () {
        annPending.splice(idx, 1);
        renderAnnWork();
      });
      var totalEl = document.createElement("span");
      totalEl.className = "ann-total";
      totalEl.textContent = "总分 0.0";
      acts.appendChild(save);
      acts.appendChild(skip);
      acts.appendChild(totalEl);
      body.appendChild(acts);
      card.appendChild(body);
      w.appendChild(card);
      annRecalcTotal(card);
    });
  }

  function annRecalcTotal(card) {
    var sliders = card.querySelectorAll(".ann-slider");
    var sum = 0, cnt = 0;
    sliders.forEach(function (s) {
      var v = parseFloat(s.value);
      if (!isNaN(v)) { sum += v; cnt++; }
    });
    var total = cnt ? (sum / cnt) : 0;
    var el = card.querySelector(".ann-total");
    if (el) el.textContent = "总分 " + total.toFixed(1);
  }

  function annSave(it, card) {
    var body = {};
    ANN_DIMS.forEach(function (dm) {
      var s = card.querySelector('.ann-slider[data-dim="' + dm.key + '"]');
      body[dm.key] = parseFloat(s.value) || 0;
    });
    body.total = ((body.composition + body.light + body.creativity + body.story) / 4);
    body.path = it.path;
    var qsel = card.querySelector(".ann-quality button.on");
    body.quality = qsel ? qsel.textContent : "";
    body.note = card.querySelector(".ann-note").value || "";
    body.annotator = "web";
    API.annotationSave(body).then(function (r) {
      toast("已保存 " + it.name + " 总分 " + r.total.toFixed(1));
      var idx = annPending.findIndex(function (p) { return p.path === it.path; });
      if (idx >= 0) annPending.splice(idx, 1);
      renderAnnWork();
      renderAnnList();
    }).catch(function (e) { toast("保存失败: " + e.message); });
  }

  function annExport(fmt) {
    API.annotationExport(fmt).then(function (d) {
      if (fmt === "csv") {
        var blob = new Blob([d.text], { type: "text/csv" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "annotations.csv";
        a.click();
      } else {
        var text = d.lines.join("\n");
        var blob = new Blob([text], { type: "application/jsonl" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "annotations.jsonl";
        a.click();
      }
      toast("已导出 " + d.count + " 条 " + fmt.toUpperCase());
    }).catch(function (e) { toast("导出失败: " + e.message); });
  }

  function annImportToTrain() {
    API.annotationExport("jsonl").then(function (d) {
      if (d.count < 2) { toast("至少 2 条标注才可导入训练"); return; }
      var paths = d.lines.map(function (l) { return JSON.parse(l).path; });
      toast("正在用 " + paths.length + " 张已标注图启动批量训练…");
      API.trainBatch(200, paths).then(function (r) {
        toast("训练任务已启动 " + (r.job_id || "ok"));
      }).catch(function (e) {
        toast("训练启动失败: " + e.message);
      });
    }).catch(function (e) { toast("导出失败: " + e.message); });
  }

  function renderAnnList() {
    API.annotations({ limit: 200 }).then(function (d) {
      document.getElementById("ann-count").textContent = "已标 " + d.total + " 条";
      var list = document.getElementById("ann-list");
      list.innerHTML = "";
      if (!d.items.length) { list.innerHTML = '<div class="ann-empty">暂无标注</div>'; return; }
      d.items.forEach(function (a) {
        var row = document.createElement("div");
        row.className = "ann-row";
        var p = document.createElement("div");
        p.className = "p";
        p.textContent = a.path;
        p.title = a.note || "";
        var ct = document.createElement("div");
        ct.className = "n";
        ct.textContent = a.composition.toFixed(1);
        var lt = document.createElement("div");
        lt.className = "n";
        lt.textContent = a.light.toFixed(1);
        var qt = document.createElement("div");
        qt.className = "q";
        var chip = document.createElement("span");
        chip.className = "chip" + (a.quality ? " " + a.quality : "");
        chip.textContent = a.quality || "—";
        qt.appendChild(chip);
        var del = document.createElement("button");
        del.textContent = "✕";
        del.title = "删除";
        del.addEventListener("click", function () {
          API.annotationDelete(a.path).then(function () {
            toast("已删除 " + a.path);
            renderAnnList();
            if (typeof loadLibrary === "function") loadLibrary(libPage);
          }).catch(function (e) { toast("删除失败: " + e.message); });
        });
        row.appendChild(p);
        row.appendChild(ct);
        row.appendChild(lt);
        row.appendChild(qt);
        row.appendChild(del);
        list.appendChild(row);
      });
    }).catch(function (e) { toast(e.message); });
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
      img.style.height = "220px";
      img.style.cursor = "zoom-in";
      img.addEventListener("click", function (e) {
        e.stopPropagation();
        openLightbox(p, p.split("/").pop());
      });
      var t = document.createElement("div"); t.className = "t"; t.textContent = (i + 1) + ". " + p.split("/").pop(); t.title = p;
      var rank = document.createElement("span"); rank.className = "rank"; rank.textContent = cmpPicked.indexOf(p) >= 0 ? (cmpPicked.indexOf(p) + 1) : (i + 1);
      var scBadge = document.createElement("span"); scBadge.className = "score";
      if (cmpScores[p] && cmpScores[p].total != null) scBadge.textContent = cmpScores[p].total.toFixed(1);
      var rm = document.createElement("button");
      rm.textContent = "✕";
      rm.style.cssText = "position:absolute;top:4px;right:4px;z-index:3;width:22px;height:22px;border-radius:50%;border:1px solid var(--line2);background:rgba(0,0,0,.7);color:#fff;cursor:pointer;";
      rm.addEventListener("click", function (e) {
        e.stopPropagation();
        var k = cmpPaths.indexOf(p); if (k >= 0) cmpPaths.splice(k, 1);
        var j = cmpPicked.indexOf(p); if (j >= 0) cmpPicked.splice(j, 1);
        renderCompare();
      });
      c.appendChild(rm); c.appendChild(img); c.appendChild(t); c.appendChild(rank); c.appendChild(scBadge);
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
  var DIM_LABELS = { composition: "构图", light: "光效", creativity: "创意", story: "叙事" };
  function scoreCompare() {
    if (cmpPaths.length < 2) { toast("比对需至少 2 图"); return; }
    var btn = document.getElementById("cmp-score");
    if (btn) { btn.disabled = true; btn.textContent = "评分中…"; }
    API.scoreBatch(cmpPaths).then(function (sc) {
      if (btn) { btn.disabled = false; btn.textContent = "评分对比"; }
      cmpScores = {};
      sc.items.forEach(function (it) {
        if (it.total != null) cmpScores[it.path] = it;
      });
      // 排序 = 按总分降序
      var ranked = cmpPaths.slice().sort(function (a, b) {
        var sa = cmpScores[a], sb = cmpScores[b];
        return (sb ? sb.total : -1) - (sa ? sa.total : -1);
      });
      cmpPicked = ranked;
      renderCompare();
      // ---- 结果区：总分 + 维度明细表 ----
      var lines = sc.items.map(function (it) {
        if (it.total != null) return "<div><b>" + it.total.toFixed(1) + "</b> · " + it.path.split("/").pop() + "</div>";
        return "<div>" + (it.error || "err") + " · " + it.path.split("/").pop() + "</div>";
      }).join("");
      document.getElementById("cmp-result").innerHTML = "<b>评分对比（按总分排序）：</b><div style='margin-top:8px'>" + lines + "</div>";
      // ---- 维度明细表 ----
      var v = document.getElementById("cmp-verdict");
      if (v) {
        var scored = sc.items.filter(function (it) { return it.total != null; }).sort(function (a, b) { return b.total - a.total; });
        if (scored.length >= 2) {
          var winner = scored[0];
          var runnerUp = scored[1];
          // 维度表
          var dimKeys = ["composition", "light", "creativity", "story"];
          var tbl = "<table style='border-collapse:collapse;margin-top:10px;width:100%'>";
          tbl += "<thead><tr style='border-bottom:2px solid var(--line)'><th style='text-align:left;padding:6px 8px;font-size:12px;color:var(--muted)'>维度</th>";
          scored.forEach(function (it, i) {
            var tag = i === 0 ? " <span style='color:var(--green);font-weight:600'>★优</span>" : (i === 1 ? " <span style='color:var(--yellow)'>次</span>" : "");
            tbl += "<th style='padding:6px 8px;font-size:12px;text-align:right'>" + (i + 1) + ". " + it.path.split("/").pop() + tag + "</th>";
          });
          tbl += "</tr></thead><tbody>";
          dimKeys.forEach(function (dk) {
            tbl += "<tr style='border-bottom:1px solid var(--line)'><td style='padding:5px 8px;font-size:13px;color:var(--txt2)'>" + DIM_LABELS[dk] + "</td>";
            scored.forEach(function (it) {
              var val = it[dk] != null ? it[dk].toFixed(1) : "-";
              var isMax = false;
              var mx = -Infinity; scored.forEach(function (o) { if (o[dk] != null && o[dk] > mx) mx = o[dk]; });
              if (it[dk] != null && it[dk] === mx) isMax = true;
              tbl += "<td style='padding:5px 8px;font-size:13px;text-align:right;font-family:var(--mono)" + (isMax ? ";color:var(--green);font-weight:600" : "") + "'>" + val + "</td>";
            });
            tbl += "</tr>";
          });
          tbl += "</tbody></table>";
          // 结论
          var bestDim = dimKeys.reduce(function (acc, k) {
            var diff = (winner[k] || 0) - (runnerUp[k] || 0);
            if (diff > (acc.diff || -99)) return { key: k, diff: diff };
            return acc;
          }, { key: null, diff: 0 });
          var gap = (winner.total - runnerUp.total).toFixed(1);
          var verdict = "<div style='margin-top:16px;padding:14px 16px;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--bg2)'>";
          verdict += "<b style='font-size:15px'>结论</b>";
          verdict += "<p style='margin:8px 0;font-size:14px;color:var(--txt2)'>";
          verdict += "<b style='color:var(--green)'>" + winner.path.split("/").pop() + "</b> 综合最优（" + winner.total.toFixed(1) + " 分），领先第二名 " + gap + " 分。";
          verdict += "</p><ul style='margin:6px 0 0 18px;padding:0;font-size:13px;color:var(--txt2);line-height:1.9'>";
          dimKeys.forEach(function (dk) {
            var wv = winner[dk] != null ? winner[dk].toFixed(1) : "-";
            var lv = runnerUp[dk] != null ? runnerUp[dk].toFixed(1) : "-";
            var d = (winner[dk] != null && runnerUp[dk] != null) ? (winner[dk] - runnerUp[dk]).toFixed(1) : "";
            var cls = (winner[dk] != null && runnerUp[dk] != null && winner[dk] > runnerUp[dk]) ? "color:var(--green)" : (winner[dk] != null && runnerUp[dk] != null && winner[dk] < runnerUp[dk] ? "color:var(--red)" : "");
            verdict += "<li>" + DIM_LABELS[dk] + "：最优 " + wv + " vs 次优 " + lv + (d ? "（差 " + d + "）" : "") + "</li>";
          });
          if (bestDim.key) {
            verdict += "<li style='margin-top:6px;padding:4px 0;border-top:1px solid var(--line)'><b style='color:var(--accent)'>训练建议</b>：" + DIM_LABELS[bestDim.key] + " 是最大优势维度（领先 " + bestDim.diff.toFixed(1) + " 分），可作为训练标注的正样本依据；" +
              "建议对「" + DIM_LABELS[bestDim.key] + "」维度权重上调后重训，观察 val/test 指标变化。</li>";
          }
          verdict += "</ul></div>";
          v.innerHTML = tbl + verdict;
        } else {
          v.innerHTML = "";
        }
      }
      toast("评分完成 平均 " + sc.avg_total);
    }).catch(function (e) {
      if (btn) { btn.disabled = false; btn.textContent = "评分对比"; }
      toast("评分失败: " + e.message);
    });
  }

  function genSamples() {
    inputDialog("自动生成合成图", "生成多少张合成训练图？(1-500)", "20").then(function (r) {
      if (!r.ok) return;
      var n = parseInt(r.value, 10);
      if (!n || n < 1 || n > 500) { toast("n 须在 1-500"); return; }
      var st = document.getElementById("sc-state");
      st.textContent = "正在生成 " + n + " 张合成图...";
      API.samplesGenerate(n).then(function (d) {
        st.textContent = "已生成 " + d.generated + " 张，素材库共 " + d.total + " 张";
        toast("自动生成完成：" + d.generated + " 张");
        loadLibrary();
      }).catch(function (e) { st.textContent = "生成失败: " + e.message; });
    });
  }

  /* ===== 批量上传评分 ===== */
  function runBatch(files) {
    if (!files || !files.length) return;
    var st = document.getElementById("sc-state");
    var prog = document.getElementById("sc-progress");
    var grid = document.getElementById("sc-grid");
    var go = document.getElementById("sc-go");
    grid.innerHTML = "";
    var running = false;
    function setBusy(b) {
      running = b;
      if (go) go.disabled = b;
      if (go) go.textContent = b ? "处理中..." : "上传并评分";
    }
    setBusy(true);
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
    }).catch(function (e) { st.textContent = e.code + ": " + e.message; })
    .then(function () { setBusy(false); });
  }

  /* ===== toast ===== */
  function toast(msg) {
    var t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;bottom:18px;right:18px;z-index:10001;padding:10px 16px;border-radius:8px;background:#1a1f2c;border:1px solid var(--red);color:#ffc2c8;font-size:13px;max-width:420px;";
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  }

  /* ===== 自定义 modal ===== */
  // modal(opts): {title, body, ok, cancel, value} 返回 Promise<{ok:bool, value?:string}>
  function modal(opts) {
    var m = document.getElementById("ap-modal");
    if (!m) { return Promise.resolve({ ok: true }); }
    document.getElementById("ap-modal-title").textContent = opts.title || "";
    var body = document.getElementById("ap-modal-body");
    body.innerHTML = "";
    if (opts.message) {
      var p = document.createElement("div");
      p.textContent = opts.message;
      body.appendChild(p);
    }
    var input = null;
    if (opts.value !== undefined) {
      input = document.createElement("input");
      input.type = "text";
      input.value = opts.value;
      body.appendChild(input);
    }
    var okBtn = document.getElementById("ap-modal-ok");
    var cancelBtn = document.getElementById("ap-modal-cancel");
    okBtn.textContent = opts.ok || "确定";
    cancelBtn.textContent = opts.cancel || "取消";
    if (opts.okOnly) cancelBtn.style.display = "none"; else cancelBtn.style.display = "";
    m.hidden = false;
    if (input) setTimeout(function () { input.focus(); input.select(); }, 20);
    return new Promise(function (resolve) {
      function done(ok) {
        m.hidden = true;
        okBtn.onclick = null; cancelBtn.onclick = null;
        resolve({ ok: ok, value: input ? input.value : undefined });
      }
      okBtn.onclick = function () { done(true); };
      cancelBtn.onclick = function () { done(false); };
      m.querySelector(".ap-modal-mask").onclick = function () { done(false); };
    });
  }
  function confirmDialog(msg) {
    return modal({ title: "确认", message: msg, ok: "确定", cancel: "取消" }).then(function (r) { return r.ok; });
  }
  function inputDialog(title, msg, def) {
    return modal({ title: title, message: msg, value: def, ok: "确定", cancel: "取消" }).then(function (r) { return r; });
  }

  /* ===== 模型管理 ===== */
  var currentModel = null;
  function loadModels() {
    API.models().then(function (d) {
      var sel = document.getElementById("model-select");
      if (!sel) return;
      sel.innerHTML = "";
      d.items.forEach(function (it) {
        var o = document.createElement("option");
        o.value = it.path;
        o.textContent = it.name + (it.category ? " · " + it.category : "") + (it.active ? " (当前)" : "");
        if (it.active) o.selected = true;
        sel.appendChild(o);
      });
      currentModel = d.active_model;
      showModelMeta(d.items);
      renderModelList(d.items);
    }).catch(function (e) { toast("模型加载失败: " + e.message); });
  }
  function showModelMeta(items) {
    var path = document.getElementById("model-select").value;
    var it = null;
    items.forEach(function (i) { if (i.path === path) it = i; });
    if (!it) return;
    document.getElementById("m-name").textContent = it.name;
    document.getElementById("m-category").textContent = it.category || "-";
    document.getElementById("m-tags").textContent = (it.tags && it.tags.length) ? it.tags.join(", ") : "-";
    document.getElementById("mm-name").value = it.name;
    document.getElementById("mm-category").value = it.category || "";
    document.getElementById("mm-tags").value = (it.tags || []).join(", ");
  }
  function renderModelList(items) {
    var list = document.getElementById("mm-list");
    if (!list) return;
    list.innerHTML = "";
    items.forEach(function (it) {
      var row = document.createElement("div");
      row.textContent = it.path + "  →  " + it.name + (it.category ? " [" + it.category + "]" : "") + (it.active ? " ★" : "");
      list.appendChild(row);
    });
  }
  function initModels() {
    loadModels();
    var sel = document.getElementById("model-select");
    if (sel) sel.addEventListener("change", function () {
      // 重取当前选中模型元数据
      API.models().then(function (d) {
        var it = null;
        d.items.forEach(function (i) { if (i.path === sel.value) it = i; });
        if (it) { currentModel = it.path; showModelMeta(d.items); }
      });
    });
    var mb = document.getElementById("model-manage-btn");
    if (mb) mb.addEventListener("click", function () {
      var p = document.getElementById("model-manage-panel");
      p.hidden = !p.hidden;
    });
    var sv = document.getElementById("mm-save");
    if (sv) sv.addEventListener("click", function () {
      var path = document.getElementById("model-select").value;
      var name = document.getElementById("mm-name").value;
      var cat = document.getElementById("mm-category").value;
      var tags = document.getElementById("mm-tags").value.split(/[,，\s]+/).filter(Boolean);
      API.modelsMeta(path, { name: name, category: cat, tags: tags }).then(function () {
        toast("模型元数据已保存");
        loadModels();
      }).catch(function (e) { toast("保存失败: " + e.message); });
    });
  }

  /* ===== 认证 ===== */
  function initAuth() {
    var lv = document.getElementById("login-view");
    if (!lv) return;
    // 模式切换
    var tabL = document.getElementById("tab-login");
    var tabR = document.getElementById("tab-register");
    var btn = document.getElementById("login-btn");
    var err = document.getElementById("login-err");
    var mode = "login";
    function showErr(m) { err.textContent = m; err.classList.add("show"); }
    function hideErr() { err.classList.remove("show"); }
    function setMode(m) {
      mode = m;
      if (tabL) tabL.classList.toggle("active", m === "login");
      if (tabR) tabR.classList.toggle("active", m === "register");
      if (btn) btn.textContent = m === "login" ? "登录" : "注册";
      hideErr();
    }
    if (tabL) tabL.addEventListener("click", function () { setMode("login"); });
    if (tabR) tabR.addEventListener("click", function () { setMode("register"); });
    if (btn) btn.addEventListener("click", function () {
      var u = document.getElementById("login-username").value.trim();
      var p = document.getElementById("login-password").value;
      if (!u || u.length < 3) { showErr("用户名至少 3 个字符"); return; }
      if (!p || p.length < 6) { showErr("密码至少 6 个字符"); return; }
      var call = mode === "login" ? API.login(u, p) : API.register(u, p);
      call.then(function (r) {
        if (mode === "login") {
          AUTH.setToken(r.token);
          hideErr();
          lv.hidden = true;
          refreshBalance();
        } else {
          setMode("login");
          showErr("注册成功，请登录");
        }
      }).catch(function (e) { showErr(e.message || e.code); });
    });
    // 已登录则隐藏登录页
    if (AUTH.isAuthed()) { lv.hidden = true; refreshBalance(); }
    // 登出按钮
    var lo = document.getElementById("logout-btn");
    if (lo) lo.addEventListener("click", function () { AUTH.clear(); location.reload(); });
  }
  function refreshBalance() {
    if (!AUTH.isAuthed()) return;
    API.wallet().then(function (w) {
      var b = document.getElementById("balance-badge");
      if (b) b.textContent = "积分 " + w.balance + " · 空间 " + fmtSize(w.space_bytes);
    }).catch(function () {});
  }

  function renderWallet() {
    if (!AUTH.isAuthed()) { toast("请先登录"); return; }
    API.wallet().then(function (w) {
      document.getElementById("wal-bal").textContent = w.balance;
      document.getElementById("wal-space").textContent = fmtSize(w.space_bytes);
    }).catch(function (e) { toast(e.message); });
    API.ledger(30).then(function (d) {
      var el = document.getElementById("wal-ledger-list");
      el.innerHTML = (d.items || []).map(function (r) {
        return "<div>" + (r.amount > 0 ? "+" : "") + r.amount + " · " + r.kind + " · " + r.item + " · " + r.ts + "</div>";
      }).join("") || "暂无流水";
    }).catch(function () {});
  }
  function renderShop() {
    if (!AUTH.isAuthed()) { toast("请先登录"); return; }
    API.shop().then(function (d) {
      var g = document.getElementById("shop-grid");
      g.innerHTML = "";
      var items = d.items || [];
      if (!items.length) { g.innerHTML = '<div class="muted" style="padding:20px">暂无可用模型</div>'; return; }
      items.forEach(function (it) {
        var c = document.createElement("div"); c.className = "card";
        var t = document.createElement("b"); t.textContent = it.model_id.split("/").pop(); t.style.display = "block";
        var p = document.createElement("div"); p.className = "meta"; p.textContent = it.model_id + " · " + it.price + " 积分";
        var b = document.createElement("button"); b.className = "btn primary"; b.textContent = it.owned ? "已拥有" : "购买 " + it.price;
        b.disabled = it.owned;
        b.style.cssText = "margin:10px;width:calc(100% - 20px)";
        b.addEventListener("click", function () {
          API.buy(it.model_id).then(function (r) { toast(r.already ? "已拥有" : "购买成功，扣 " + it.price + " 积分"); renderShop(); refreshBalance(); }).catch(function (e) { toast(e.message); });
        });
        c.appendChild(t); c.appendChild(p); c.appendChild(b);
        g.appendChild(c);
      });
    }).catch(function (e) { toast(e.message); });
  }
  function renderSpace() {
    if (!AUTH.isAuthed()) { toast("请先登录"); return; }
    API.wallet().then(function (w) { document.getElementById("space-now").textContent = fmtSize(w.space_bytes); }).catch(function (e) { toast(e.message); });
  }
  function renderCompute() {
    if (!AUTH.isAuthed()) { toast("请先登录"); return; }
  }
  function bindCommercial() {
    var wr = document.getElementById("wal-recharge-btn");
    if (wr) wr.addEventListener("click", function () {
      var a = parseInt(document.getElementById("wal-recharge-amt").value, 10);
      if (!a || a <= 0) { toast("输入有效积分"); return; }
      var b = wr; b.disabled = true;
      API.recharge(a).then(function (r) { toast("充值成功，余额 " + r.balance); renderWallet(); refreshBalance(); }).catch(function (e) { toast(e.message); }).then(function () { b.disabled = false; });
    });
    var se = document.getElementById("space-expand-btn");
    if (se) se.addEventListener("click", function () {
      var gb = parseInt(document.getElementById("space-gb").value, 10);
      if (!gb || gb < 1) { toast("输入有效 GB"); return; }
      API.spaceExpand(gb).then(function (r) { toast("扩容成功，空间 " + fmtSize(r.space_bytes)); renderSpace(); refreshBalance(); }).catch(function (e) { toast(e.message); });
    });
    var cg = document.getElementById("compute-go");
    if (cg) cg.addEventListener("click", function () {
      var tier = parseInt(document.getElementById("compute-tier").value, 10);
      API.compute(tier).then(function (r) { document.getElementById("compute-result").textContent = JSON.stringify(r, null, 2); refreshBalance(); }).catch(function (e) { document.getElementById("compute-result").textContent = "错误: " + e.message; });
    });
  }

  function init() {
    initAuth();
    bindCommercial();
    bindTabs();
    initModels();
    var si = document.getElementById("lib-search");
    var ss = document.getElementById("lib-sort");
    var so = document.getElementById("lib-order");
    if (si) si.addEventListener("input", debounce(function () { libPage = 0; loadLibrary(); }, 300));
    if (ss) ss.addEventListener("change", function () { libPage = 0; loadLibrary(); });
    if (so) so.addEventListener("change", function () { libPage = 0; loadLibrary(); });
    var rf = document.getElementById("lib-refresh"); if (rf) rf.addEventListener("click", function () { libPage = 0; loadLibrary(); });
    var ds = document.getElementById("lib-del-sel"); if (ds) ds.addEventListener("click", delSelectedLibrary);
    var ac = document.getElementById("lib-add-compare"); if (ac) ac.addEventListener("click", addSelectedToCompare);
    var lr = document.getElementById("lib-random"); if (lr) lr.addEventListener("click", function () {
      var n = parseInt(document.getElementById("lib-random-n").value, 10) || 4;
      randomDrawToCompare(n);
    });
    var lp = document.getElementById("lib-prev"); if (lp) lp.addEventListener("click", function () { if (libPage > 0) loadLibrary(libPage - 1); });
    var ln = document.getElementById("lib-next"); if (ln) ln.addEventListener("click", function () { loadLibrary(libPage + 1); });
    var cl = document.getElementById("cmp-load"); if (cl) cl.addEventListener("click", function () {
      var inp = document.getElementById("cmp-input");
      if (!inp.files || !inp.files.length) { toast("请先选择要加入比对的图片"); return; }
      toast("正在上传 " + inp.files.length + " 图到素材库...");
      API.assetsUploadBatch(inp.files).then(function (up) {
        var paths = up.results.filter(function (r) { return r.ok; }).map(function (r) { return r.path; });
        if (!paths.length) { toast("上传失败：" + up.fail + " 个文件无效"); return; }
        addComparePaths(paths);
        inp.value = "";
        toast("已上传并加入 " + paths.length + " 图到比对");
      }).catch(function (e) { toast("上传失败: " + e.message); });
    });
    var cc = document.getElementById("cmp-clear"); if (cc) cc.addEventListener("click", function () { cmpPaths = []; cmpPicked = []; cmpScores = {}; renderCompare(); });
    var cr = document.getElementById("cmp-random"); if (cr) cr.addEventListener("click", function () {
      var n = 4;
      randomDrawToCompare(n);
    });
    var cs = document.getElementById("cmp-score"); if (cs) cs.addEventListener("click", scoreCompare);
    var sg = document.getElementById("sc-go"); if (sg) sg.addEventListener("click", function () { runBatch(document.getElementById("sc-dir").files); });
    var sc = document.getElementById("sc-clear"); if (sc) sc.addEventListener("click", function () { document.getElementById("sc-dir").value = ""; document.getElementById("sc-grid").innerHTML = ""; });
    var sg2 = document.getElementById("sc-gen"); if (sg2) sg2.addEventListener("click", genSamples);
    toast("增强面板已就绪：素材库 / 多图比对 / 批量评分");
  }

  function debounce(fn, ms) {
    var t = null;
    return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); };
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", init); } else { init(); }
})();
