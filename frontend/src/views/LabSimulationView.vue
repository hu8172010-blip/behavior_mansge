<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();

interface AnomalyEvent {
  event_type: string;
  start_time: number;
  end_time: number;
  confidence: number;
  track_ids: number[];
  requires_review?: boolean;
}

interface AnomalyTrack {
  track_id: number;
  generation: number;
  event_types: string[];
  first_seen: number;
  last_seen: number;
  path_length_px: number;
  point_count: number;
}

interface AnomalyResult {
  events: AnomalyEvent[];
  tracks: AnomalyTrack[];
  summary: { total_events: number; total_tracks: number; need_review: number; model_version?: string };
}

const videoFile = ref<File | null>(null);
const videoUrl = ref("");
const loading = ref(false);
const progress = ref(0);
const result = ref<AnomalyResult | null>(null);
const recordId = ref<number | null>(null);
const isPublished = ref(false);

const selectedDevice = ref<number | undefined>(undefined);
const devices = ref<{ id: number; name: string }[]>([]);

const calibration = ref(JSON.stringify({
  fall_seconds: 1.0,
  stationary_seconds: 20.0,
  dangerous_zones: [],
}, null, 2));

const threshold = ref(0.7);
const simulationOutput = ref<string[]>([]);
const message = ref("");
const messageType = ref<"info" | "success" | "error">("info");

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

const summary = computed(() => {
  if (!result.value) return null;
  return {
    total_events: result.value.events?.length || 0,
    total_tracks: result.value.tracks?.length || 0,
    need_review: (result.value.events || []).filter((e) => e.requires_review).length,
  };
});

const canPublish = computed(() => !!recordId.value && !!result.value && !isPublished.value);

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value);
  videoFile.value = file;
  videoUrl.value = URL.createObjectURL(file);
  recordId.value = null;
  result.value = null;
  isPublished.value = false;
}

let pollTimer: number | null = null;

function clearPoll() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onBeforeUnmount(() => {
  clearPoll();
});

