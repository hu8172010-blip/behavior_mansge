<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api, type AccountItem, type AlertItem, type MetaEnums, type WorkOrderItem } from "../api";
import { useAuthStore } from "../stores/auth";
import { useSettingsStore } from "../stores/settings";
import TrackDetailModal from "../components/TrackDetailModal.vue";
import { formatBehaviorDesc } from "../utils/behaviorDisplay";

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

const showReview = ref(false);
const currentReview = ref<AlertItem | null>(null);
const reviewFalsePositive = ref(false);
const reviewPersonIdentity = ref<"registered" | "stranger">("stranger");
const reviewNote = ref("");
const reviewPersonId = ref<number | null>(null);
const reviewPersonName = ref<string>("");
const personSearchKeyword = ref("");
const personOptions = ref<AccountItem[]>([]);
const personSearching = ref(false);
const personLoadingMore = ref(false);
const personSearchError = ref("");
const personDropdownOpen = ref(false);
const personPage = ref(1);
const personTotal = ref(0);
const personPageSize = 20;
let personSearchTimer: number | null = null;
let personSearchRequestId = 0;
const personLoadFailCount = ref(0);
const personSelectRef = ref<HTMLElement | null>(null);
const reviewFormError = ref("");

const personHasMore = computed(() => personOptions.value.length < personTotal.value);

// 切换人员身份时清空已选数据库人员，避免脏数据
watch(reviewPersonIdentity, (v) => {
  if (v !== "registered") {
    reviewPersonId.value = null;
    reviewPersonName.value = "";
    personSearchKeyword.value = "";
    personOptions.value = [];
    personSearchError.value = "";
    personDropdownOpen.value = false;
    personPage.value = 1;
    personTotal.value = 0;
  }
  reviewFormError.value = "";
});

function friendlySearchError(e: any): string {
  const status = e?.status ?? e?.response?.status;
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return "网络已断开，请检查网络后重试";
  }
  if (status === 0 || status === undefined) {
    return "网络连接异常，请稍后重试";
  }
  if (status === 500) {
    return "服务器繁忙，请稍后重试";
  }
  if (status === 503) {
    return "服务暂时不可用，请稍后重试";
  }
  if (status === 403) {
    return "没有权限加载账号列表";
  }
  if (status === 400) {
    return "搜索参数错误，请调整关键词";
  }
  return e?.message || "账号加载失败，请重试";
}

// 加载人员列表（支持分页，reset=true 时回到第1页并替换列表）
async function loadPersons(reset = false) {
  if (reset) {
    personPage.value = 1;
    personOptions.value = [];
    personLoadFailCount.value = 0;
  }
  if (personLoadingMore.value) return;
  personLoadingMore.value = true;
  if (reset) personSearching.value = true;
  personSearchError.value = "";
  const requestId = ++personSearchRequestId;
  try {
    const kw = personSearchKeyword.value.trim() || undefined;
    const result = await api.accounts({ keyword: kw, page: personPage.value, size: personPageSize });
    if (requestId !== personSearchRequestId) return;
    if (personDropdownOpen.value === false && !reset) return;
    if (reset) {
      personOptions.value = result.list;
    } else {
      const existIds = new Set(personOptions.value.map((p) => p.account_id));
      personOptions.value = [...personOptions.value, ...result.list.filter((p) => !existIds.has(p.account_id))];
    }
    personTotal.value = result.total;
    personLoadFailCount.value = 0;
  } catch (e: any) {
    if (requestId !== personSearchRequestId) return;
    personSearchError.value = friendlySearchError(e);
    personLoadFailCount.value += 1;
    if (!reset && personPage.value > 1) {
      personPage.value -= 1;
    }
  } finally {
    personSearching.value = false;
    personLoadingMore.value = false;
  }
}

function retryLoadPersons() {
  personLoadFailCount.value = 0;
  loadPersons(true);
}

