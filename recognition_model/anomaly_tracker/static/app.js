const form = document.querySelector("#upload-form");
const input = document.querySelector("#video-input");
const fileName = document.querySelector("#file-name");
const submitButton = document.querySelector("#submit-button");
const statusPanel = document.querySelector("#status-panel");
const statusText = document.querySelector("#status-text");
const progressText = document.querySelector("#progress-text");
const progressBar = document.querySelector("#progress-bar");
const errorText = document.querySelector("#error-text");
const resultPanel = document.querySelector("#result-panel");

const eventLabels = {
  suspected_fall: "疑似跌倒",
  suspected_violence: "疑似暴力行为",
  abnormal_staying: "疑似异常滞留",
  long_loitering: "疑似长时间徘徊",
  rapid_movement: "疑似异常快速移动",
  suspected_intense_interaction: "疑似激烈交互",
};

const evidenceLabels = {
  model: "模型",
  rules: "规则",
  both: "模型与规则",
};

function publicErrorMessage(error) {
  if (typeof error === "string" && error) return error;
  if (error && typeof error.message === "string") return error.message;
  return "视频处理失败";
}

input.addEventListener("change", () => {
  fileName.textContent = input.files[0]?.name || "尚未选择视频";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files[0]) return;
  resetView();
  submitButton.disabled = true;
  const body = new FormData();
  body.append("video", input.files[0]);

  try {
    const response = await fetch("/api/jobs", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "上传失败");
    await pollJob(payload.job_id);
  } catch (error) {
    showError(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

async function pollJob(jobId) {
  while (true) {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "查询任务失败");
    updateProgress(job);
    if (job.status === "failed") {
      throw new Error(publicErrorMessage(job.error));
    }
    if (job.status === "completed") {
      const resultResponse = await fetch(job.result_url);
      const result = await resultResponse.json();
      if (!resultResponse.ok) {
        throw new Error(result.detail || "读取结果失败");
      }
      renderResult(job, result);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
}

function resetView() {
  statusPanel.classList.remove("hidden");
  resultPanel.classList.add("hidden");
  errorText.classList.add("hidden");
  progressBar.style.width = "0%";
  progressText.textContent = "0%";
  statusText.textContent = "正在上传";
}

function updateProgress(job) {
  const percent = Math.round(job.progress * 100);
  const labels = {
    queued: "等待处理",
    running: "正在分析",
    completed: "分析完成",
  };
  statusText.textContent = labels[job.status] || job.status;
  progressText.textContent = `${percent}%`;
  progressBar.style.width = `${percent}%`;
}

function showError(message) {
  statusPanel.classList.remove("hidden");
  statusText.textContent = "处理失败";
  errorText.textContent = message;
  errorText.classList.remove("hidden");
}

function appendLine(parent, label, value) {
  const line = document.createElement("span");
  line.textContent = `${label}：${value}`;
  parent.append(line);
}

function renderModelStatus(result) {
  const target = document.querySelector("#model-status");
  target.replaceChildren();
  const status =
    result?.model_status && typeof result.model_status === "object"
      ? result.model_status
      : { mode: "rules_only" };
  const headline = document.createElement("strong");
  if (status.mode === "hybrid") {
    headline.textContent = "混合分析：模型与轨迹规则";
    target.className = "model-status hybrid";
  } else if (status.mode === "hybrid_degraded") {
    headline.textContent = "混合分析已降级，后续仅使用轨迹规则";
    target.className = "model-status degraded";
  } else {
    headline.textContent = "仅使用轨迹规则（未使用行为分类模型）";
    target.className = "model-status rules-only";
  }
  target.append(headline);
  if (status.device) appendLine(target, "推理设备", status.device);
  if (status.checkpoint) appendLine(target, "模型配置", status.checkpoint);
  if (status.error) appendLine(target, "降级原因", status.error);
  if (status.track_errors) {
    appendLine(target, "失败轨迹窗口", status.track_errors);
  }
  const trackingStatus =
    result?.tracking_status && typeof result.tracking_status === "object"
      ? result.tracking_status
      : {};
  if (trackingStatus.errors) {
    appendLine(target, "轨迹输入错误", trackingStatus.errors);
  }
}

function renderPredictions(result) {
  const list = document.querySelector("#prediction-list");
  list.replaceChildren();
  const predictionData = Array.isArray(result?.classifier_predictions)
    ? result.classifier_predictions
    : [];
  const predictions = predictionData
    .filter(
      (prediction) => prediction && typeof prediction === "object",
    )
    .filter((prediction) => prediction.status === "ok");
  if (!predictions.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "没有可显示的模型推理窗口";
    list.append(empty);
    return;
  }
  for (const prediction of predictions) {
    const item = document.createElement("article");
    item.className = "prediction-item";
    appendLine(item, "轨迹 ID", prediction.track_id);
    appendLine(
      item,
      "时间区间",
      `${prediction.start_time}s – ${prediction.end_time}s`,
    );
    const probabilities = prediction.smoothed_probabilities || {};
    appendLine(
      item,
      "平滑概率",
      `正常 ${formatPercent(probabilities.normal)} / 暴力 ${formatPercent(
        probabilities.violence,
      )} / 跌倒 ${formatPercent(probabilities.fall)}`,
    );
    list.append(item);
  }
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : "—";
}

function renderResult(job, result) {
  resultPanel.classList.remove("hidden");
  const video = document.querySelector("#result-video");
  video.src = `${job.video_url}?t=${Date.now()}`;
  document.querySelector("#download-link").href = job.video_url;
  renderModelStatus(result);
  renderPredictions(result);

  const events = Array.isArray(result.events) ? result.events : [];
  document.querySelector("#event-count").textContent = events.length;
  const list = document.querySelector("#event-list");
  list.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "没有发现达到复核阈值的疑似异常事件";
    list.append(empty);
  }
  for (const event of events) {
    if (!event || typeof event !== "object") continue;
    const item = document.createElement("article");
    item.className = "event-item";
    const title = document.createElement("strong");
    title.textContent = eventLabels[event.event_type] || `疑似事件：${event.event_type}`;
    item.append(title);
    const trackIds = Array.isArray(event.track_ids) ? event.track_ids : [];
    appendLine(item, "轨迹 ID", trackIds.length ? trackIds.join(", ") : "未知");
    appendLine(
      item,
      "时间区间",
      `${event.start_time}s – ${event.end_time}s`,
    );
    appendLine(item, "置信度", formatPercent(event.confidence));
    appendLine(
      item,
      "证据来源",
      evidenceLabels[event.evidence?.source] || "未知",
    );
    const warning = document.createElement("small");
    warning.textContent = "疑似事件，需要人工复核";
    item.append(warning);
    list.append(item);
  }
  document.querySelector("#json-output").textContent = JSON.stringify(
    result,
    null,
    2,
  );
}
