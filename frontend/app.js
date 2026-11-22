// Aesthetic Prism 前端逻辑（原生 JS 零依赖零构建；同源 fetch 无 CORS）
// 契约 C-SERVE-01：ScoreResponse 六字段（total+composition/light/creativity/story+model）；
// 错误体统一 {"error":{"code","message"}}；键名逐字。
// 双端流程：上传(/upload) → 评分(/score) → 训练(/train + /train/status + /jobs/<id>) → 状态(/health)。
"use strict";

const DIMS = ["composition", "light", "creativity", "story"];
const MAX_BYTES = 10 * 1024 * 1024; // 与 service.MAX_IMAGE_BYTES 一致（10485760）

const $ = (id) => document.getElementById(id);

let picked = null;        // 当前选中的 File
let uploadedPath = null;  // /upload 返回的服务端相对路径
let trainTimer = null;    // 训练进度轮询句柄

/* ================= 公共：错误体 / 请求 ================= */

function showError(code, message) {
  $("error-box").classList.add("show");
  $("error-code").textContent = code;
  $("error-message").textContent = message;
}
function clearError() {
  $("error-box").classList.remove("show");
}

async function parseBody(resp) {
  try {
    return await resp.json();
  } catch (e) {
    return null;
  }
}

function bodyError(resp, body) {
  // 契约错误体优先；解析失败给 http_<status> 兜底
  const err = body && body.error;
  if (err && typeof err.code === "string" && typeof err.message === "string") {
    return [err.code, err.message];
  }
  return ["http_" + resp.status, "响应无法解析为契约错误体"];
}

/* ================= Step 1 素材上传 ================= */

const dropZone = $("drop-zone");
const fileInput = $("file-input");

dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => accept(fileInput.files && fileInput.files[0]));
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("over");
  accept(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
});

function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(2) + " MB";
}

function accept(file) {
  clearError();
  if (!file) return;
  if (file.size > MAX_BYTES) {
    // 前端预检：不发请求，直接给 413 同文案
    showError("payload_too_large", "image is " + file.size + " bytes, limit " + MAX_BYTES);
    $("upload-state").textContent = "超出大小限制";
    $("upload-state").className = "pill err";
    return;
  }
  picked = file;
  uploadedPath = null;
  const url = URL.createObjectURL(file);
  const img = $("preview");
  if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
  img.src = url;
  img.dataset.url = url;
  $("preview-wrap").classList.add("show");
  $("m-name").textContent = file.name || "upload.png";
  $("m-size").textContent = fmtBytes(file.size);
  $("m-path").textContent = "尚未上传";
  $("m-dim").textContent = "-";
  $("upload-state").textContent = "待上传";
  $("upload-state").className = "pill idle";
  $("upload-btn").disabled = false;
  $("score-btn").disabled = false;
}

$("upload-btn").addEventListener("click", async () => {
  if (!picked) return;
  clearError();
  const btn = $("upload-btn");
  btn.disabled = true;
  const st = $("upload-state");
  st.textContent = "上传中";
  st.className = "pill run";
  const fd = new FormData();
  fd.append("image", picked, picked.name || "upload.png");
  try {
    const resp = await fetch("/upload", { method: "POST", body: fd });
    const body = await parseBody(resp);
    if (!resp.ok || !body || body.error) {
      const [code, message] = bodyError(resp, body);
      showError(code, message);
      st.textContent = "上传失败";
      st.className = "pill err";
      return;
    }
    uploadedPath = body.path;
    $("m-path").textContent = body.path;
    $("m-dim").textContent = body.width + " x " + body.height + " · " + body.mime;
    st.textContent = "已上传";
    st.className = "pill ok";
  } catch (e) {
    showError("network_error", String((e && e.message) || e));
    st.textContent = "上传失败";
    st.className = "pill err";
  } finally {
    btn.disabled = false;
  }
});

/* ================= Step 2 评分 ================= */

$("score-btn").addEventListener("click", async () => {
  if (!picked) return;
  clearError();
  const btn = $("score-btn");
  const st = $("score-state");
  btn.disabled = true;
  st.textContent = "评分中";
  st.className = "pill run";
  const fd = new FormData();
  fd.append("image", picked, picked.name || "upload.png");
  try {
    const resp = await fetch("/score", { method: "POST", body: fd });
    const body = await parseBody(resp);
    if (!resp.ok || !body || body.error) {
      const [code, message] = bodyError(resp, body);
      showError(code, message);
      st.textContent = "评分失败";
      st.className = "pill err";
      return;
    }
    render(body);
    st.textContent = "已完成";
    st.className = "pill ok";
  } catch (e) {
    showError("network_error", String((e && e.message) || e));
    st.textContent = "评分失败";
    st.className = "pill err";
  } finally {
    btn.disabled = false;
  }
});

function render(d) {
  $("score-empty").style.display = "none";
  $("score-board").classList.add("show");
  $("total-score").textContent = Number(d.total).toFixed(1);
  $("model-badge").textContent = "model: " + (d.model != null ? d.model : "-");
  for (const k of DIMS) {
    const v = Number(d[k]);
    const ok = Number.isFinite(v);
    $("fill-" + k).style.width = (ok ? Math.max(0, Math.min(100, v)) : 0) + "%";
    $("value-" + k).textContent = ok ? v.toFixed(1) : "--";
  }
}

