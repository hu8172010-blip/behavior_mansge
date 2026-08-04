<template>
  <div class="modal-mask" v-if="visible" @click.self="close">
    <div class="modal-box repair-modal">
      <div class="modal-header">
        <h3>维修工单详情 {{ detail ? `- ${detail.order_no}` : "" }}</h3>
        <button class="modal-close" @click="close">&times;</button>
      </div>
      <div class="modal-body" v-if="detail">
        <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>

        <h4 class="section-title">工单基础信息</h4>
        <div class="info-grid">
          <div class="info-item"><span class="label">工单ID</span><span class="value">{{ detail.id }}</span></div>
          <div class="info-item"><span class="label">工单编号</span><span class="value">{{ detail.order_no }}</span></div>
          <div class="info-item"><span class="label">工单状态</span><span class="value" :class="statusClass(detail.status)">● {{ statusLabel(detail.status) }}</span></div>
          <div class="info-item"><span class="label">创建时间</span><span class="value">{{ detail.create_time || "-" }}</span></div>
          <div class="info-item">
            <span class="label">绑定故障记录ID</span>
            <span class="value"><a class="link" @click="goFault">#{{ detail.fault_id }}</a></span>
          </div>
          <div class="info-item"><span class="label">故障类型</span><span class="value">{{ faultTypeLabel(detail.fault_type) }}</span></div>
          <div class="info-item"><span class="label">故障等级</span><span class="value" :class="detail.fault_level === 'CRITICAL' || detail.fault_level === 'HIGH' ? 'danger' : detail.fault_level === 'MEDIUM' ? 'warn' : ''">{{ faultLevelLabel(detail.fault_level) }}</span></div>
          <div class="info-item"><span class="label">故障发生时间</span><span class="value">{{ detail.fault_occurrence_time || "-" }}</span></div>
          <div class="info-item full"><span class="label">故障描述</span><span class="value">{{ detail.fault_desc || "-" }}</span></div>
        </div>

        <h4 class="section-title">关联设备信息</h4>
        <div class="info-grid">
          <div class="info-item">
            <span class="label">设备名称 / 编号</span>
            <span class="value"><a class="link" @click="goDevice">{{ detail.device_name || "-" }}</a>（{{ detail.device_code }}）</span>
          </div>
          <div class="info-item"><span class="label">设备类型</span><span class="value">{{ deviceTypeLabel(detail.device_type) }}</span></div>
          <div class="info-item"><span class="label">IP 地址</span><span class="value">{{ detail.device_ip || "-" }}</span></div>
          <div class="info-item"><span class="label">安装位置</span><span class="value">{{ detail.device_region ? detail.device_region + " · " : "" }}{{ detail.device_location || "-" }}</span></div>
        </div>

        <h4 class="section-title">派发信息</h4>
        <div class="info-grid">
          <div class="info-item"><span class="label">自动派单时间</span><span class="value">{{ detail.assigned_at || "-" }}</span></div>
          <div class="info-item"><span class="label">计划处理时间</span><span class="value">{{ detail.plan_finish_time || "-" }}</span></div>
          <div class="info-item"><span class="label">维修负责人</span><span class="value">{{ detail.assigned_name || "待派发" }}</span></div>
          <div class="info-item"><span class="label">派发结果</span><span class="value">{{ detail.dispatch_result === "SUCCESS" ? `派发成功（候选 ${detail.candidate_count} 人）` : detail.dispatch_result === "NO_CANDIDATE" ? "无候选维修人员" : "-" }}</span></div>
          <div class="info-item full"><span class="label">分配规则说明</span><span class="value">{{ detail.dispatch_rule_desc || "-" }}</span></div>
        </div>

        <h4 class="section-title">业务内容</h4>
        <template v-if="canEdit">
          <label class="form-label">损坏原因（必填）</label>
          <input v-model="finishForm.damage_cause" placeholder="如 电源模块老化导致断电" />
          <label class="form-label">维修情况（必填）</label>
          <input v-model="finishForm.repair_detail" placeholder="如 已更换电源模块，复检画面正常" />
          <button class="primary submit-btn" :disabled="submitting" @click="submitFinish">{{ submitting ? "提交中..." : "提交归档（设备将恢复在线）" }}</button>
        </template>
        <div class="info-grid" v-else>
          <div class="info-item full"><span class="label">损坏原因</span><span class="value">{{ detail.damage_cause || "-" }}</span></div>
          <div class="info-item full"><span class="label">维修情况</span><span class="value">{{ detail.repair_detail || "-" }}</span></div>
          <div class="info-item"><span class="label">维修完成时间</span><span class="value">{{ detail.completed_at || "-" }}</span></div>
          <div class="info-item"><span class="label">归档操作人</span><span class="value">{{ detail.operator_name || "-" }}</span></div>
        </div>

        <button v-if="canAccept" class="primary submit-btn" :disabled="submitting" @click="submitAccept">{{ submitting ? "提交中..." : "接单（开始维修）" }}</button>

        <h4 class="section-title">状态履历</h4>
        <div class="timeline">
          <div v-for="step in detail.history" :key="step.status" class="timeline-item">
            <span class="timeline-dot" :class="statusClass(step.status)"></span>
            <div><b>{{ step.status_name }}</b><small>{{ step.time || "-" }}　{{ step.operator || "" }}</small></div>
          </div>
        </div>

        <h4 class="section-title">操作日志</h4>
        <table class="data-table" v-if="detail.logs.length">
          <thead>
            <tr><th>时间</th><th>操作人</th><th>动作</th></tr>
          </thead>
          <tbody>
            <tr v-for="(log, idx) in detail.logs" :key="idx">
              <td>{{ log.operated_at }}</td>
              <td>{{ log.operator_name }}</td>
              <td><small>{{ actionLabel(log.action) }}</small></td>
            </tr>
          </tbody>
        </table>
        <p class="empty-text" v-else>暂无操作日志</p>
      </div>
      <div class="modal-body empty" v-else-if="loadError">{{ loadError }}</div>
      <div class="modal-body empty" v-else>加载中...</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api, type RepairOrderDetail } from "../api";
