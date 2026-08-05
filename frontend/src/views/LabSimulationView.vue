<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../api";
import { useAuthStore } from "../stores/auth";
import { useSettingsStore } from "../stores/settings";
import {
  MODEL_OFFLINE_MSG,
  MODEL_QUEUE_HINT,
  modelCreateCollection,
  modelCreateJob,
  modelDeleteCollection,
  modelDeleteJob,
  modelGetCollectionResult,
  modelGetResult,
  modelHealth,
  modelJobVideoUrl,
  modelResolveCollection,
  modelUploadCollectionVideo,
  pollModelJob,
  validateVideoFile,
} from "../api/model";
import type { CollectionResult, ModelJobStatus, ModelResult } from "../api/model";

const auth = useAuthStore();
const settings = useSettingsStore();

/* ---------------- 模型服务健康检测 ---------------- */
const modelOnline = ref<boolean | null>(null);
const healthChecking = ref(false);

async function checkModelHealth() {
  healthChecking.value = true;
  try {
    const res = await modelHealth();
    modelOnline.value = res.status === "ok";
  } catch {
    modelOnline.value = false;
  } finally {
    healthChecking.value = false;
  }
}

const modelOffline = computed(() => modelOnline.value === false);

/* ---------------- 设备 ---------------- */
const selectedDevice = ref<number | undefined>(undefined);
const selectedReidDeviceA = ref<number | undefined>(undefined);
const selectedReidDeviceB = ref<number | undefined>(undefined);
const devices = ref<{ id: number; name: string }[]>([]);

/* ---------------- 页签 ---------------- */
const activeTab = ref<"single" | "reid">("single");

/* ---------------- 单视频识别 ---------------- */
const videoFile = ref<File | null>(null);
const videoUrl = ref("");
const calibration = ref(
  JSON.stringify({ fall_seconds: 1.0, stationary_seconds: 20.0, dangerous_zones: [] }, null, 2)
);
const singleJobId = ref("");
const singleStatus = ref<ModelJobStatus | "">("");
const progress = ref(0);
const analyzing = ref(false);
const result = ref<ModelResult | null>(null);
const isPublished = ref(false);
const publishedRecordId = ref<number | null>(null);
const message = ref("");
const messageType = ref<"info" | "success" | "error">("info");

const threshold = ref(0.7);
const simulationOutput = ref<string[]>([]);

const summary = computed(() => {
  if (!result.value) return null;
  return {
    total_events: result.value.events?.length || 0,
    total_tracks: result.value.tracks?.length || 0,
    need_review: (result.value.events || []).filter((e) => e.requires_review).length,
  };
});

const canPublish = computed(
  () => !!result.value && !isPublished.value && selectedDevice.value != null && singleStatus.value === "completed"
);
const canDeleteJob = computed(
  () => !!singleJobId.value && (singleStatus.value === "completed" || singleStatus.value === "failed") && !analyzing.value
);
const annotatedUrl = computed(() =>
  singleJobId.value && singleStatus.value === "completed" ? modelJobVideoUrl(singleJobId.value) : ""
);

function statusText(s: string): string {
  switch (s) {
    case "queued":
      return "排队中";
    case "processing":
      return "推理中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return s || "—";
  }
}

function resetSingleState() {
  singleJobId.value = "";
  singleStatus.value = "";
  progress.value = 0;
  result.value = null;
  isPublished.value = false;
  publishedRecordId.value = null;
  simulationOutput.value = [];
  message.value = "";
}

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  const err = validateVideoFile(file);
  if (err) {
    alert(err);
    target.value = "";
    return;
  }
  resetSingleState();
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value);
  videoFile.value = file;
  videoUrl.value = URL.createObjectURL(file);
}

async function startAnalyze() {
  if (!videoFile.value || analyzing.value) return;
  if (selectedDevice.value == null) {
    message.value = "请选择模拟摄像头";
    messageType.value = "error";
    return;
  }
  if (modelOffline.value) {
    alert(MODEL_OFFLINE_MSG);
    return;
  }
  let cal = "";
  try {
    cal = calibration.value.trim() ? JSON.stringify(JSON.parse(calibration.value)) : "";
  } catch {
    message.value = "校准配置不是合法 JSON，请检查后重试";
    messageType.value = "error";
    return;
  }

  const file = videoFile.value;
  analyzing.value = true;
  resetSingleState();
  message.value = "正在上传视频到模型推理服务...";
  messageType.value = "info";
  try {
    const job = await modelCreateJob(file, cal || undefined);
    singleJobId.value = job.job_id;
    singleStatus.value = job.status;
    progress.value = job.progress || 0;
    message.value = "任务已提交，等待模型推理...";
    await pollModelJob(job.job_id, (st) => {
      singleStatus.value = st.status;
      progress.value = st.progress || 0;
    });
    singleStatus.value = "completed";
    progress.value = 1;
    result.value = await modelGetResult(job.job_id);
    message.value = `识别完成！事件 ${summary.value?.total_events || 0} 个，轨迹 ${summary.value?.total_tracks || 0} 条。可播放标注视频、导出结果或发布到业务。`;
    messageType.value = "success";
  } catch (e: any) {
    if (singleJobId.value) singleStatus.value = "failed";
    message.value = e?.message || "识别失败";
    messageType.value = "error";
  } finally {
    analyzing.value = false;
  }
}

