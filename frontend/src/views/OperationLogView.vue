<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { api, type LogItem } from "../api";
import { useSettingsStore } from "../stores/settings";
const settings = useSettingsStore();
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();

const moduleOptions = [
  { value: "ABNORMAL_BEHAVIOR", label: "异常行为" },
  { value: "DEVICE", label: "设备管理" },
  { value: "SYSTEM", label: "权限管理" },
  { value: "USER_PROFILE", label: "用户资料" },
  { value: "BACKUP_RESTORE", label: "备份恢复" },
];
const typeOptions = ["QUERY", "UPDATE", "EXPORT", "DELETE", "BACKUP", "RESTORE"];

const moduleCode = ref("");
const operationType = ref("");
const keyword = ref("");
const startTime = ref("");
const endTime = ref("");
const page = ref(1);
const size = 10;
const total = ref(0);
const logs = ref<LogItem[]>([]);
const loading = ref(false);
const exporting = ref(false);
const errorText = ref("");
const notice = ref("");
const jumpPage = ref<number | null>(null);

function moduleLabel(value: string): string {
  return moduleOptions.find((item) => item.value === value)?.label || value;
}

function currentParams() {
  return {
    module_code: moduleCode.value || undefined,
    operation_type: operationType.value || undefined,
    keyword: keyword.value || undefined,
    start_time: startTime.value ? startTime.value.replace("T", " ") : undefined,
    end_time: endTime.value ? endTime.value.replace("T", " ") : undefined,
  };
}

async function loadLogs() {
  loading.value = true;
  try {
    const result = await api.logs({ ...currentParams(), page: page.value, size });
    logs.value = result.list;
    total.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  loadLogs();
}

function goToPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / size));
  let p = Number(jumpPage.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === page.value) return;
  page.value = p;
  jumpPage.value = null;
  loadLogs();
}

async function exportCsv() {
  exporting.value = true;
  try {
    await api.exportLogs(currentParams());
    notice.value = "日志已导出为 CSV 文件";
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

onMounted(loadLogs);
watch(() => settings.filterLabData, () => loadLogs());

function resetLogFilter() {
  moduleCode.value = "";
  operationType.value = "";
  keyword.value = "";
  startTime.value = "";
  endTime.value = "";
  page.value = 1;
  loadLogs();
}
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>系统操作日志</h2><p>全模块操作审计，支持筛选与 CSV 导出（最多 5000 条）</p></div>
      <div class="tabs">
        <button v-if="auth.hasPermission('log:export')" :disabled="exporting" @click="exportCsv">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <div class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="keyword" placeholder="搜索操作人或操作详情" @keyup.enter="search" /></div>
        <select v-model="moduleCode" @change="search">
          <option value="">全部模块</option>
          <option v-for="item in moduleOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <select v-model="operationType" @change="search">
          <option value="">全部操作类型</option>
          <option v-for="item in typeOptions" :key="item" :value="item">{{ item }}</option>
        </select>
        <input v-model="startTime" type="datetime-local" style="max-width:190px" />
        <input v-model="endTime" type="datetime-local" style="max-width:190px" />
        <button class="primary" @click="search">查询</button>
        <button @click="resetLogFilter">重置</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>操作时间</span><span>模块</span><span>操作类型</span><span>操作人</span><span>对象</span><span>操作详情</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!logs.length" class="table-row"><span>暂无符合条件的日志</span></div>
        <div v-for="item in logs" :key="item.log_id" class="table-row">
          <span><small>{{ item.operated_at }}</small></span>
          <span>{{ moduleLabel(item.module_code) }}</span>
          <span>{{ item.operation_type }}</span>
          <span>{{ item.operator_name || "系统" }}<br /><small>{{ item.operator_role || "—" }}</small></span>
          <span>{{ item.target_type || "—" }} #{{ item.target_id ?? "—" }}</span>
          <span><small>{{ item.operation_content || "—" }}</small></span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadLogs()">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ Math.max(1, Math.ceil(total / size)) }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadLogs()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="jumpPage" type="number" min="1" :max="Math.max(1, Math.ceil(total / size))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToPage" />
        <span>页</span>
        <button @click="goToPage" :disabled="!jumpPage">GO</button>
      </div>
    </div>
  </div>
</template>
