<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api, type AlertItem, type MetaEnums, type WorkOrderItem } from "../api";
import { useAuthStore } from "../stores/auth";
import TrackDetailModal from "../components/TrackDetailModal.vue";
import { formatBehaviorDesc } from "../utils/behaviorDisplay";

const router = useRouter();
const auth = useAuthStore();

const activeTab = ref<"alerts" | "orders">("alerts");
const enums = ref<MetaEnums | null>(null);
const errorText = ref("");
const notice = ref("");

const alertStatusId = ref<number | undefined>(1);
const alertSeverityId = ref<number | undefined>(undefined);
const alertKeyword = ref("");
const alertPage = ref(1);
const alertSize = 10;
const alertTotal = ref(0);
const alerts = ref<AlertItem[]>([]);
const alertsLoading = ref(false);

const orderStatusId = ref<number | undefined>(undefined);
const orderPage = ref(1);
const orderSize = 10;
const orderTotal = ref(0);
const orders = ref<WorkOrderItem[]>([]);
const ordersLoading = ref(false);

const showIgnore = ref(false);
const showAssign = ref(false);
const currentAlert = ref<AlertItem | null>(null);
const ignoreNote = ref("");
const assignTo = ref<number>(0);
const submitting = ref(false);
const exporting = ref(false);
const detailChainId = ref<number | null>(null);

async function loadAlerts() {
  alertsLoading.value = true;
  try {
    const result = await api.alerts({ status_id: alertStatusId.value, severity_id: alertSeverityId.value, keyword: alertKeyword.value || undefined, page: alertPage.value, size: alertSize });
    alerts.value = result.list;
    alertTotal.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    alertsLoading.value = false;
  }
}