onMounted(async () => {
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

async function startAnalyze() {
  if (!videoFile.value) return;
  if (selectedDevice.value == null) {
    message.value = "请选择模拟摄像头";
    messageType.value = "error";
    return;
  }
  loading.value = true;
  result.value = null;
  recordId.value = null;
  isPublished.value = false;
  simulationOutput.value = [];
  message.value = "正在提交识别任务（持久化归档...";
  messageType.value = "info";
  progress.value = 0;
  clearPoll();
  try {
    const deviceId = selectedDevice.value || 0;
    // 使用 persist 模式：识别完成后自动保存 LabRecord（不自动发布）
    const create = await api.labJobCreate(videoFile.value, deviceId, calibration.value, "persist", `模拟-${videoFile.value.name}`);
    progress.value = 5;
    message.value = "任务已提交，等待识别...";
    const jobId = create.job_id;
    pollTimer = window.setInterval(async () => {
      try {
        const st = await api.labJobGet(jobId);
        if (st.status === "completed") {
          progress.value = 100;
          result.value = (st.result as AnomalyResult | null);
          // 等待 record 落库（最多 10s）
          let waited = 0;
          while (!st.record_id && waited < 10) {
            await new Promise((r) => setTimeout(r, 1000));
            waited += 1;
            const latest = await api.labJobGet(jobId);
            if (latest.record_id) {
              recordId.value = latest.record_id;
              break;
            }
            if (latest.record_save_error) {
              throw new Error("识别完成，但保存记录失败：" + latest.record_save_error);
            }
          }
          if (!recordId.value && st.record_id) recordId.value = st.record_id;
          if (!recordId.value) {
            message.value = `识别完成！事件 ${summary.value?.total_events || 0} 个，轨迹 ${summary.value?.total_tracks || 0} 条。` + "\n⚠️ 记录保存超时，请前往“我的模拟记录”查看。点击发布仍可继续。";
            messageType.value = "info";
            clearPoll();
            loading.value = false;
            return;
          }
          clearPoll();
          message.value = `识别完成！事件 ${summary.value?.total_events || 0} 个，轨迹 ${summary.value?.total_tracks || 0} 条。已保存记录 ID：${recordId.value}。\n请点击“发布到业务”将数据写入模拟业务库。`;
          messageType.value = "success";
          loading.value = false;
        } else if (st.status === "failed") {
          clearPoll();
          progress.value = 0;
          message.value = st.error || "识别失败";
          messageType.value = "error";
          loading.value = false;
        } else {
          progress.value = Math.max(5, Math.round(st.progress * 100));
          message.value = `识别状态：${st.status}，进度 ${Math.round(st.progress * 100)}%`;
        }
      } catch (e: any) {
        clearPoll();
        progress.value = 0;
        message.value = e?.message || "查询任务失败";
        messageType.value = "error";
        loading.value = false;
      }
    }, 1000);
  } catch (e: any) {
    clearPoll();
    progress.value = 0;
    message.value = e?.message || "提交识别任务失败";
    messageType.value = "error";
    console.error(e);
    loading.value = false;
  }
}

async function publishRecord() {
  if (!result.value || !recordId.value) return;
  loading.value = true;
  message.value = "正在发布到业务...（读取已保存的识别结果写入业务表，不会重复推理）";
  messageType.value = "info";
  try {
    const data = await api.labRecordPublish(recordId.value);
    isPublished.value = true;
    const c = (data as any).counts;
    if (c) {
      const hint = `✅ 成功发布到业务！记录 ID：${recordId.value}。\n生成：异常行为 ${c.behavior_count} 条、预警 ${c.alert_count} 条、工单 ${c.work_order_count} 条、轨迹 ${c.track_count} 条、人员 ${c.person_count} 个。\n\n💡 请将顶部导航栏【过滤模拟数据】开关关闭，即可在业务列表（异常行为记录 / 告警待办 / 轨迹查询 中看到带“模拟”标签的数据。`;
      message.value = hint;
      messageType.value = "success";
      if (window.confirm(`${hint}\n\n是否立即关闭"过滤模拟数据"开关并前往异常行为记录查看？`)) {
        try {
          const { useSettingsStore } = await import("../stores/settings");
          const settings = useSettingsStore();
          settings.filterLabData = false;
        } catch (_) {}
        window.location.hash = "#/behaviors";
      }
    } else {
      message.value = `已发布到业务。`;
      messageType.value = "success";
    }
  } catch (e: any) {
    message.value = "发布失败：" + (e?.message || "未知错误");
    messageType.value = "error";
  } finally {
    loading.value = false;
  }
}

async function clearSandbox() {
  if (!window.confirm("确定清空所有模拟实验室数据吗？此操作不可恢复。")) return;
  try {
    await api.labClearSandbox();
    alert("模拟数据已清空");
  } catch (e: any) {
    alert(e?.message || "清空失败");
  }
}

async function submitFaultSimulate() {
  if (faultDeviceId.value == null) {
    faultMessage.value = "请选择目标设备";
    faultMessageType.value = "error";
    return;
  }
  faultSubmitting.value = true;
  faultMessage.value = "";
  try {
    const result = await api.simulateFault(faultDeviceId.value, {
      fault_type: faultType.value,
      fault_level: faultLevel.value,
      fault_desc: faultDesc.value || undefined,
    });
    faultMessage.value = result.assigned_name
      ? `已生成故障并自动派发工单 ${result.order_no} → ${result.assigned_name}，可前往「维修工单」页面处理`
      : `已生成故障工单 ${result.order_no}，暂无可用维修人员，待人工处理`;
    faultMessageType.value = "success";
  } catch (e: any) {
    faultMessage.value = e?.message || "模拟故障失败";
    faultMessageType.value = "error";
  } finally {
    faultSubmitting.value = false;
  }
}

function runSimulation() {
  if (!result.value) return;
  const out: string[] = [];
  const events = result.value.events || [];
  const severe = events.filter(
    (e) => ["suspected_fall", "suspected_violence", "dangerous_zone_proximity"].includes(e.event_type) && e.confidence >= threshold.value
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

onBeforeUnmount(() => {
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value);
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div>
        <h2>模拟实验室</h2>
        <p>上传本地视频，调用识别模型进行沙箱推演，支持结果保存与业务发布</p>
      </div>
    </div>

    <div class="panel upload-panel">
      <div class="panel-title">
        <div><h3>视频与参数</h3><p>选择视频并配置本次模拟上下文</p></div>
      </div>
      <div class="form-row">
        <label>上传视频</label>
        <div class="upload-zone">
          <input id="lab-video" type="file" accept="video/*" @change="onFileChange" />
          <label for="lab-video" class="upload-button">选择文件</label>
          <span v-if="videoFile" class="file-name">{{ videoFile.name }}（{{ (videoFile.size / 1024 / 1024).toFixed(1) }} MB）</span>
          <span v-else class="placeholder">支持 mp4/avi/mov，最大 500MB</span>
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
        <button class="primary" :disabled="loading || !videoFile || selectedDevice == null" @click="startAnalyze">
          {{ loading ? "识别中..." : "开始识别" }}
        </button>
        <button class="success" :disabled="!canPublish || loading" @click="publishRecord">
          {{ isPublished ? "已发布" : "发布到业务" }}
        </button>
        <button class="danger" @click="clearSandbox" style="margin-left: auto">清空模拟数据</button>
      </div>
      <div v-if="loading" class="progress-wrap">
        <div class="progress-bar" :style="{ width: progress + '%' }"></div>
        <span>{{ Math.round(progress) }}%</span>
      </div>
      <div v-if="message" :class="['message', messageType]">
        {{ message }}
      </div>
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

    <div v-if="videoUrl || result" class="video-panel">
      <div class="panel" style="flex: 1">
        <div class="panel-title"><h3>视频预览</h3></div>
        <video v-if="videoUrl" :src="videoUrl" controls style="width: 100%; max-height: 420px"></video>
      </div>
      <div v-if="result" class="panel" style="flex: 1">
        <div class="panel-title"><h3>识别摘要</h3></div>
        <div class="stats" v-if="summary">
          <div><small>事件数</small><strong>{{ summary.total_events }}</strong></div>
          <div><small>轨迹数</small><strong>{{ summary.total_tracks }}</strong></div>
          <div><small>需复核</small><strong>{{ summary.need_review }}</strong></div>
        </div>
        <div v-if="recordId" style="margin-top: 12px; font-size: 13px;">
          <p style="color: var(--text-secondary)">记录 ID：{{ recordId }} 
            <span v-if="isPublished" style="color: #52c41a; margin-left: 8px">✓ 已发布到业务库</span>
            <span v-else style="color: #faad14; margin-left: 8px">⏳ 待发布</span>
          </p>
        </div>
        <button class="success" style="width: 100%; margin-top: 12px" :disabled="!canPublish" @click="publishRecord">
          {{ isPublished ? "已发布" : "发布到业务" }}
        </button>
        <p v-if="!isPublished && result" style="margin-top: 8px; font-size: 12px; color: var(--text-secondary)">
          点击“发布到业务”将把识别结果写入模拟业务数据（带标记），可在告警/工单等页面查看。
        </p>
        <p v-if="isPublished" style="margin-top: 8px; font-size: 12px; color: #52c41a">
          数据已成功发布。您可以前往“我的模拟记录”查看详情，或使用全局开关查看包含模拟数据的业务列表。
        </p>
      </div>
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

    <div v-if="result" class="panel">
      <div class="panel-title"><h3>轨迹列表</h3></div>
      <div class="table full">
        <div class="table-head"><span>Track ID</span><span>Generation</span><span>事件类型</span><span>路径长度</span><span>点数</span></div>
        <div v-for="(t, i) in (result.tracks || [])" :key="i" class="table-row">
          <span>{{ t.track_id }}</span>
          <span>{{ t.generation }}</span>
          <span>{{ t.event_types.join(", ") || "—" }}</span>
          <span>{{ t.path_length_px }} px</span>
          <span>{{ t.point_count }}</span>
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
  </div>
</template>

<style scoped>
.mode-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  background: #f6f8fa;
}
.mode-bar.persist {
  background: #fff7e6;
}
.mode-switch {
  display: flex;
  gap: 8px;
}
.mode-switch button {
  padding: 6px 14px;
  border: 1px solid #d0d7de;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
.mode-switch button.active {
  background: #3788e8;
  color: #fff;
  border-color: #3788e8;
}
.mode-hint {
  font-size: 13px;
  color: var(--text-secondary);
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