import { useAuthStore } from "../stores/auth";

const props = defineProps<{ visible: boolean; orderId: number | null }>();
const emit = defineEmits<{ (e: "update:visible", value: boolean): void; (e: "changed", message: string): void }>();

const router = useRouter();
const auth = useAuthStore();

const detail = ref<RepairOrderDetail | null>(null);
const loadError = ref("");
const errorText = ref("");
const submitting = ref(false);
const finishForm = reactive({ damage_cause: "", repair_detail: "" });

const statusOptions = [
  { value: "PENDING", label: "待处理" },
  { value: "REPAIRING", label: "维修中" },
  { value: "COMPLETED", label: "已完成" },
];
const faultTypeMap: Record<string, string> = { HEARTBEAT_TIMEOUT: "心跳超时", VIDEO_ABNORMAL: "画面异常", HARDWARE: "硬件损坏", NETWORK: "网络中断", OTHER: "其他" };
const faultLevelMap: Record<string, string> = { LOW: "低", MEDIUM: "中", HIGH: "高", CRITICAL: "严重" };
const deviceTypeMap: Record<string, string> = { CAMERA: "摄像头", NVR: "录像机", EDGE: "边缘分析盒" };
const actionMap: Record<string, string> = {
  simulate_fault: "模拟设备故障",
  accept_repair_order: "维修接单",
  finish_repair_order: "完成归档",
  close_fault: "关闭故障",
  create: "新增设备",
  update: "编辑设备",
};