async function exportAlerts() {
  exporting.value = true;
  try {
    await api.exportAlerts({ status_id: alertStatusId.value, severity_id: alertSeverityId.value, keyword: alertKeyword.value || undefined });
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

async function loadOrders() {
  ordersLoading.value = true;
  try {
    const result = await api.workOrders({ status_id: orderStatusId.value, page: orderPage.value, size: orderSize });
    orders.value = result.list;
    orderTotal.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    ordersLoading.value = false;
  }
}

function searchAlerts() {
  alertPage.value = 1;
  loadAlerts();
}

function searchOrders() {
  orderPage.value = 1;
  loadOrders();
}

async function confirmAlert(item: AlertItem) {
  submitting.value = true;
  try {
    await api.confirmAlert(item.alert_id);
    item.alert_status_id = 2;
    item.status_name = "已确认";
    notice.value = `告警 #${item.alert_id} 已确认，可继续派单`;
    await auth.refreshPendingCount();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

function openIgnore(item: AlertItem) {
  currentAlert.value = item;
  ignoreNote.value = "";
  showIgnore.value = true;
}

async function submitIgnore() {
  if (!currentAlert.value) return;
  submitting.value = true;
  try {
    await api.ignoreAlert(currentAlert.value.alert_id, ignoreNote.value || undefined);
    showIgnore.value = false;
    currentAlert.value.alert_status_id = 6;
    currentAlert.value.status_name = "已忽略";
    notice.value = `告警 #${currentAlert.value.alert_id} 已按误报忽略`;
    await auth.refreshPendingCount();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

const showReview = ref(false);
const currentReview = ref<AlertItem | null>(null);
const reviewFalsePositive = ref(false);
const reviewPersonIdentity = ref<"registered" | "stranger">("stranger");
const reviewNote = ref("");

function openReview(item: AlertItem) {
  currentReview.value = item;
  reviewFalsePositive.value = false;
  reviewPersonIdentity.value = "stranger";
  reviewNote.value = "";
  showReview.value = true;
}

function openVideo(item: AlertItem) {
  const urls = [item.video_path, item.video_path_b].filter(Boolean);
  if (!urls.length) {
    alert("未关联原始视频");
    return;
  }
  for (const u of urls) {
    if (u) window.open(u, "_blank");
  }
}

async function submitReview() {
  if (!currentReview.value) return;
  submitting.value = true;
  try {
    await api.reviewAlert(currentReview.value.alert_id, {
      false_positive: reviewFalsePositive.value,
      person_identity: reviewPersonIdentity.value,
      note: reviewNote.value || undefined,
    });
    showReview.value = false;
    currentReview.value.alert_status_id = 6;
    currentReview.value.status_name = "已复核归档";
    notice.value = `告警 #${currentReview.value.alert_id} 已复核归档`;
    await auth.refreshPendingCount();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

function openAssign(item: AlertItem) {
  currentAlert.value = item;
  assignTo.value = enums.value?.handlers[0]?.account_id ?? 0;
  showAssign.value = true;
}

async function submitAssign() {
  if (!currentAlert.value || !assignTo.value) return;
  submitting.value = true;
  try {
    const result: any = await api.createWorkOrder(currentAlert.value.alert_id, assignTo.value);
    showAssign.value = false;
    currentAlert.value.alert_status_id = 3;
    currentAlert.value.status_name = "已派单";
    notice.value = `派单成功，工单号 ${result.work_order_no}，已切换到工单列表`;
    orderStatusId.value = undefined;
    orderPage.value = 1;
    activeTab.value = "orders";
    await Promise.all([loadOrders(), auth.refreshPendingCount()]);
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

function levelClass(level: string): string {
  return level === "高" ? "danger" : level === "中" ? "warn" : "success";
}

onMounted(async () => {
  try {
    enums.value = await api.enums();
  } catch {
    enums.value = null;
  }
  await Promise.all([loadAlerts(), loadOrders()]);
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>告警待办队列</h2><p>确认异常行为预警，按需派发处置工单，闭环跟踪</p></div>
      <div class="tabs">
        <button :class="{ selected: activeTab === 'alerts' }" @click="activeTab = 'alerts'">预警待办</button>
        <button :class="{ selected: activeTab === 'orders' }" @click="activeTab = 'orders'">处置工单</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <div v-if="activeTab === 'alerts'" class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="alertKeyword" placeholder="搜索事件类型或描述关键字" @keyup.enter="searchAlerts" /></div>
        <select v-model="alertStatusId" @change="searchAlerts">
          <option :value="undefined">全部状态</option>
          <option v-for="item in enums?.alert_statuses || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="alertSeverityId" @change="searchAlerts">
          <option :value="undefined">全部级别</option>
          <option v-for="item in enums?.severity_levels || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <button class="primary" @click="searchAlerts">查询</button>
        <button :disabled="exporting" @click="exportAlerts">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>预警时间</span><span>事件类型</span><span>级别</span><span>位置 / 设备</span><span>状态</span><span>操作</span></div>
        <div v-if="alertsLoading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!alerts.length" class="table-row"><span>暂无符合条件的预警</span></div>
        <div v-for="item in alerts" :key="item.alert_id" class="table-row">
          <span>{{ item.alert_time }}</span>
          <span><b>{{ item.type_name }}</b><em v-if="item.is_marked_focus" class="orange">　◆重点关注</em><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span><br /><small>{{ formatBehaviorDesc(item.description, item.type_name) || "—" }}</small></span>
          <span :class="levelClass(item.level_name)">● {{ item.level_name }}</span>
          <span>{{ item.region_name || "—" }}<br /><small>{{ item.device_name }}</small></span>
          <span>{{ item.status_name }}<br /><small v-if="item.track_id"><button class="link" @click="detailChainId = item.track_id">查看轨迹</button></small></span>
          <span class="row-actions">
            <button v-if="item.alert_status_id === 1" class="btn-sm" :disabled="submitting" @click="openVideo(item)">查看视频</button>
            <button v-if="item.alert_status_id === 1" class="btn-sm btn-confirm" :disabled="submitting" @click="openReview(item)">人工复核</button>
            <button v-if="item.alert_status_id === 2 && auth.hasPermission('alarm:assign')" class="btn-sm btn-assign" :disabled="submitting" @click="openAssign(item)">派单</button>
            <span v-if="item.alert_status_id >= 3 && item.alert_status_id <= 5">—</span>
          </span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ alertTotal }} 条</span>
        <button :disabled="alertPage <= 1" @click="alertPage--; loadAlerts()">上一页</button>
        <span>第 {{ alertPage }} 页</span>
        <button :disabled="alertPage * alertSize >= alertTotal" @click="alertPage++; loadAlerts()">下一页</button>
      </div>
    </div>

    <div v-else class="panel data-panel">
      <div class="toolbar">
        <select v-model="orderStatusId" @change="searchOrders">
          <option :value="undefined">全部状态</option>
          <option v-for="item in enums?.work_order_statuses || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <button class="primary" @click="searchOrders">查询</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>工单号</span><span>事件类型</span><span>级别</span><span>处理人</span><span>派单时间</span><span>状态</span><span>操作</span></div>
        <div v-if="ordersLoading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!orders.length" class="table-row"><span>暂无工单</span></div>
        <div v-for="item in orders" :key="item.work_order_id" class="table-row">
          <span><b>{{ item.work_order_no }}</b><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span></span>
          <span>{{ item.type_name }}<br /><small>{{ formatBehaviorDesc(item.description, item.type_name) || "—" }}</small></span>
          <span :class="levelClass(item.level_name)">● {{ item.level_name }}</span>
          <span>{{ item.assignee_name }}</span>
          <span>{{ item.assigned_at }}</span>
          <span>{{ item.status_name }}</span>
          <span><button class="link" @click="router.push('/workorder/detail/' + item.work_order_id)">查看详情</button></span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ orderTotal }} 条</span>
        <button :disabled="orderPage <= 1" @click="orderPage--; loadOrders()">上一页</button>
        <span>第 {{ orderPage }} 页</span>
        <button :disabled="orderPage * orderSize >= orderTotal" @click="orderPage++; loadOrders()">下一页</button>
      </div>
    </div>

    <div v-if="showIgnore" class="modal-mask" @click.self="showIgnore = false">
      <div class="modal">
        <button class="close" @click="showIgnore = false">×</button>
        <h2>忽略告警（误报）</h2>
        <p><b>事件：</b>{{ currentAlert?.type_name }}　<b>位置：</b>{{ currentAlert?.region_name }}</p>
        <label>误报原因（可选）</label>
        <input v-model="ignoreNote" placeholder="例如：保安正常巡楼" />
        <button class="primary" :disabled="submitting" @click="submitIgnore">确认忽略</button>
      </div>
    </div>

    <div v-if="showAssign" class="modal-mask" @click.self="showAssign = false">
      <div class="modal">
        <button class="close" @click="showAssign = false">×</button>
        <h2>派发处置工单</h2>
        <p><b>事件：</b>{{ currentAlert?.type_name }}　<b>级别：</b>{{ currentAlert?.level_name }}　<b>位置：</b>{{ currentAlert?.region_name }}</p>
        <label>选择处理人</label>
        <select v-model="assignTo" class="role-select">
          <option v-for="handler in enums?.handlers || []" :key="handler.account_id" :value="handler.account_id">{{ handler.real_name }}</option>
        </select>
        <button class="primary" :disabled="submitting || !assignTo" @click="submitAssign">确认派单</button>
      </div>
    </div>

    <div v-if="showReview" class="modal-mask" @click.self="showReview = false">
      <div class="modal">
        <button class="close" @click="showReview = false">×</button>
        <h2>人工复核</h2>
        <p><b>事件：</b>{{ currentReview?.type_name }}　<b>级别：</b>{{ currentReview?.level_name }}　<b>位置：</b>{{ currentReview?.region_name }}</p>
        <p><small>{{ formatBehaviorDesc(currentReview?.description, currentReview?.type_name || '') || '—' }}</small></p>
        <div class="form-row" style="display: block; margin-top: 12px">
          <label>是否误报</label>
          <select v-model="reviewFalsePositive" style="width: 100%; margin-top: 6px">
            <option :value="false">否</option>
            <option :value="true">是</option>
          </select>
        </div>
        <div class="form-row" style="display: block; margin-top: 12px">
          <label>人员身份</label>
          <select v-model="reviewPersonIdentity" style="width: 100%; margin-top: 6px">
            <option value="registered">数据库登记人员</option>
            <option value="stranger">陌生人</option>
          </select>
        </div>
        <div class="form-row" style="display: block; margin-top: 12px">
          <label>复核备注（可选）</label>
          <input v-model="reviewNote" placeholder="例如：已确认，非误报" style="width: 100%; margin-top: 6px" />
        </div>
        <div class="toolbar" style="margin-top: 16px">
          <button class="primary" :disabled="submitting" @click="submitReview">确认归档</button>
          <button :disabled="submitting" @click="openVideo(currentReview!)">查看视频</button>
        </div>
      </div>
    </div>

    <TrackDetailModal v-if="detailChainId" :chain-id="detailChainId" @close="detailChainId = null" />
  </div>
</template>