function onPersonSearchInput() {
  if (personSearchTimer) window.clearTimeout(personSearchTimer);
  personSearchTimer = window.setTimeout(() => {
    loadPersons(true);
  }, 300);
}

function togglePersonDropdown() {
  if (personDropdownOpen.value) {
    personDropdownOpen.value = false;
    personSearchKeyword.value = "";
    personSearchError.value = "";
    if (personSearchTimer) window.clearTimeout(personSearchTimer);
  } else {
    personDropdownOpen.value = true;
    personSearchKeyword.value = "";
    personSearchError.value = "";
    if (personOptions.value.length === 0 && !personSearching.value) {
      loadPersons(true);
    }
  }
}

function onPersonListScroll(e: Event) {
  if (personLoadFailCount.value >= 2) return;
  const target = e.target as HTMLElement;
  if (personHasMore.value && !personLoadingMore.value && target.scrollTop + target.clientHeight >= target.scrollHeight - 20) {
    personPage.value += 1;
    loadPersons(false);
  }
}

function selectPerson(p: AccountItem) {
  reviewPersonId.value = p.account_id;
  reviewPersonName.value = p.real_name || p.login_name || `账号#${p.account_id}`;
  personSearchKeyword.value = "";
  personOptions.value = [];
  personSearchError.value = "";
  personDropdownOpen.value = false;
  if (personSearchTimer) window.clearTimeout(personSearchTimer);
  reviewFormError.value = "";
}

function clearSelectedPerson() {
  reviewPersonId.value = null;
  reviewPersonName.value = "";
  personSearchKeyword.value = "";
  personOptions.value = [];
  personSearchError.value = "";
  reviewFormError.value = "";
}

function personDisplayText(p: AccountItem): string {
  const name = p.real_name || p.login_name || `账号#${p.account_id}`;
  const dept = p.dept ? ` / ${p.dept}` : "";
  return `${name}（ID:${p.account_id}${dept}）`;
}

function openReview(item: AlertItem) {
  currentReview.value = item;
  reviewFalsePositive.value = false;
  reviewPersonIdentity.value = "stranger";
  reviewNote.value = "";
  reviewPersonId.value = null;
  reviewPersonName.value = "";
  personSearchKeyword.value = "";
  personOptions.value = [];
  personSearching.value = false;
  personLoadingMore.value = false;
  personSearchError.value = "";
  personDropdownOpen.value = false;
  personPage.value = 1;
  personTotal.value = 0;
  reviewFormError.value = "";
  showReview.value = true;
}

function extractVideoJobId(url: string | null): string | null {
  if (!url) return null;
  const match = url.match(/\/api\/jobs\/([^/]+)\/video$/);
  return match ? match[1] : null;
}

const showVideoPlayer = ref(false);
const videoPlayerAlert = ref<AlertItem | null>(null);
const videoPlayerList = ref<{ name: string; src: string; jobId: string }[]>([]);
const videoPlayerLoading = ref(false);
const videoPlayerError = ref("");
let videoLoadTimer: number | null = null;

function formatLocalDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return String(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const videoPlayerTitle = computed(() => {
  const alert = videoPlayerAlert.value;
  if (!alert) return "视频回放";
  return `视频回放 - ${alert.device_name || "摄像头"}（${formatLocalDateTime(alert.alert_time)}）`;
});

function getVideoJobIds(item: AlertItem): string[] {
  const ids: string[] = [];
  if (item.video_job_id) ids.push(item.video_job_id);
  if (item.is_dual_video && item.video_job_id_b) ids.push(item.video_job_id_b);
  if (ids.length) return ids;
  return ([item.video_path, item.video_path_b].filter(Boolean) as string[])
    .map(extractVideoJobId)
    .filter(Boolean) as string[];
}

function onVideoError() {
  videoPlayerError.value = "视频加载失败，请稍后重试";
  if (videoLoadTimer) {
    window.clearTimeout(videoLoadTimer);
    videoLoadTimer = null;
  }
}

function onVideoLoaded() {
  if (videoLoadTimer) {
    window.clearTimeout(videoLoadTimer);
    videoLoadTimer = null;
  }
}

async function openVideoPlayer(item: AlertItem | null) {
  if (!item) return;
  showVideoPlayer.value = true;
  videoPlayerAlert.value = item;
  videoPlayerLoading.value = true;
  videoPlayerError.value = "";
  videoPlayerList.value = [];
  if (videoLoadTimer) {
    window.clearTimeout(videoLoadTimer);
    videoLoadTimer = null;
  }

  const jobIds = getVideoJobIds(item);
  if (!jobIds.length) {
    videoPlayerLoading.value = false;
    videoPlayerError.value = "未关联原始视频";
    return;
  }

  const list: { name: string; src: string; jobId: string }[] = [];
  for (let i = 0; i < jobIds.length; i++) {
    const jobId = jobIds[i];
    try {
      const res = await api.verifyVideo(jobId);
      if (res.exists && res.video_url) {
        list.push({ name: `摄像头 ${String.fromCharCode(65 + i)}`, src: res.video_url, jobId });
      } else {
        videoPlayerLoading.value = false;
        videoPlayerError.value = res.message || "视频资源已过期清理，无法回放查看";
        return;
      }
    } catch (e: any) {
      videoPlayerLoading.value = false;
      videoPlayerError.value = e?.message || "模型推理服务离线，暂时无法查看视频";
      return;
    }
  }

  videoPlayerList.value = list;
  videoPlayerLoading.value = false;
  videoLoadTimer = window.setTimeout(() => {
    if (videoPlayerList.value.length && !videoPlayerError.value) {
      videoPlayerError.value = "视频加载失败，请稍后重试";
    }
  }, 30000);
}

function closeVideoPlayer() {
  showVideoPlayer.value = false;
  videoPlayerAlert.value = null;
  videoPlayerList.value = [];
  videoPlayerError.value = "";
  videoPlayerLoading.value = false;
  if (videoLoadTimer) {
    window.clearTimeout(videoLoadTimer);
    videoLoadTimer = null;
  }
}

async function submitReview() {
  if (!currentReview.value) return;
  reviewFormError.value = "";
  if (reviewPersonIdentity.value === "registered" && !reviewPersonId.value) {
    reviewFormError.value = "请选择具体的系统账号";
    return;
  }
  submitting.value = true;
  try {
    await api.reviewAlert(currentReview.value.alert_id, {
      false_positive: reviewFalsePositive.value,
      person_identity: reviewPersonIdentity.value,
      person_id: reviewPersonIdentity.value === "registered" ? reviewPersonId.value : null,
      person_name: reviewPersonIdentity.value === "registered" ? reviewPersonName.value || undefined : undefined,
      note: reviewNote.value || undefined,
    });
    showReview.value = false;
    currentReview.value.alert_status_id = 6;
    currentReview.value.status_name = "已复核归档";
    notice.value = `告警 #${currentReview.value.alert_id} 已复核归档`;
    await auth.refreshPendingCount();
  } catch (error: any) {
    errorText.value = error.message;
    if (reviewPersonIdentity.value === "registered" && /删除|不存在|账号/.test(error.message || "")) {
      reviewPersonId.value = null;
      reviewPersonName.value = "";
      personOptions.value = [];
      personDropdownOpen.value = false;
    }
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

function onDocumentClick(e: MouseEvent) {
  if (!personDropdownOpen.value) return;
  const el = personSelectRef.value;
  if (el && !el.contains(e.target as Node)) {
    personDropdownOpen.value = false;
  }
}

onMounted(async () => {
  document.addEventListener("click", onDocumentClick);
  try {
    enums.value = await api.enums();
  } catch {
    enums.value = null;
  }
  await Promise.all([loadAlerts(), loadOrders()]);
});

onUnmounted(() => {
  document.removeEventListener("click", onDocumentClick);
  if (personSearchTimer) window.clearTimeout(personSearchTimer);
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
          <span><b>{{ item.type_name }}</b><em v-if="item.is_marked_focus" class="orange">　◆重点关注</em><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span><br /><small>{{ formatBehaviorDesc(item.description, item.type_name) || "—" }}</small></span>
          <span :class="levelClass(item.level_name)">● {{ item.level_name }}</span>
          <span>{{ item.region_name || "—" }}<br /><small>{{ item.device_name }}</small></span>
          <span>{{ item.status_name }}<br /><small v-if="item.track_id"><button class="link" @click="detailChainId = item.track_id">查看轨迹</button></small></span>
          <span class="row-actions">
            <button v-if="item.alert_status_id === 1" class="btn-sm" :disabled="submitting || (!item.video_path && !item.video_path_b)" @click="openVideoPlayer(item)">查看视频</button>
            <button v-if="item.alert_status_id === 1" class="btn-sm btn-confirm" :disabled="submitting" @click="openReview(item)">人工复核</button>
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
          <span>{{ item.type_name }}<br /><small>{{ formatBehaviorDesc(item.description, item.type_name) || "—" }}</small></span>
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
        <div v-if="reviewPersonIdentity === 'registered'" class="form-row" style="display: block; margin-top: 12px; position: relative">
          <label>选择登记人员<span style="color: #f56c6c"> *</span></label>
          <div class="person-select" ref="personSelectRef">
            <div class="person-select-trigger" @click="togglePersonDropdown">
              <span v-if="reviewPersonId" class="person-select-value">
                {{ reviewPersonName }}（ID:{{ reviewPersonId }}）
                <span class="person-select-clear" @click.stop="clearSelectedPerson">×</span>
              </span>
              <span v-else class="person-select-placeholder">请选择系统账号</span>
              <span class="person-select-arrow" :class="{ open: personDropdownOpen }">▾</span>
            </div>
            <div v-if="personDropdownOpen" class="person-select-panel">
              <div class="person-select-search">
                <input
                  v-model="personSearchKeyword"
                  placeholder="输入姓名/账号/部门搜索"
                  @input="onPersonSearchInput"
                />
              </div>
              <div class="person-select-list" @scroll="onPersonListScroll">
                <div v-if="personSearching && personOptions.length === 0" class="person-select-empty">搜索中...</div>
                <div v-else-if="personSearchError" class="person-select-empty person-select-error" @click="retryLoadPersons" style="cursor: pointer; text-decoration: underline;">
                  {{ personSearchError }}，点击重试
                </div>
                <div v-else-if="!personOptions.length" class="person-select-empty">无匹配账号</div>
                <div
                  v-for="p in personOptions"
                  :key="p.account_id"
                  class="person-select-option"
                  :class="{ active: p.account_id === reviewPersonId }"
                  @mousedown.prevent="selectPerson(p)"
                >
                  {{ personDisplayText(p) }}
                </div>
                <div v-if="personLoadingMore" class="person-select-empty">加载更多...</div>
                <div v-if="!personHasMore && personOptions.length > 0" class="person-select-empty person-select-end">已加载全部 {{ personTotal }} 条</div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="reviewFormError" class="error" style="margin-top: 8px" @click="reviewFormError = ''">{{ reviewFormError }}</div>
        <div class="form-row" style="display: block; margin-top: 12px">
          <label>复核备注（可选）</label>
          <input v-model="reviewNote" placeholder="例如：已确认，非误报" style="width: 100%; margin-top: 6px" />
        </div>
        <div class="toolbar" style="margin-top: 16px">
          <button class="primary" :disabled="submitting || (reviewPersonIdentity === 'registered' && !reviewPersonId)" @click="submitReview">确认归档</button>
          <button :disabled="submitting || (currentReview && !currentReview.video_path && !currentReview.video_path_b)" @click="openVideoPlayer(currentReview)">查看视频</button>
        </div>
      </div>
    </div>

    <TrackDetailModal v-if="detailChainId" :chain-id="detailChainId" @close="detailChainId = null" />

    <div v-if="showVideoPlayer" class="video-modal-mask" @click.self="closeVideoPlayer">
      <div class="video-modal" @click.stop>
        <div class="video-modal-header">
          <h2>{{ videoPlayerTitle }}</h2>
          <button class="close" @click="closeVideoPlayer">×</button>
        </div>
        <div class="video-modal-body">
          <div v-if="videoPlayerLoading" class="video-status">正在校验视频资源...</div>
          <div v-else-if="videoPlayerError" class="video-status video-error">{{ videoPlayerError }}</div>
          <div v-else class="video-players" :class="{ 'video-players-dual': videoPlayerList.length > 1 }">
            <div v-for="(v, i) in videoPlayerList" :key="v.jobId" class="video-player">
              <div class="video-player-label">{{ v.name }}</div>
              <video
                :src="v.src"
                controls
                preload="metadata"
                style="width: 100%; max-height: 420px; background: #000; border-radius: 4px"
                @error="onVideoError"
                @loadeddata="onVideoLoaded"
              ></video>
            </div>
          </div>
        </div>
        <div v-if="videoPlayerAlert && !videoPlayerLoading && !videoPlayerError" class="video-modal-footer">
          <div><b>事件类型：</b>{{ videoPlayerAlert.type_name }}（{{ videoPlayerAlert.level_name }}）</div>
          <div><b>置信度：</b>{{ videoPlayerAlert.confidence_score != null ? (videoPlayerAlert.confidence_score * 100).toFixed(1) + '%' : '—' }}</div>
          <div v-if="videoPlayerAlert.description" style="margin-top: 8px; color: #666; font-size: 13px">
            <b>描述：</b>{{ formatBehaviorDesc(videoPlayerAlert.description, videoPlayerAlert.type_name || '') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.video-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-modal {
  background: #fff;
  border-radius: 8px;
  width: min(960px, 92vw);
  max-height: 92vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
}

.video-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
}

.video-modal-header h2 {
  margin: 0;
  font-size: 16px;
}

.video-modal-body {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
  min-height: 200px;
}

.video-status {
  text-align: center;
  padding: 80px 16px;
  color: #666;
  font-size: 15px;
}

.video-error {
  color: #f56c6c;
}

.video-players {
  display: flex;
  gap: 16px;
  flex-direction: column;
}

.video-players-dual {
  flex-direction: row;
}

.video-player {
  flex: 1;
  min-width: 0;
}

.video-player-label {
  margin-bottom: 8px;
  font-weight: 600;
  color: #333;
}

.video-modal-footer {
  padding: 12px 16px;
  border-top: 1px solid #e4e7ed;
  background: #f5f7fa;
}

.close {
  background: none;
  border: none;
  font-size: 22px;
  color: #999;
  cursor: pointer;
}

.close:hover {
  color: #333;
}

.person-select {
  position: relative;
  width: 100%;
  margin-top: 6px;
}

.person-select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 36px;
  padding: 0 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
}

.person-select-trigger:hover {
  border-color: #c0c4cc;
}

.person-select-value {
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.person-select-clear {
  color: #c0c4cc;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.person-select-clear:hover {
  color: #f56c6c;
}

.person-select-placeholder {
  color: #c0c4cc;
}

.person-select-arrow {
  color: #c0c4cc;
  transition: transform 0.2s;
}

.person-select-arrow.open {
  transform: rotate(180deg);
}

.person-select-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 20;
  display: flex;
  flex-direction: column;
}

.person-select-search {
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.person-select-search input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
  box-sizing: border-box;
}

.person-select-search input:focus {
  outline: none;
  border-color: #409eff;
}

.person-select-list {
  max-height: 240px;
  overflow-y: auto;
}

.person-select-option {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #303133;
}

.person-select-option:hover {
  background: #f5f7fa;
}

.person-select-option.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}

.person-select-empty {
  padding: 16px;
  text-align: center;
  font-size: 13px;
  color: #999;
}

.person-select-error {
  color: #f56c6c;
}

.person-select-end {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
