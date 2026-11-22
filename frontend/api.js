// Aesthetic Prism 前端 API 封装（原生 JS 零依赖，同源 fetch）
// 统一错误体 {"error":{code,message}}；所有请求返回 Promise。
"use strict";
var API = (function () {
  function http(url, opts) {
    opts = opts || {};
    return fetch(url, opts).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (body) {
        if (!resp.ok) {
          var err = body && body.error;
          var e = new Error((err && err.message) || ("HTTP " + resp.status));
          e.code = (err && err.code) || ("http_" + resp.status);
          e.status = resp.status;
          throw e;
        }
        return body;
      });
    });
  }
  return {
    score: function (file) {
      var fd = new FormData(); fd.append("image", file);
      return http("/score", { method: "POST", body: fd });
    },
    upload: function (file) {
      var fd = new FormData(); fd.append("image", file);
      return http("/upload", { method: "POST", body: fd });
    },
    train: function (steps) {
      return http("/train", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ steps: steps }) });
    },
    trainStatus: function () { return http("/train/status"); },
    job: function (id) { return http("/jobs/" + id); },
    health: function () { return http("/health"); },
    assets: function (params) {
      var q = new URLSearchParams(params || {}).toString();
      return http("/assets" + (q ? "?" + q : ""));
    },
    assetsDelete: function (paths) {
      return http("/assets/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: paths }) });
    },
    assetsRename: function (path, newName) {
      return http("/assets/rename", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: path, new_name: newName }) });
    },
    assetsMeta: function (path, tags, note) {
      var body = { path: path };
      if (tags) body.tags = tags;
      if (note !== undefined) body.note = note;
      return http("/assets/meta", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    },
    assetsUploadBatch: function (files) {
      var fd = new FormData();
      Array.prototype.forEach.call(files, function (f) { fd.append("files", f); });
      return http("/assets/upload-batch", { method: "POST", body: fd });
    },
    scoreBatch: function (paths) {
      return http("/score-batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: paths }) });
    },
    trainBatch: function (steps, paths) {
      var body = { steps: steps };
      if (paths) body.paths = paths;
      return http("/train/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    },
    assetsExists: function (paths) {
      return http("/assets/exists", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: paths }) });
    }
  };
})();
function assetUrl(path) { return "/" + path; }
