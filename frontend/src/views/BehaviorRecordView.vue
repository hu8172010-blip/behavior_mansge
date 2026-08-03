<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, type BehaviorItem, type MetaEnums } from "../api";
import TrackDetailModal from "../components/TrackDetailModal.vue";
import PersonDetailModal from "../components/PersonDetailModal.vue";

const enums = ref<MetaEnums | null>(null);
const errorText = ref("");

const typeId = ref<number | undefined>(undefined);
const severityId = ref<number | undefined>(undefined);
const statusId = ref<number | undefined>(undefined);
const keyword = ref("");
const page = ref(1);
const size = 10;
const total = ref(0);
const items = ref<BehaviorItem[]>([]);
const loading = ref(false);
const exporting = ref(false);

const detailChainId = ref<number | null>(null);
const detailPersonId = ref<number | null>(null);

async function loadData() {
  loading.value = true;
  try {
    const result = await api.behaviors({ type_id: typeId.value, severity_id: severityId.value, status_id: statusId.value, keyword: keyword.value || undefined, page: page.value, size });
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

async function exportData() {
  exporting.value = true;
  try {
    await api.exportBehaviors({ type_id: typeId.value, severity_id: severityId.value, status_id: statusId.value, keyword: keyword.value || undefined });
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
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="keyword" placeholder="搜索事件类型或描述关键字" @keyup.enter="search" /></div>
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
        <button class="primary" @click="search">查询</button>
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
        <span>第 {{ page }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadData()">下一页</button>
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
</style>