async function deleteSingleJob() {
  if (!singleJobId.value) return;
  if (!confirm("确认删除该任务？将清理模型服务端相关文件（不影响已发布到业务库的数据）。")) return;
  try {
    await modelDeleteJob(singleJobId.value);
    resetSingleState();
    message.value = "模型服务端任务文件已清理";
    messageType.value = "info";
  } catch (e: any) {
    alert(e?.message || "删除失败");
  }
}

function exportResult() {
  if (!result.value) return;
  const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: "application/json" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = `model-result-${singleJobId.value || "export"}.json`;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

async function publishRecord() {
  if (!result.value || !canPublish.value) return;
  if (selectedDevice.value == null) {
    message.value = "请选择模拟摄像头";
    messageType.value = "error";
    return;
  }
  analyzing.value = true;
  message.value = "正在发布到业务库...";
  messageType.value = "info";
  try {
    const data = await api.labPublishResult({
      device_ids: [selectedDevice.value],
      record_name: `模拟-${videoFile.value?.name || "识别结果"}`,
      video_filename: videoFile.value?.name || "",
      video_url: singleJobId.value ? modelJobVideoUrl(singleJobId.value) : "",
      video_job_id: singleJobId.value || "",
      result: result.value,
    });
    isPublished.value = true;
    publishedRecordId.value = (data as any).record_id ?? null;
    const c = (data as any).counts;
    if (c) {
      const hint = `成功发布到业务！记录 ID：${data.record_id}。\n生成：异常行为 ${c.behavior_count} 条、预警 ${c.alert_count} 条、工单 ${c.work_order_count} 条。\n\n请将顶部导航栏【过滤模拟数据】开关关闭，即可在业务列表（异常行为记录 / 告警待办 / 轨迹查询）中看到带“模拟”标签的数据。`;
      message.value = hint;
      messageType.value = "success";
      if (window.confirm(`${hint}\n\n是否立即关闭“过滤模拟数据”开关？`)) {
        settings.filterLabData = false;
      }
    } else {
      message.value = "已发布到业务。";
      messageType.value = "success";
    }
  } catch (e: any) {
    message.value = "发布失败：" + (e?.message || "未知错误");
    messageType.value = "error";
  } finally {
    analyzing.value = false;
  }
}

const clearingSandbox = ref(false);

async function clearSandbox() {
  if (clearingSandbox.value) return;
  if (!confirm("⚠️ 警告：此操作将删除全部模拟业务数据（带“模拟”标签的异常行为/预警/工单/轨迹/人员），且不可恢复！\n\n确认继续吗？")) return;
  if (!confirm("请再次确认：真的要清空全部模拟数据吗？")) return;
  clearingSandbox.value = true;
  try {
    await api.labClearSandbox();
    message.value = "全部模拟数据已清空";
    messageType.value = "success";
  } catch (e: any) {
    alert(e?.message || "清空失败");
  } finally {
    clearingSandbox.value = false;
  }
}

function runSimulation() {
  if (!result.value) return;
  const out: string[] = [];
  const events = result.value.events || [];
  const severe = events.filter(
    (e) =>
      ["suspected_fall", "suspected_violence", "dangerous_zone_proximity"].includes(e.event_type) &&
      e.confidence >= threshold.value
  );
  if (severe.length) {
    out.push(`命中高等级规则 ${severe.length} 条，将生成告警记录`);
    out.push("根据默认派单策略，告警将派发给园区安全负责人");
  }
  const tracks = (result.value.tracks || []).filter((t) => (t.event_types || []).length);
  if (tracks.length) {
    out.push(`${tracks.length} 个目标将被标记为重点跟踪人员`);
  }
  if (!out.length) {
    out.push("当前阈值与规则下，未命中任何业务动作");
  }
  simulationOutput.value = out;
}

/* ---------------- 跨视频人员关联（ReID） ---------------- */
const reidFileA = ref<File | null>(null);
const reidFileB = ref<File | null>(null);
const reidCollectionId = ref("");
const reidJobA = ref<{ id: string; status: string; progress: number }>({ id: "", status: "", progress: 0 });
const reidJobB = ref<{ id: string; status: string; progress: number }>({ id: "", status: "", progress: 0 });
const reidPhase = ref<"idle" | "working" | "resolving" | "done" | "failed">("idle");
const reidResult = ref<CollectionResult | null>(null);
const reidMessage = ref("");
const reidMessageType = ref<"info" | "success" | "error">("info");

const reidWorking = computed(() => reidPhase.value === "working" || reidPhase.value === "resolving");
const reidPublishing = ref(false);
const reidUnavailable = computed(() => reidResult.value?.reid_status === "unavailable");
const reidCanStart = computed(
  () =>
    !!reidFileA.value &&
    !!reidFileB.value &&
    selectedReidDeviceA.value != null &&
    selectedReidDeviceB.value != null &&
    selectedReidDeviceA.value !== selectedReidDeviceB.value &&
    !reidWorking.value &&
    !reidPublishing.value &&
    !modelOffline.value
);
const reidCanClean = computed(
  () => !!reidCollectionId.value && (reidPhase.value === "done" || reidPhase.value === "failed") && !reidPublishing.value
);
const reidCanPublish = computed(
  () =>
    !!reidResult.value &&
    reidPhase.value === "done" &&
    reidResult.value.reid_status !== "unavailable" &&
    !reidPublishing.value
);

function onReidFileChange(which: "A" | "B", e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  const err = validateVideoFile(file);
  if (err) {
    alert(err);
    target.value = "";
    return;
  }
  if (which === "A") reidFileA.value = file;
  else reidFileB.value = file;
}

async function startReid() {
  if (!reidFileA.value || !reidFileB.value || reidWorking.value) return;
  if (selectedReidDeviceA.value == null || selectedReidDeviceB.value == null) {
    reidMessage.value = "请分别为两段视频选择对应的摄像头";
    reidMessageType.value = "error";
    return;
  }
  if (selectedReidDeviceA.value === selectedReidDeviceB.value) {
    reidMessage.value = "双视频场景需要选择两个不同的摄像头";
    reidMessageType.value = "error";
    return;
  }
  if (modelOffline.value) {
    alert(MODEL_OFFLINE_MSG);
    return;
  }
  reidPhase.value = "working";
  reidResult.value = null;
  reidMessage.value = "正在创建跨视频分析集合...";
  reidMessageType.value = "info";
  try {
    const collection = await modelCreateCollection();
    reidCollectionId.value = collection.collection_id;
    reidMessage.value = "集合已创建，正在上传两段视频...";
    const [jobA, jobB] = await Promise.all([
      modelUploadCollectionVideo(collection.collection_id, reidFileA.value),
      modelUploadCollectionVideo(collection.collection_id, reidFileB.value),
    ]);
    reidJobA.value = { id: jobA.job_id, status: jobA.status, progress: jobA.progress || 0 };
    reidJobB.value = { id: jobB.job_id, status: jobB.status, progress: jobB.progress || 0 };
    reidMessage.value = "两段视频已提交，等待模型推理...";
    await Promise.all([
      pollModelJob(jobA.job_id, (st) => {
        reidJobA.value = { id: st.job_id, status: st.status, progress: st.progress || 0 };
      }),
      pollModelJob(jobB.job_id, (st) => {
        reidJobB.value = { id: st.job_id, status: st.status, progress: st.progress || 0 };
      }),
    ]);
    reidPhase.value = "resolving";
    reidMessage.value = "两段视频识别完成，正在执行跨视频人员关联...";
    await modelResolveCollection(collection.collection_id);
    reidResult.value = await modelGetCollectionResult(collection.collection_id);
    reidPhase.value = "done";
    if (reidResult.value.reid_status === "unavailable") {
      reidMessage.value = "跨视频模型不可用，本次无法输出人员匹配结果。";
      reidMessageType.value = "error";
    } else {
      reidMessage.value = "跨视频人员关联完成。注意：结果仅为外观辅助关联，必须人工复核。";
      reidMessageType.value = "success";
    }
  } catch (e: any) {
    reidPhase.value = "failed";
    reidMessage.value = e?.message || "跨视频分析失败";
    reidMessageType.value = "error";
  }
}

function resetReid() {
  reidCollectionId.value = "";
  reidJobA.value = { id: "", status: "", progress: 0 };
  reidJobB.value = { id: "", status: "", progress: 0 };
  reidResult.value = null;
  reidPhase.value = "idle";
  reidMessage.value = "";
}

async function publishReidRecord() {
  if (!reidResult.value || reidResult.value.reid_status === "unavailable" || reidPublishing.value) return;
  if (selectedReidDeviceA.value == null || selectedReidDeviceB.value == null) {
    reidMessage.value = "请分别为两段视频选择对应的摄像头";
    reidMessageType.value = "error";
    return;
  }
  reidPublishing.value = true;
  reidMessage.value = "正在发布到业务库...";
  reidMessageType.value = "info";
  try {
    const data = await api.labPublishResult({
      device_ids: [selectedReidDeviceA.value, selectedReidDeviceB.value],
      record_name: `ReID-${reidFileA.value?.name || "A"} / ${reidFileB.value?.name || "B"}`,
      video_filename: reidFileA.value?.name || "",
      video_filename_b: reidFileB.value?.name || "",
      video_url: reidJobA.value.id ? modelJobVideoUrl(reidJobA.value.id) : "",
      video_url_b: reidJobB.value.id ? modelJobVideoUrl(reidJobB.value.id) : "",
      video_job_id: reidJobA.value.id || "",
      video_job_id_b: reidJobB.value.id || "",
      result: reidResult.value,
    });
    const c = (data as any).counts;
    reidMessage.value = `成功发布到业务！记录 ID：${(data as any).record_id}。\n生成：异常行为 ${c.behavior_count} 条、预警 ${c.alert_count} 条。\n请关闭“过滤模拟数据”后在异常行为/告警/轨迹列表中查看。`;
    reidMessageType.value = "success";
  } catch (e: any) {
    reidMessage.value = "发布失败：" + (e?.message || "未知错误");
    reidMessageType.value = "error";
  } finally {
    reidPublishing.value = false;
  }
}

async function deleteReidCollection() {
  if (!reidCollectionId.value) return;
  if (!confirm("确认清理该集合？将删除模型服务端两段视频及关联文件。")) return;
  try {
    await modelDeleteCollection(reidCollectionId.value);
    resetReid();
    reidMessage.value = "集合及关联任务文件已清理";
    reidMessageType.value = "info";
  } catch (e: any) {
    alert(e?.message || "清理失败");
  }
}

function formatScore(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(3);
}

function decisionText(d: string): string {
  switch (d) {
    case "auto_match":
      return "自动匹配";
    case "new_identity":
      return "新人员";
    case "needs_review":
      return "待复核";
    case "insufficient_evidence":
      return "证据不足";
    default:
      return d || "—";
  }
}

/* ---------------- 设备故障模拟 ---------------- */
const faultDeviceId = ref<number | undefined>(undefined);
const faultType = ref("HARDWARE");
const faultLevel = ref("HIGH");
const faultDesc = ref("");
const faultSubmitting = ref(false);
const faultMessage = ref("");
const faultMessageType = ref<"info" | "success" | "error">("info");
const faultTypeOptions = [
  { value: "HARDWARE", label: "硬件损坏" },
  { value: "NETWORK", label: "网络中断" },
  { value: "VIDEO_ABNORMAL", label: "画面异常" },
  { value: "OTHER", label: "其他" },
];
const faultLevelOptions = [
  { value: "LOW", label: "低" },
  { value: "MEDIUM", label: "中" },
  { value: "HIGH", label: "高" },
  { value: "CRITICAL", label: "严重" },
];

async function submitFaultSimulate() {
  if (faultDeviceId.value == null) {
    faultMessage.value = "请选择目标设备";
    faultMessageType.value = "error";
    return;
  }
  faultSubmitting.value = true;
  faultMessage.value = "";
  try {
    const res = await api.simulateFault(faultDeviceId.value, {
      fault_type: faultType.value,
      fault_level: faultLevel.value,
      fault_desc: faultDesc.value || undefined,
    });
    faultMessage.value = res.assigned_name
      ? `已生成故障并自动派发工单 ${res.order_no} → ${res.assigned_name}，可前往「维修工单」页面处理`
      : `已生成故障工单 ${res.order_no}，暂无可用维修人员，待人工处理`;
    faultMessageType.value = "success";
  } catch (e: any) {
    faultMessage.value = e?.message || "模拟故障失败";
    faultMessageType.value = "error";
  } finally {
    faultSubmitting.value = false;
  }
}

/* ---------------- 生命周期 ---------------- */
onMounted(async () => {
  checkModelHealth();
  try {
    const res = await api.devices({ page: 1, size: 100 });
    devices.value = (res.list || []).map((d) => ({ id: d.id, name: d.device_name }));
    if (devices.value.length && selectedDevice.value == null) {
      selectedDevice.value = devices.value[0].id;
    }
  } catch (e: any) {
    message.value = e?.message || "加载摄像头列表失败";
    messageType.value = "error";
  }
});

onBeforeUnmount(() => {
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value);
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div>
        <h2>模拟实验室</h2>
        <p>上传视频调用远端模型推理服务：单视频异常识别 + 轨迹，双视频跨视频人员辅助关联</p>
      </div>
    </div>

    <!-- 模型服务健康状态 -->
    <div v-if="modelOnline === null" class="banner-warning">
      {{ healthChecking ? "正在检测模型推理服务状态..." : "等待检测模型推理服务状态..." }}
    </div>
    <div v-else-if="modelOffline" class="banner-error">
      {{ MODEL_OFFLINE_MSG }}
      <button class="link-btn" @click="checkModelHealth">重新检测</button>
    </div>

    <!-- 页签 -->
    <div class="tab-bar">
      <button :class="{ active: activeTab === 'single' }" @click="activeTab = 'single'">单视频识别</button>
      <button :class="{ active: activeTab === 'reid' }" @click="activeTab = 'reid'">跨视频人员关联</button>
    </div>

    <!-- ==================== 单视频识别 ==================== -->
    <template v-if="activeTab === 'single'">
      <div class="panel upload-panel">
        <div class="panel-title">
          <div><h3>视频与参数</h3><p>选择视频并配置本次模拟上下文（支持 MP4/AVI/MOV/MKV/WEBM，单文件 ≤ 2GB）</p></div>
        </div>
        <div class="form-row">
          <label>上传视频</label>
          <div class="upload-zone">
            <input id="lab-video" type="file" accept="video/*" @change="onFileChange" />
            <label for="lab-video" class="upload-button">选择文件</label>
            <span v-if="videoFile" class="file-name">{{ videoFile.name }}（{{ (videoFile.size / 1024 / 1024).toFixed(1) }} MB）</span>
            <span v-else class="placeholder">支持 MP4/AVI/MOV/MKV/WEBM，最大 2GB</span>
          </div>
        </div>
        <div class="form-row">
          <label>模拟设备</label>
          <select v-model="selectedDevice">
            <option :value="undefined">请选择摄像头</option>
            <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>标定配置（JSON）</label>
          <textarea v-model="calibration" rows="4"></textarea>
        </div>
        <div class="toolbar" style="margin-top: 12px">
          <button class="primary" :disabled="analyzing || !videoFile || selectedDevice == null || modelOffline" @click="startAnalyze">
            {{ analyzing ? "识别中..." : "开始识别" }}
          </button>
          <button class="success" :disabled="!canPublish || analyzing" @click="publishRecord">
            {{ isPublished ? "已发布" : "发布到业务" }}
          </button>
          <button class="danger" style="margin-left: auto" :disabled="!canDeleteJob" @click="deleteSingleJob">删除任务</button>
          <button class="danger" :disabled="clearingSandbox" @click="clearSandbox">
            {{ clearingSandbox ? "清空中..." : "清空模拟数据" }}
          </button>
        </div>
        <div v-if="analyzing || singleStatus" class="progress-wrap">
          <div class="progress-bar" :style="{ width: Math.round(progress * 100) + '%' }"></div>
          <span>{{ Math.round(progress * 100) }}%（{{ statusText(singleStatus) }}）</span>
        </div>
        <p class="hint-text">{{ MODEL_QUEUE_HINT }}</p>
        <div v-if="message" :class="['message', messageType]">
          {{ message }}
        </div>
      </div>

      <div v-if="videoUrl || annotatedUrl" class="video-panel">
        <div class="panel" style="flex: 1">
          <div class="panel-title"><h3>原始视频</h3></div>
          <video v-if="videoUrl" :src="videoUrl" controls style="width: 100%; max-height: 420px"></video>
        </div>
        <div v-if="annotatedUrl" class="panel" style="flex: 1">
          <div class="panel-title"><h3>标注视频（模型输出）</h3></div>
          <video :src="annotatedUrl" controls style="width: 100%; max-height: 420px"></video>
        </div>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-title">
          <div><h3>识别摘要</h3></div>
          <div class="panel-actions">
            <button class="link-btn" @click="exportResult">导出结果 JSON</button>
          </div>
        </div>
        <div class="stats" v-if="summary">
          <div><small>事件数</small><strong>{{ summary.total_events }}</strong></div>
          <div><small>轨迹数</small><strong>{{ summary.total_tracks }}</strong></div>
          <div><small>需复核</small><strong>{{ summary.need_review }}</strong></div>
        </div>
        <div v-if="publishedRecordId" style="margin-top: 12px; font-size: 13px;">
          <p style="color: var(--text-secondary)">
            记录 ID：{{ publishedRecordId }}
            <span style="color: #52c41a; margin-left: 8px">✓ 已发布到业务库</span>
          </p>
        </div>
        <p v-if="!isPublished" style="margin-top: 8px; font-size: 12px; color: var(--text-secondary)">
          点击“发布到业务”将把识别结果写入模拟业务数据（带“模拟”标记），可在告警/工单等页面查看。
        </p>
        <p v-if="isPublished" style="margin-top: 8px; font-size: 12px; color: #52c41a">
          数据已成功发布。请使用顶部“过滤模拟数据”开关查看包含模拟数据的业务列表。
        </p>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-title"><h3>识别事件</h3></div>
        <div class="table full">
          <div class="table-head"><span>类型</span><span>起止时间</span><span>track</span><span>置信度</span><span>状态</span></div>
          <div v-for="(e, i) in (result.events || [])" :key="i" class="table-row">
            <span>{{ e.event_type }}</span>
            <span>{{ e.start_time.toFixed(2) }}s - {{ e.end_time.toFixed(2) }}s</span>
            <span>{{ (e.track_ids || []).join(", ") || "—" }}</span>
            <span>{{ e.confidence.toFixed(3) }}</span>
            <span>{{ e.requires_review ? "需复核" : "已确认" }}</span>
          </div>
        </div>
      </div>

      <div v-if="result && (result.classifier_predictions || []).length" class="panel">
        <div class="panel-title"><h3>分类概率（normal / violence / fall）</h3></div>
        <div class="table full">
          <div class="table-head"><span>Track</span><span>时间窗</span><span>正常</span><span>暴力</span><span>跌倒</span><span>复核</span></div>
          <div v-for="(p, i) in (result.classifier_predictions || [])" :key="i" class="table-row">
            <span>{{ p.track_id }}</span>
            <span>{{ p.start_time.toFixed(2) }}s - {{ p.end_time.toFixed(2) }}s</span>
            <span>{{ (p.smoothed_probabilities.normal * 100).toFixed(1) }}%</span>
            <span>{{ (p.smoothed_probabilities.violence * 100).toFixed(1) }}%</span>
            <span>{{ (p.smoothed_probabilities.fall * 100).toFixed(1) }}%</span>
            <span>{{ p.evidence?.requires_review ? "需复核" : "—" }}</span>
          </div>
        </div>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-title"><h3>轨迹列表</h3></div>
        <div class="table full">
          <div class="table-head"><span>Track ID</span><span>Generation</span><span>事件类型</span><span>路径长度</span><span>点数</span></div>
          <div v-for="(t, i) in (result.tracks || [])" :key="i" class="table-row">
            <span>{{ t.track_id }}</span>
            <span>{{ t.generation }}</span>
            <span>{{ (t.event_types || []).join(", ") || "—" }}</span>
            <span>{{ t.path_length_px ?? "—" }} px</span>
            <span>{{ (t.points || []).length }}</span>
          </div>
        </div>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-title">
          <div><h3>业务推演</h3><p>使用后端业务数据模拟规则命中与处置流程</p></div>
        </div>
        <div class="form-row">
          <label>置信度阈值</label>
          <input v-model.number="threshold" type="number" step="0.05" min="0" max="1" style="width: 120px" />
        </div>
        <button class="primary" @click="runSimulation">运行推演</button>
        <ul v-if="simulationOutput.length" class="sim-list">
          <li v-for="(line, i) in simulationOutput" :key="i">{{ line }}</li>
        </ul>
      </div>

      <div v-if="auth.hasPermission('device:update')" class="panel">
        <div class="panel-title">
          <div><h3>设备故障模拟</h3><p>人工模拟设备损坏：自动生成故障记录，设备置为故障并下调健康分，按平均负载自动派发维修工单</p></div>
        </div>
        <div class="form-row">
          <label>目标设备</label>
          <select v-model="faultDeviceId" class="fault-select">
            <option :value="undefined">请选择设备</option>
            <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>故障类型</label>
          <select v-model="faultType" class="fault-select">
            <option v-for="item in faultTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>故障级别</label>
          <select v-model="faultLevel" class="fault-select">
            <option v-for="item in faultLevelOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>故障描述</label>
          <input v-model="faultDesc" placeholder="选填，默认：人工模拟设备故障" style="flex: 1" />
        </div>
        <div class="toolbar" style="margin-top: 12px">
          <button class="primary" style="width: auto; min-width: 180px" :disabled="faultSubmitting || faultDeviceId == null" @click="submitFaultSimulate">
            {{ faultSubmitting ? "提交中..." : "生成模拟故障并派单" }}
          </button>
        </div>
        <div v-if="faultMessage" :class="['message', faultMessageType]">
          {{ faultMessage }}
        </div>
      </div>
    </template>

    <!-- ==================== 跨视频人员关联 ==================== -->
    <template v-else>
      <div class="banner-warning">
        ⚠️ 跨视频仅为外观辅助关联，非人脸识别，结果必须人工复核；辅助匹配不可作为身份判定依据。
      </div>

      <div class="panel upload-panel">
        <div class="panel-title">
          <div><h3>双视频上传</h3><p>分别上传两段视频，模型将对两段视频中的人员做外观特征辅助关联</p></div>
        </div>
        <div class="form-row">
          <label>视频 A</label>
          <div class="upload-zone">
            <input id="reid-video-a" type="file" accept="video/*" @change="onReidFileChange('A', $event)" />
            <label for="reid-video-a" class="upload-button">选择文件</label>
            <span v-if="reidFileA" class="file-name">{{ reidFileA.name }}（{{ (reidFileA.size / 1024 / 1024).toFixed(1) }} MB）</span>
            <span v-else class="placeholder">支持 MP4/AVI/MOV/MKV/WEBM，最大 2GB</span>
          </div>
        </div>
        <div class="form-row">
          <label>视频 B</label>
          <div class="upload-zone">
            <input id="reid-video-b" type="file" accept="video/*" @change="onReidFileChange('B', $event)" />
            <label for="reid-video-b" class="upload-button">选择文件</label>
            <span v-if="reidFileB" class="file-name">{{ reidFileB.name }}（{{ (reidFileB.size / 1024 / 1024).toFixed(1) }} MB）</span>
            <span v-else class="placeholder">支持 MP4/AVI/MOV/MKV/WEBM，最大 2GB</span>
          </div>
        </div>
        <div class="form-row">
          <label>摄像头 A</label>
          <select v-model="selectedReidDeviceA">
            <option :value="undefined">请选择摄像头 A</option>
            <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>摄像头 B</label>
          <select v-model="selectedReidDeviceB">
            <option :value="undefined">请选择摄像头 B</option>
            <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div class="toolbar" style="margin-top: 12px">
          <button class="primary" :disabled="!reidCanStart" @click="startReid">
            {{ reidWorking ? "分析中..." : "开始关联分析" }}
          </button>
          <button class="danger" style="margin-left: auto" :disabled="!reidCanClean" @click="deleteReidCollection">清理集合</button>
        </div>
        <div v-if="reidJobA.id" class="progress-wrap">
          <span style="width: 70px; flex-shrink: 0">视频 A</span>
          <div class="progress-bar" :style="{ width: Math.round(reidJobA.progress * 100) + '%' }"></div>
          <span>{{ Math.round(reidJobA.progress * 100) }}%（{{ statusText(reidJobA.status) }}）</span>
        </div>
        <div v-if="reidJobB.id" class="progress-wrap">
          <span style="width: 70px; flex-shrink: 0">视频 B</span>
          <div class="progress-bar" :style="{ width: Math.round(reidJobB.progress * 100) + '%' }"></div>
          <span>{{ Math.round(reidJobB.progress * 100) }}%（{{ statusText(reidJobB.status) }}）</span>
        </div>
        <p class="hint-text">{{ MODEL_QUEUE_HINT }}</p>
        <div v-if="reidMessage" :class="['message', reidMessageType]">
          {{ reidMessage }}
        </div>
      </div>

      <template v-if="reidResult">
        <div v-if="reidUnavailable" class="banner-error">
          跨视频模型不可用（reid_status = unavailable），本次无法输出人员匹配结果，请检查模型电脑 ReID 模型配置。
        </div>

        <template v-else>
          <div class="panel">
            <div class="panel-title"><h3>匹配明细（按视频轨迹）</h3></div>
            <div class="table full">
              <div class="table-head">
                <span>视频</span><span>Track</span><span>决策</span><span>全局人员</span><span>相似度</span><span>次佳</span><span>差值</span><span>样本数</span>
              </div>
              <template v-for="v in reidResult.videos" :key="v.job_id">
                <div v-for="t in (v.tracklets || [])" :key="`${v.job_id}-${t.track_id}`" class="table-row">
                  <span>{{ v.original_name }}</span>
                  <span>{{ t.track_id }}</span>
                  <span>{{ decisionText(t.decision) }}</span>
                  <span>{{ t.global_person_id || "—" }}</span>
                  <span>{{ formatScore(t.similarity) }}</span>
                  <span>{{ formatScore(t.runner_up) }}</span>
                  <span>{{ formatScore(t.margin) }}</span>
                  <span>{{ t.sample_count ?? "—" }}</span>
                </div>
              </template>
            </div>
            <p class="hint-text">
              模型：{{ reidResult.reid_model?.model_name || "—" }}；阈值来源：{{ reidResult.reid_model?.threshold_source || "—" }}；
              全局人员编号（global_person_id）仅为本次集合内的匿名编号，不代表真实身份。
            </p>
          </div>

          <div class="panel">
            <div class="panel-title"><h3>全局人员轨迹段</h3></div>
            <div class="table full">
              <div class="table-head"><span>全局人员</span><span>来源视频 job</span><span>Track</span><span>起止时间</span><span>点数</span></div>
              <template v-for="p in reidResult.persons" :key="p.global_person_id">
                <div v-for="(seg, i) in p.trajectory_segments" :key="`${p.global_person_id}-${i}`" class="table-row">
                  <span>{{ p.global_person_id }}</span>
                  <span>{{ seg.job_id.slice(0, 8) }}…</span>
                  <span>{{ seg.track_id }}</span>
                  <span>{{ seg.start_time.toFixed(2) }}s - {{ seg.end_time.toFixed(2) }}s</span>
                  <span>{{ (seg.points || []).length }}</span>
                </div>
              </template>
            </div>
          </div>

          <div class="video-panel">
            <div v-for="v in reidResult.videos" :key="v.job_id" class="panel" style="flex: 1">
              <div class="panel-title"><h3>标注视频：{{ v.original_name }}</h3></div>
              <video v-if="v.status === 'completed'" :src="modelJobVideoUrl(v.job_id)" controls style="width: 100%; max-height: 360px"></video>
            </div>
          </div>

          <div class="toolbar" style="margin-top: 12px">
            <button class="success" :disabled="!reidCanPublish" @click="publishReidRecord">
              {{ reidPublishing ? "发布中..." : "发布到业务" }}
            </button>
          </div>
        </template>
      </template>
    </template>
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.tab-bar button {
  padding: 8px 20px;
  border: 1px solid #d0d7de;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}
.tab-bar button.active {
  background: #3788e8;
  color: #fff;
  border-color: #3788e8;
}
.banner-warning {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  color: #ad6800;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.banner-error {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  color: #cf1322;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.hint-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 8px;
  line-height: 1.6;
}
.link-btn {
  border: none;
  background: none;
  color: #3788e8;
  cursor: pointer;
  font-size: 13px;
  text-decoration: underline;
  padding: 0;
}
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar .primary,
.toolbar .success,
.toolbar .danger {
  width: 120px;
  padding: 10px 17px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  text-align: center;
  white-space: nowrap;
}
button.primary {
  background: #3788e8;
  color: #fff;
  border: 1px solid #3788e8;
}
button.success {
  background: #52c41a;
  color: #fff !important;
  border: 1px solid #52c41a;
}
button.danger {
  background: #ff4d4f;
  color: #fff !important;
  border: 1px solid #ff4d4f;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.form-row label {
  width: 120px;
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.form-row input,
.form-row select,
.form-row textarea {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #d0d7de;
  border-radius: 4px;
  font-size: 13px;
}
.upload-zone {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}
.upload-zone input[type="file"] {
  display: none;
}
.upload-button {
  padding: 6px 14px;
  border: 1px solid #d0d7de;
  border-radius: 4px;
  background: #f6f8fa;
  cursor: pointer;
  font-size: 13px;
}
.file-name {
  font-size: 13px;
  color: var(--text-primary);
}
.placeholder {
  font-size: 13px;
  color: var(--text-secondary);
}
.progress-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  font-size: 13px;
}
.progress-bar {
  height: 8px;
  background: #3788e8;
  border-radius: 4px;
  flex: 1;
}
.video-panel {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.stats {
  display: flex;
  gap: 24px;
  margin-top: 12px;
}
.stats div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stats small {
  font-size: 12px;
  color: var(--text-secondary);
}
.stats strong {
  font-size: 24px;
  font-weight: 600;
}
.sim-list {
  margin-top: 12px;
  padding-left: 20px;
  color: var(--text-primary);
  font-size: 13px;
}
.message {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  white-space: pre-line;
}
.fault-select {
  max-width: 420px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.message.info {
  background: #e6f4ff;
  color: #1677ff;
}
.message.success {
  background: #f6ffed;
  color: #389e0d;
}
.message.error {
  background: #fff2f0;
  color: #cf1322;
}
</style>
