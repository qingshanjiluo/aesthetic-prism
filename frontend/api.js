// Aesthetic Prism 前端 API 封装（原生 JS 零依赖，同源 fetch）
// 统一错误体 {"error":{code,message}}；带 JWT 鉴权头。
"use strict";

// ---- token 管理（localStorage）----
var AUTH = {
  TOKEN_KEY: "ap_token",
  getToken: function () { try { return localStorage.getItem(AUTH.TOKEN_KEY) || ""; } catch (e) { return ""; } },
  setToken: function (t) { try { localStorage.setItem(AUTH.TOKEN_KEY, t); } catch (e) {} },
  clear: function () { try { localStorage.removeItem(AUTH.TOKEN_KEY); } catch (e) {} },
  isAuthed: function () { return !!AUTH.getToken(); }
};

var API = (function () {
  function http(url, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    var tok = AUTH.getToken();
    if (tok) headers["Authorization"] = "Bearer " + tok;
    opts.headers = headers;
    return fetch(url, opts).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (body) {
        if (!resp.ok) {
          if (resp.status === 401) { AUTH.clear(); try { var lv = document.getElementById("login-view"); if (lv) lv.hidden = false; } catch (e) {} }
          var err = body && body.error;
          var detail = body && body.detail;
          if (Array.isArray(detail)) {
            detail = detail.map(function (d) { return typeof d === "object" ? JSON.stringify(d) : String(d); }).join("; ");
          }
          var e = new Error((err && err.message) || detail || ("HTTP " + resp.status));
          e.code = (err && err.code) || ("http_" + resp.status);
          e.status = resp.status;
          throw e;
        }
        return body;
      });
    });
  }
  function json(method, url, data) {
    return http(url, { method: method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });
  }
  return {
    // ---- 认证 ----
    register: function (username, password) { return json("POST", "/api/auth/register", { username: username, password: password }); },
    login: function (username, password) { return json("POST", "/api/auth/login", { username: username, password: password }); },
    me: function () { return http("/api/me"); },
    // ---- 钱包 ----
    wallet: function () { return http("/api/wallet"); },
    ledger: function (limit) { return http("/api/wallet/ledger?limit=" + (limit || 50)); },
    recharge: function (amount) { return json("POST", "/api/wallet/recharge", { amount: amount }); },
    // ---- 商城 ----
    shop: function () { return http("/api/models/shop"); },
    buy: function (model_id) { return json("POST", "/api/models/buy", { model_id: model_id }); },
    // ---- 空间 / 算力 ----
    spaceExpand: function (gb) { return json("POST", "/api/space/expand", { gb: gb }); },
    compute: function (tier) { return json("POST", "/api/compute", { tier: tier }); },
    // ---- 原有业务 ----
    score: function (file) { var fd = new FormData(); fd.append("image", file); return http("/score", { method: "POST", body: fd }); },
    upload: function (file) { var fd = new FormData(); fd.append("image", file); return http("/upload", { method: "POST", body: fd }); },
    train: function (steps) { return json("POST", "/train", { steps: steps }); },
    trainStatus: function () { return http("/train/status"); },
    job: function (id) { return http("/jobs/" + id); },
    health: function () { return http("/health"); },
    assets: function (params) { var q = new URLSearchParams(params || {}).toString(); return http("/assets" + (q ? "?" + q : "")); },
    assetsDelete: function (paths) { return json("POST", "/assets/delete", { paths: paths }); },
    assetsRename: function (path, newName) { return json("POST", "/assets/rename", { path: path, new_name: newName }); },
    assetsMeta: function (path, tags, note) { var b = { path: path }; if (tags) b.tags = tags; if (note !== undefined) b.note = note; return json("POST", "/assets/meta", b); },
    assetsUploadBatch: function (files) { var fd = new FormData(); Array.prototype.forEach.call(files, function (f) { fd.append("files", f); }); return http("/assets/upload-batch", { method: "POST", body: fd }); },
    scoreBatch: function (paths) { return json("POST", "/score-batch", { paths: paths }); },
    trainBatch: function (steps, paths) { var b = { steps: steps }; if (paths) b.paths = paths; return json("POST", "/train/batch", b); },
    assetsExists: function (paths) { return json("POST", "/assets/exists", { paths: paths }); },
    models: function () { return http("/models"); },
    modelsMeta: function (path, data) { var b = { path: path }; if (data.name !== undefined) b.name = data.name; if (data.category !== undefined) b.category = data.category; if (data.tags) b.tags = data.tags; if (data.note !== undefined) b.note = data.note; return json("POST", "/models/meta", b); },
    samplesGenerate: function (n) { return json("POST", "/samples/generate", { n: n }); },
    // ---- 数据标注 ----
    annotations: function (params) { var q = new URLSearchParams(params || {}).toString(); return http("/annotations" + (q ? "?" + q : "")); },
    annotationSave: function (body) { return json("POST", "/annotations", body); },
    annotationDelete: function (path) { return http("/annotations?path=" + encodeURIComponent(path), { method: "DELETE" }); },
    annotationExport: function (fmt, quality, minTotal) { var q = "fmt=" + (fmt || "jsonl"); if (quality) q += "&quality=" + encodeURIComponent(quality); if (minTotal) q += "&min_total=" + minTotal; return http("/annotations/export?" + q); }
  };
})();
function assetUrl(path) { return "/" + path; }