const isOperator = computed(() => Boolean(detail.value && auth.hasPermission("device:repair") && (detail.value.assigned_to === auth.accountId || auth.typeId === 1)));
const canEdit = computed(() => Boolean(isOperator.value && detail.value?.status === "REPAIRING"));
const canAccept = computed(() => Boolean(isOperator.value && detail.value?.status === "PENDING"));

function statusLabel(value: string): string {
  return statusOptions.find((item) => item.value === value)?.label || value;
}
function statusClass(value: string): string {
  return value === "COMPLETED" ? "success" : value === "REPAIRING" ? "warn" : "";
}
function faultTypeLabel(value: string | null): string {
  return value ? faultTypeMap[value] || value : "-";
}
function faultLevelLabel(value: string | null): string {
  return value ? faultLevelMap[value] || value : "-";
}
function deviceTypeLabel(value: string | null): string {
  return value ? deviceTypeMap[value] || value : "-";
}
function actionLabel(value: string | null): string {
  return value ? actionMap[value] || value : "-";
}

watch(
  () => [props.visible, props.orderId],
  async ([visible, orderId]) => {
    if (visible && orderId) {
      detail.value = null;
      loadError.value = "";
      errorText.value = "";
      Object.assign(finishForm, { damage_cause: "", repair_detail: "" });
      try {
        detail.value = await api.repairOrderDetail(orderId);
        finishForm.damage_cause = detail.value.damage_cause || "";
        finishForm.repair_detail = detail.value.repair_detail || "";
      } catch (error: any) {
        loadError.value = error.message || "加载失败";
      }
    }
  }
);

async function reload() {
  if (!props.orderId) return;
  detail.value = await api.repairOrderDetail(props.orderId);
}

async function submitAccept() {
  submitting.value = true;
  try {
    await api.acceptRepairOrder(props.orderId!);
    await reload();
    emit("changed", `工单 ${detail.value?.order_no} 已接单，进入维修中`);
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

async function submitFinish() {
  if (!finishForm.damage_cause.trim() || !finishForm.repair_detail.trim()) {
    errorText.value = "请填写损坏原因与维修情况";
    return;
  }
  submitting.value = true;
  try {
    await api.finishRepairOrder(props.orderId!, { damage_cause: finishForm.damage_cause.trim(), repair_detail: finishForm.repair_detail.trim() });
    emit("changed", `工单 ${detail.value?.order_no} 已完成归档，设备状态已恢复`);
    close();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

function goDevice() {
  close();
  router.push("/device/list");
}
function goFault() {
  close();
  router.push({ path: "/device/list", query: { tab: "faults" } });
}
function close() {
  emit("update:visible", false);
}
</script>

<style scoped>
.repair-modal {
  max-width: 760px;
  width: 92%;
  max-height: 86vh;
  overflow-y: auto;
}
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 8px;
}
.info-item.full {
  grid-column: 1 / -1;
}
.info-item .label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.info-item .value {
  font-size: 14px;
  color: var(--text-primary);
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 12px;
  color: var(--text-primary);
}
.link {
  color: #3788e8;
  cursor: pointer;
}
.form-label {
  display: block;
  margin: 12px 0 6px;
  font-size: 13px;
  color: var(--text-secondary);
}
.form-label + input {
  width: 100%;
  height: 38px;
  padding: 0 12px;
  border: 1px solid #dbe3ed;
  border-radius: 5px;
  outline: 0;
}
.submit-btn {
  margin-top: 16px;
}
.timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 8px;
}
.timeline-item {
  display: flex;
  align-items: center;
  gap: 10px;
}
.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #9aa6b5;
}
.timeline-item b {
  display: block;
  font-size: 13px;
  color: var(--text-primary);
}
.timeline-item small {
  color: var(--text-secondary);
  font-size: 12px;
}
.empty-text {
  color: var(--text-secondary);
  font-size: 13px;
}
.danger {
  color: #e76b71;
}
.warn {
  color: #e9a052;
}
.success {
  color: #76b89d;
}
</style>
