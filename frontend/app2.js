// Aesthetic Prism 增强视图主控（标签切换 + 素材库 + 多图比对 + 批量上传评分）
// 依赖 api.js；兼容现有 app.js（只操作 view-home，不冲突）。
"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var VIEWS = ["home", "library", "compare", "score", "wallet", "shop", "space", "compute"];
  var cmpPaths = [];      // 比对视图已载入路径
  var cmpPicked = [];     // 比对标记优的路径
  var cmpScores = {};     // 比对评分缓存 {path: total}
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
      if (cmpScores[p]) scBadge.textContent = cmpScores[p].toFixed(1);
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
  function scoreCompare() {
    if (cmpPaths.length < 2) { toast("比对需至少 2 图"); return; }
    API.scoreBatch(cmpPaths).then(function (sc) {
      cmpScores = {};
      sc.items.forEach(function (it) {
        if (it.total != null) cmpScores[it.path] = it.total;
      });
      // 排序标记优 = 按总分降序
      var ranked = cmpPaths.slice().sort(function (a, b) {
        return (cmpScores[b] || -1) - (cmpScores[a] || -1);
      });
      cmpPicked = ranked;
      renderCompare();
      var lines = sc.items.map(function (it) {
        return "<div>" + (it.total != null ? it.total.toFixed(1) + "分" : it.error) + " · " + it.path.split("/").pop() + "</div>";
      }).join("");
      document.getElementById("cmp-result").innerHTML = "<b>评分对比（按分排序）：</b>" + lines;
      toast("评分完成 平均 " + sc.avg_total);
    }).catch(function (e) { toast("评分失败: " + e.message); });
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
      (d.items || []).forEach(function (it) {
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
      API.recharge(a).then(function (r) { toast("充值成功，余额 " + r.balance); renderWallet(); refreshBalance(); }).catch(function (e) { toast(e.message); });
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
    if (si) si.addEventListener("input", debounce(loadLibrary, 300));
    if (ss) ss.addEventListener("change", loadLibrary);
    if (so) so.addEventListener("change", loadLibrary);
    var rf = document.getElementById("lib-refresh"); if (rf) rf.addEventListener("click", loadLibrary);
    var ds = document.getElementById("lib-del-sel"); if (ds) ds.addEventListener("click", delSelectedLibrary);
    var ac = document.getElementById("lib-add-compare"); if (ac) ac.addEventListener("click", addSelectedToCompare);
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
