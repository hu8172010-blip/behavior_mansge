<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api, type AlertItem, type MetaEnums, type WorkOrderItem } from "../api";
import { useAuthStore } from "../stores/auth";
import { useSettingsStore } from "../stores/settings";
import TrackDetailModal from "../components/TrackDetailModal.vue";

const router = useRouter();
const auth = useAuthStore();
const settings = useSettingsStore();

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
const alertJump = ref<number | null>(null);

const orderStatusId = ref<number | undefined>(undefined);
const orderSeverityId = ref<number | undefined>(undefined);
const orderTypeId = ref<number | undefined>(undefined);
const orderAssigneeId = ref<number | undefined>(undefined);
const orderAssigneeInput = ref("");
const orderKeyword = ref("");
const orderStartTime = ref("");
const orderEndTime = ref("");
const orderPage = ref(1);
const orderSize = 10;
const orderTotal = ref(0);
const orders = ref<WorkOrderItem[]>([]);
const ordersLoading = ref(false);
const orderJump = ref<number | null>(null);
const orderExporting = ref(false);

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
    notice.value = "告警已导出为 CSV 文件";
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

async function loadOrders() {
  ordersLoading.value = true;
  try {
    const assigneeName = orderAssigneeInput.value.trim();
    const result = await api.workOrders({
      status_id: orderStatusId.value,
      severity_id: orderSeverityId.value,
      type_id: orderTypeId.value,
      assignee_id: orderAssigneeId.value,
      assignee_name: !orderAssigneeId.value && assigneeName ? assigneeName : undefined,
      keyword: orderKeyword.value || undefined,
      start_time: orderStartTime.value ? orderStartTime.value.replace("T", " ") : undefined,
      end_time: orderEndTime.value ? orderEndTime.value.replace("T", " ") : undefined,
      page: orderPage.value,
      size: orderSize,
    });
    orders.value = result.list;
    orderTotal.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    ordersLoading.value = false;
  }
}

