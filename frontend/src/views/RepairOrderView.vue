<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useSettingsStore } from "../stores/settings";
const settings = useSettingsStore();
import { api, type RepairCandidateItem, type RepairOrderItem } from "../api";
import RepairOrderDetailModal from "../components/RepairOrderDetailModal.vue";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();

const errorText = ref("");
const notice = ref("");

const statusOptions = [
  { value: "PENDING", label: "待处理" },
  { value: "REPAIRING", label: "维修中" },
  { value: "COMPLETED", label: "已完成" },
];

const filters = reactive({
  keyword: "",
  status: "",
  fault_id: "",
  assigned_to: "",
  start_time: "",
  end_time: "",
});
const assigneeInput = ref("");

const page = ref(1);
const size = 10;
const total = ref(0);
const jumpPage = ref<number | null>(null);
const orders = ref<RepairOrderItem[]>([]);
const loading = ref(false);
const submitting = ref(false);

const showDetail = ref(false);
const currentOrderId = ref<number | null>(null);

function statusLabel(value: string): string {
  return statusOptions.find((item) => item.value === value)?.label || value;
}

function statusClass(value: string): string {
  return value === "COMPLETED" ? "success" : value === "REPAIRING" ? "warn" : "";
}

function canOperate(item: RepairOrderItem): boolean {
  return auth.hasPermission("device:repair") && (item.assigned_to === auth.accountId || auth.typeId === 1);
}

function truncate(value: string | null, len = 12): string {
  if (!value) return "—";
  return value.length > len ? value.slice(0, len) + "…" : value;
}

async function loadOrders() {
  loading.value = true;
  try {
    const result = await api.repairOrders({
      status: filters.status || undefined,
      keyword: filters.keyword || undefined,
      fault_id: filters.fault_id ? Number(filters.fault_id) : undefined,
      assigned_to: filters.assigned_to ? Number(filters.assigned_to) : undefined,
      assigned_name: !filters.assigned_to && assigneeInput.value.trim() ? assigneeInput.value.trim() : undefined,
      start_time: filters.start_time || undefined,
      end_time: filters.end_time || undefined,
      page: page.value,
      size,
    });
    orders.value = result.list;
    total.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  loadOrders();
}

function goToPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / size));
  let p = Number(jumpPage.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === page.value) return;
  page.value = p;
  jumpPage.value = null;
  loadOrders();
}

function resetFilters() {
  Object.assign(filters, { keyword: "", status: "", fault_id: "", assigned_to: "", start_time: "", end_time: "" });
  assigneeInput.value = "";
  search();
}

function openDetail(item: RepairOrderItem) {
  currentOrderId.value = item.id;
  showDetail.value = true;
}

async function acceptOrder(item: RepairOrderItem) {
  submitting.value = true;
  try {
    await api.acceptRepairOrder(item.id);
    notice.value = `工单 ${item.order_no} 已接单，进入维修中`;
    await loadOrders();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

function onDetailChanged(message: string) {
  notice.value = message;
  loadOrders();
}

function goDevice() {
  router.push("/device/list");
}

function goFault() {
  router.push({ path: "/device/list", query: { tab: "faults" } });
}

onMounted(() => {
  loadOrders();
});
watch(() => settings.filterLabData, () => loadOrders());
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>设备维修工单</h2><p>故障触发自动派单 · 接单维修 · 完成归档恢复设备</p></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <div class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="filters.keyword" placeholder="设备编号 / 名称 / 安装位置 / 工单号" @keyup.enter="search" /></div>
        <select v-model="filters.status" @change="search">
          <option value="">全部状态</option>
          <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <input v-model="filters.fault_id" class="filter-input" type="number" min="1" placeholder="故障记录ID" @keyup.enter="search" />
        <input v-model="assigneeInput" type="text" placeholder="输入姓名搜索维修负责人" @keyup.enter="search" style="width: 200px; height: 40px; padding: 0 10px; border: 1px solid #dbe3ed; border-radius: 5px; outline: 0;" />
        <input v-model="filters.start_time" class="filter-input" type="date" title="创建时间起" @change="search" />
        <input v-model="filters.end_time" class="filter-input" type="date" title="创建时间止" @change="search" />
        <button class="primary" @click="search">查询</button>
        <button @click="resetFilters">重置</button>
      </div>
      <div class="table full repair-table">
        <div class="table-head"><span>工单编号</span><span>关联设备</span><span>故障类型</span><span>状态</span><span>维修负责人</span><span>创建时间</span><span>计划处理</span><span>损坏原因</span><span>维修情况</span><span>操作</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!orders.length" class="table-row"><span>暂无符合条件的维修工单</span></div>
        <div v-for="item in orders" :key="item.id" class="table-row">
          <span><b>{{ item.order_no }}</b><br /><a class="link" @click="goFault"><small>故障 #{{ item.fault_id }}</small></a></span>
          <span><a class="link" @click="goDevice"><b>{{ item.device_name || "—" }}</b></a><br /><small>{{ item.device_code }}</small></span>
          <span>{{ item.fault_type }}<br /><small>{{ item.fault_level }}</small></span>
          <span :class="statusClass(item.status)">● {{ statusLabel(item.status) }}</span>
          <span>{{ item.assigned_name || "待派发" }}</span>
          <span><small>{{ item.create_time || "—" }}</small></span>
          <span><small>{{ item.plan_finish_time || "—" }}</small></span>
          <span :title="item.damage_cause || ''"><small>{{ truncate(item.damage_cause) }}</small></span>
          <span :title="item.repair_detail || ''"><small>{{ truncate(item.repair_detail) }}</small></span>
          <span>
            <button class="btn-sm" @click="openDetail(item)">详情</button>
            <button v-if="item.status === 'PENDING' && canOperate(item)" class="btn-sm btn-confirm" :disabled="submitting" @click="acceptOrder(item)">接单</button>
          </span>
        </div>
      </div>
      <div class="pager">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadOrders()">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ Math.max(1, Math.ceil(total / size)) }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadOrders()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="jumpPage" type="number" min="1" :max="Math.max(1, Math.ceil(total / size))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToPage" />
        <span>页</span>
        <button @click="goToPage" :disabled="!jumpPage">GO</button>
      </div>
    </div>

    <RepairOrderDetailModal v-model:visible="showDetail" :order-id="currentOrderId" @changed="onDetailChanged" />
  </div>
</template>

<style scoped>
.repair-table .table-head,
.repair-table .table-row {
  grid-template-columns: 1.2fr 1.2fr 0.9fr 0.8fr 0.9fr 1.1fr 1.1fr 1fr 1fr 0.9fr;
}
.filter-input {
  width: 150px;
  height: 40px;
  padding: 0 12px;
  border: 1px solid #dbe3ed;
  border-radius: 5px;
  outline: 0;
  color: #35465e;
}
.link {
  color: #3788e8;
  cursor: pointer;
}
</style>