/* ================= Step 3 训练 ================= */

function setTrainPill(state, text) {
  const p = $("job-pill");
  p.textContent = text;
  p.className = "pill " + state;
}

function applyProgress(p) {
  const done = Number(p.done) || 0;
  const total = Number(p.total) || 0;
  const pct = Number(p.pct) || 0;
  $("p-fill").style.width = Math.max(0, Math.min(100, pct)) + "%";
  $("p-text").textContent = done + " / " + total + " steps";
  $("p-pct").textContent = pct + "%";
  const last = p.last_loss;
  $("job-progress").textContent =
    (last != null ? "loss " + last : "loss -") + " · " + pct + "%";
  if (p.state) {
    const map = { running: ["run", "运行中"], succeeded: ["ok", "已完成"], failed: ["err", "失败"], idle: ["idle", "未触发"] };
    const m = map[p.state] || ["idle", p.state];
    setTrainPill(m[0], m[1]);
  }
}

$("train-btn").addEventListener("click", async () => {
  clearError();
  const steps = Math.max(1, Math.min(10000, parseInt($("steps-input").value, 10) || 20));
  $("steps-input").value = String(steps);
  const btn = $("train-btn");
  btn.disabled = true;
  setTrainPill("run", "已触发");
  $("train-log").textContent = "";
  try {
    const resp = await fetch("/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps: steps }),
    });
    const body = await parseBody(resp);
    if (!resp.ok || !body || body.error) {
      const [code, message] = bodyError(resp, body);
      showError(code, message);
      setTrainPill("err", "触发失败");
      return;
    }
    $("job-id").textContent = body.job_id;
    $("train-log").textContent =
      "job " + body.job_id + " 已提交 steps=" + body.steps + "\n" +
      "loss-log: " + body.loss_log;
    startTrainPoll(body.job_id);
  } catch (e) {
    showError("network_error", String((e && e.message) || e));
    setTrainPill("err", "触发失败");
  } finally {
    btn.disabled = false;
  }
});

async function refreshTrain() {
  try {
    const resp = await fetch("/train/status");
    const body = await parseBody(resp);
    if (!resp.ok || !body || body.error) return;
    applyProgress(body);
    if (body.latest_job_id) $("job-id").textContent = body.latest_job_id;
    if (body.running) setTrainPill("run", "运行中");
    return body;
  } catch (e) {
    return null;
  }
}

async function pollJob(jobId) {
  try {
    const resp = await fetch("/jobs/" + encodeURIComponent(jobId));
    const body = await parseBody(resp);
    if (!resp.ok || !body || body.error) return null;
    applyProgress(body);
    if (body.state !== "running") {
      stopTrainPoll();
      setTrainPill(body.state === "succeeded" ? "ok" : "err", body.state === "succeeded" ? "已完成" : "失败");
      $("train-log").textContent +=
        "\n结束 state=" + body.state + " rc=" + body.returncode;
    }
    return body;
  } catch (e) {
    return null;
  }
}

function startTrainPoll(jobId) {
  stopTrainPoll();
  pollJob(jobId);
  trainTimer = setInterval(() => pollJob(jobId), 1500);
}
function stopTrainPoll() {
  if (trainTimer) {
    clearInterval(trainTimer);
    trainTimer = null;
  }
}
$("refresh-train-btn").addEventListener("click", () => {
  const id = $("job-id").textContent;
  if (id && id !== "-" && !trainTimer) pollJob(id);
  else refreshTrain();
});

// 页面加载即拉一次训练状态（读 loss.json）
refreshTrain();

/* ================= Step 4 服务状态 /health ================= */

async function pollHealth() {
  const badge = $("health-badge");
  const text = $("health-text");
  const brief = $("health-brief");
  try {
    const r = await fetch("/health");
    const h = await r.json();
    const pre = $("health-json");
    pre.classList.remove("off");
    pre.textContent = JSON.stringify(h, null, 2);
    $("kv-status").textContent = (h && h.status) || "-";
    $("kv-model").textContent = (h && h.model) || "-";
    $("kv-device").textContent = (h && h.device) || "-";
    $("kv-uptime").textContent = h && h.uptime_s != null ? h.uptime_s + " s" : "-";
    if (h && h.status === "ok" && h.ready === true) {
      badge.className = "badge ok";
      text.textContent = "运行中";
      brief.textContent = (h.model || "-") + " · " + (h.device || "-") + " · " + h.uptime_s + "s";
    } else if (h && h.status === "degraded") {
      badge.className = "badge deg";
      text.textContent = "降级";
      brief.textContent = "ready=false";
    } else {
      badge.className = "badge bad";
      text.textContent = "异常";
      brief.textContent = "unexpected body";
    }
    return true;
  } catch (e) {
    badge.className = "badge bad";
    text.textContent = "离线";
    brief.textContent = "no response";
    const pre = $("health-json");
    pre.classList.add("off");
    pre.textContent = JSON.stringify({ error: { code: "network_error", message: "无法连接 127.0.0.1:8000" } }, null, 2);
    $("kv-status").textContent = "离线";
    $("kv-model").textContent = "-";
    $("kv-device").textContent = "-";
    $("kv-uptime").textContent = "-";
    return false;
  }
}

$("check-btn").addEventListener("click", () => pollHealth());
pollHealth();
setInterval(pollHealth, 5000);