async function exportOrders() {
  orderExporting.value = true;
  try {
    const assigneeName = orderAssigneeInput.value.trim();
    await api.exportWorkOrders({
      status_id: orderStatusId.value,
      severity_id: orderSeverityId.value,
      type_id: orderTypeId.value,
      assignee_id: orderAssigneeId.value,
      assignee_name: !orderAssigneeId.value && assigneeName ? assigneeName : undefined,
      keyword: orderKeyword.value || undefined,
      start_time: orderStartTime.value ? orderStartTime.value.replace("T", " ") : undefined,
      end_time: orderEndTime.value ? orderEndTime.value.replace("T", " ") : undefined,
    });
    notice.value = "工单已导出为 CSV 文件";
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    orderExporting.value = false;
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

function resetAlertFilter() {
  alertStatusId.value = 1;
  alertSeverityId.value = undefined;
  alertKeyword.value = "";
  alertPage.value = 1;
  alertJump.value = null;
  loadAlerts();
}

function resetOrderFilter() {
  orderStatusId.value = undefined;
  orderSeverityId.value = undefined;
  orderTypeId.value = undefined;
  orderAssigneeId.value = undefined;
  orderAssigneeInput.value = "";
  orderKeyword.value = "";
  orderStartTime.value = "";
  orderEndTime.value = "";
  orderPage.value = 1;
  orderJump.value = null;
  loadOrders();
}

function goToAlertPage() {
  const maxPage = Math.max(1, Math.ceil(alertTotal.value / alertSize));
  let p = Number(alertJump.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === alertPage.value) return;
  alertPage.value = p;
  alertJump.value = null;
  loadAlerts();
}

function goToOrderPage() {
  const maxPage = Math.max(1, Math.ceil(orderTotal.value / orderSize));
  let p = Number(orderJump.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === orderPage.value) return;
  orderPage.value = p;
  orderJump.value = null;
  loadOrders();
}

// 顶部"过滤模拟数据"开关切换时，自动刷新两个 Tab
watch(() => settings.filterLabData, () => {
  if (activeTab.value === "alerts") loadAlerts();
  else loadOrders();
});

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
        <div class="search"><span>⌕</span><input v-model="alertKeyword" placeholder="搜索事件类型/描述/位置/设备" @keyup.enter="searchAlerts" /></div>
        <select v-model="alertStatusId" @change="searchAlerts">
          <option :value="undefined">全部状态</option>
          <option v-for="item in enums?.alert_statuses || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="alertSeverityId" @change="searchAlerts">
          <option :value="undefined">全部级别</option>
          <option v-for="item in enums?.severity_levels || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <button class="primary" @click="searchAlerts">查询</button>
        <button @click="resetAlertFilter">重置</button>
        <button :disabled="exporting" @click="exportAlerts">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>预警时间</span><span>事件类型</span><span>级别</span><span>位置 / 设备</span><span>状态</span><span>操作</span></div>
        <div v-if="alertsLoading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!alerts.length" class="table-row"><span>暂无符合条件的预警</span></div>
        <div v-for="item in alerts" :key="item.alert_id" class="table-row">
          <span>{{ item.alert_time }}</span>
          <span><b>{{ item.type_name }}</b><em v-if="item.is_marked_focus" class="orange">　◆重点关注</em><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span><br /><small>{{ item.description }}</small></span>
          <span :class="levelClass(item.level_name)">● {{ item.level_name }}</span>
          <span>{{ item.region_name || "—" }}<br /><small>{{ item.device_name }}</small></span>
          <span>{{ item.status_name }}<br /><small v-if="item.track_id"><button class="link" @click="detailChainId = item.track_id">查看轨迹</button></small></span>
          <span class="row-actions">
            <button v-if="item.alert_status_id === 1 && auth.hasPermission('alarm:confirm')" class="btn-sm btn-confirm" :disabled="submitting" @click="confirmAlert(item)">确认</button>
            <button v-if="item.alert_status_id === 1 && auth.hasPermission('alarm:confirm')" class="btn-sm btn-ignore" :disabled="submitting" @click="openIgnore(item)">误报忽略</button>
            <button v-if="item.alert_status_id === 2 && auth.hasPermission('alarm:assign')" class="btn-sm btn-assign" :disabled="submitting" @click="openAssign(item)">派单</button>
            <span v-if="item.alert_status_id >= 3 && item.alert_status_id <= 5">—</span>
          </span>
        </div>
      </div>
      <div class="pager">
        <span>共 {{ alertTotal }} 条</span>
        <button :disabled="alertPage <= 1" @click="alertPage--; loadAlerts()">上一页</button>
        <span>第 {{ alertPage }} 页 / 共 {{ Math.max(1, Math.ceil(alertTotal / alertSize)) }} 页</span>
        <button :disabled="alertPage * alertSize >= alertTotal" @click="alertPage++; loadAlerts()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="alertJump" type="number" min="1" :max="Math.max(1, Math.ceil(alertTotal / alertSize))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToAlertPage" />
        <span>页</span>
        <button @click="goToAlertPage" :disabled="!alertJump">GO</button>
      </div>
    </div>

    <div v-else class="panel data-panel">
      <!-- 第一行：核心搜索条件 + 查询 -->
      <div class="toolbar toolbar-row">
        <div class="search"><span>⌕</span><input v-model="orderKeyword" placeholder="搜索工单号/描述" @keyup.enter="searchOrders" /></div>
        <select v-model="orderStatusId" @change="searchOrders">
          <option :value="undefined">全部状态</option>
          <option v-for="item in enums?.work_order_statuses || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="orderSeverityId" @change="searchOrders">
          <option :value="undefined">全部级别</option>
          <option v-for="item in enums?.severity_levels || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="orderTypeId" @change="searchOrders">
          <option :value="undefined">全部事件类型</option>
          <option v-for="item in enums?.behavior_types || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <input v-model="orderAssigneeInput" type="text" placeholder="输入姓名搜索处理人" @keyup.enter="searchOrders" style="width: 180px; height: 32px; padding: 0 10px; border: 1px solid #dbe3ed; border-radius: 4px; outline: 0;" />
        <button class="primary" @click="searchOrders">查询</button>
      </div>
      <!-- 第二行：时间筛选 + 重置 + 导出 -->
      <div class="toolbar toolbar-row toolbar-row-2">
        <input v-model="orderStartTime" type="date" style="width: 150px; height: 32px; padding: 0 8px; border: 1px solid #dbe3ed; border-radius: 4px;" title="派单时间起" @change="searchOrders" />
        <input v-model="orderEndTime" type="date" style="width: 150px; height: 32px; padding: 0 8px; border: 1px solid #dbe3ed; border-radius: 4px;" title="派单时间止" @change="searchOrders" />
        <button @click="resetOrderFilter">重置</button>
        <button :disabled="orderExporting" @click="exportOrders">{{ orderExporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>工单号</span><span>事件类型</span><span>级别</span><span>处理人</span><span>派单时间</span><span>状态</span><span>操作</span></div>
        <div v-if="ordersLoading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!orders.length" class="table-row"><span>暂无工单</span></div>
        <div v-for="item in orders" :key="item.work_order_id" class="table-row">
          <span><b>{{ item.work_order_no }}</b><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span></span>
          <span>{{ item.type_name }}<br /><small>{{ item.description }}</small></span>
          <span :class="levelClass(item.level_name)">● {{ item.level_name }}</span>
          <span>{{ item.assignee_name }}</span>
          <span>{{ item.assigned_at }}</span>
          <span>{{ item.status_name }}</span>
          <span><button class="link" @click="router.push('/workorder/detail/' + item.work_order_id)">查看详情</button></span>
        </div>
      </div>
      <div class="pager">
        <span>共 {{ orderTotal }} 条</span>
        <button :disabled="orderPage <= 1" @click="orderPage--; loadOrders()">上一页</button>
        <span>第 {{ orderPage }} 页 / 共 {{ Math.max(1, Math.ceil(orderTotal / orderSize)) }} 页</span>
        <button :disabled="orderPage * orderSize >= orderTotal" @click="orderPage++; loadOrders()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="orderJump" type="number" min="1" :max="Math.max(1, Math.ceil(orderTotal / orderSize))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToOrderPage" />
        <span>页</span>
        <button @click="goToOrderPage" :disabled="!orderJump">GO</button>
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

    <TrackDetailModal v-if="detailChainId" :chain-id="detailChainId" @close="detailChainId = null" />
  </div>
</template>

<style scoped>
</style>
