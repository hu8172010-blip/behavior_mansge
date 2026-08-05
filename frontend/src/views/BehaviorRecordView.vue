<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useSettingsStore } from "../stores/settings";
const settings = useSettingsStore();
import { api, type BehaviorItem, type MetaEnums } from "../api";
import TrackDetailModal from "../components/TrackDetailModal.vue";
import PersonDetailModal from "../components/PersonDetailModal.vue";

const route = useRoute();

const enums = ref<MetaEnums | null>(null);
const errorText = ref("");

const typeId = ref<number | undefined>(undefined);
const severityId = ref<number | undefined>(undefined);
const statusId = ref<number | undefined>(undefined);
const regionName = ref("");
const startTime = ref("");
const endTime = ref("");
const keyword = ref("");
const page = ref(1);
const size = 10;
const total = ref(0);
const items = ref<BehaviorItem[]>([]);
const loading = ref(false);
const exporting = ref(false);
const jumpPage = ref<number | null>(null);

const detailChainId = ref<number | null>(null);
const detailPersonId = ref<number | null>(null);

async function loadData() {
  loading.value = true;
  try {
    const result = await api.behaviors({
      type_id: typeId.value,
      severity_id: severityId.value,
      status_id: statusId.value,
      region_name: regionName.value || undefined,
      start_time: startTime.value || undefined,
      end_time: endTime.value || undefined,
      keyword: keyword.value || undefined,
      page: page.value,
      size,
    });
    items.value = result.list;
    total.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  loadData();
}

function goToPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / size));
  let p = Number(jumpPage.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === page.value) return;
  page.value = p;
  jumpPage.value = null;
  loadData();
}

function resetFilter() {
  typeId.value = undefined;
  severityId.value = undefined;
  statusId.value = undefined;
  regionName.value = "";
  startTime.value = "";
  endTime.value = "";
  keyword.value = "";
  page.value = 1;
  loadData();
}

// 顶部"过滤模拟数据"开关切换时自动刷新
watch(() => settings.filterLabData, () => loadData());

async function exportData() {
  exporting.value = true;
  try {
    await api.exportBehaviors({
      type_id: typeId.value,
      severity_id: severityId.value,
      status_id: statusId.value,
      region_name: regionName.value || undefined,
      start_time: startTime.value || undefined,
      end_time: endTime.value || undefined,
      keyword: keyword.value || undefined,
    });
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

function levelClass(level: string): string {
  return level === "高" ? "danger" : level === "中" ? "warn" : "success";
}

onMounted(async () => {
  // 支持从数据管理首页"分布图下钻"跳转：/data/abnormal-record?type_id=X 或 ?region=区域名
  const qType = Number(route.query.type_id);
  if (Number.isInteger(qType) && qType > 0) typeId.value = qType;
  const qRegion = typeof route.query.region === "string" ? route.query.region.trim() : "";
  if (qRegion) regionName.value = qRegion;
  try {
    enums.value = await api.enums();
  } catch {
    enums.value = null;
  }
  await loadData();
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>异常行为记录</h2><p>按行为类型、严重级别、预警状态和时间检索历史记录</p></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>

    <div class="panel data-panel">
      <!-- 第一行：核心搜索条件 + 查询 -->
      <div class="toolbar toolbar-row">
        <div class="search search-long"><span>⌕</span><input v-model="keyword" placeholder="搜索事件类型或描述关键字" @keyup.enter="search" /></div>
        <input v-model="regionName" placeholder="区域" style="width: 110px; height: 40px; padding: 0 10px; border: 1px solid #dbe3ed; border-radius: 5px;" @keyup.enter="search" />
        <input v-model="startTime" type="datetime-local" style="width: 180px; height: 40px; padding: 0 8px; border: 1px solid #dbe3ed; border-radius: 5px;" title="起始时间" />
        <input v-model="endTime" type="datetime-local" style="width: 180px; height: 40px; padding: 0 8px; border: 1px solid #dbe3ed; border-radius: 5px;" title="截止时间" />
        <button class="primary" style="height: 40px; line-height: 20px; padding: 0 18px; box-sizing: border-box; flex-shrink: 0; white-space: nowrap; min-width: 80px" @click="search">查询</button>
      </div>
      <!-- 第二行：分类筛选 + 重置 + 导出 -->
      <div class="toolbar toolbar-row toolbar-row-2">
        <select v-model="typeId" @change="search">
          <option :value="undefined">全部类型</option>
          <option v-for="item in enums?.behavior_types || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="severityId" @change="search">
          <option :value="undefined">全部级别</option>
          <option v-for="item in enums?.severity_levels || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="statusId" @change="search">
          <option :value="undefined">全部状态</option>
          <option v-for="item in enums?.alert_statuses || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <button @click="resetFilter" title="清空所有筛选条件">重置</button>
        <button :disabled="exporting" @click="exportData">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>检出时间</span><span>行为类型</span><span>级别</span><span>描述</span><span>位置 / 设备</span><span>状态</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!items.length" class="table-row"><span>暂无符合条件的记录</span></div>
        <div v-for="item in items" :key="item.behavior_id" class="table-row">
          <span>{{ item.detected_at }}</span>
          <span><b>{{ item.type_name }}</b><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span></span>
          <span :class="levelClass(item.level_name)">● {{ item.level_name }}</span>
          <span>{{ item.description || "—" }}<br /><small v-if="item.confidence_score">置信度 {{ item.confidence_score }}</small></span>
          <span>{{ item.region_name || "—" }}<br /><small>{{ item.device_name }}</small></span>
          <span>{{ item.status_name }}<br />
            <small v-if="item.track_id">
              <button class="link" @click="detailChainId = item.track_id">查看轨迹</button>
            </small>
            <small v-if="item.person_id">
              <button class="link" @click="detailPersonId = item.person_id">查看人员</button>
            </small>
          </span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadData()">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ Math.max(1, Math.ceil(total / size)) }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadData()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="jumpPage" type="number" min="1" :max="Math.max(1, Math.ceil(total / size))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToPage" />
        <span>页</span>
        <button @click="goToPage" :disabled="!jumpPage">GO</button>
      </div>
    </div>

    <TrackDetailModal v-if="detailChainId" :chain-id="detailChainId" @close="detailChainId = null" />
    <PersonDetailModal v-if="detailPersonId" :visible="!!detailPersonId" :person-id="detailPersonId" @update:visible="detailPersonId = null" />
  </div>
</template>

<style scoped>
.tag-lab {
  display: inline-block;
  padding: 1px 6px;
  font-size: 10px;
  color: #fff;
  background-color: #f08020;
  border-radius: 3px;
  margin-left: 6px;
}
.toolbar-row {
  align-items: center;
  margin-bottom: 10px;
}
.toolbar-row-2 {
  margin-bottom: 0;
}
.search-long {
  flex: 3;
  min-width: 260px;
}
</style>
