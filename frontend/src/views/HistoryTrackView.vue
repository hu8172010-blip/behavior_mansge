<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, type TrackChainItem } from "../api";
import TrackDetailModal from "../components/TrackDetailModal.vue";
import PersonDetailModal from "../components/PersonDetailModal.vue";

const chainStatus = ref<number | undefined>(undefined);
const keyword = ref("");
const startTime = ref("");
const endTime = ref("");
const page = ref(1);
const size = 10;
const total = ref(0);
const tracks = ref<TrackChainItem[]>([]);
const loading = ref(false);
const errorText = ref("");
const detailChainId = ref<number | null>(null);
const detailPersonId = ref<number | null>(null);
const exporting = ref(false);
const jumpPage = ref<number | null>(null);

async function loadTracks() {
  loading.value = true;
  try {
    const result = await api.tracks({
      chain_status: chainStatus.value,
      keyword: keyword.value || undefined,
      start_time: startTime.value ? startTime.value.replace("T", " ") : undefined,
      end_time: endTime.value ? endTime.value.replace("T", " ") : undefined,
      page: page.value,
      size,
    });
    tracks.value = result.list;
    total.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  loadTracks();
}

function goToPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / size));
  let p = Number(jumpPage.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === page.value) return;
  page.value = p;
  jumpPage.value = null;
  loadTracks();
}

async function exportData() {
  exporting.value = true;
  try {
    await api.exportTracks({
      chain_status: chainStatus.value,
      keyword: keyword.value || undefined,
      start_time: startTime.value ? startTime.value.replace("T", " ") : undefined,
      end_time: endTime.value ? endTime.value.replace("T", " ") : undefined,
    });
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

function formatDuration(sec: number): string {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}分${s}秒` : `${s}秒`;
}

onMounted(loadTracks);
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>事后轨迹查询</h2><p>按链路状态、时间范围与关键字检索历史轨迹链路</p></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>

    <div class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="keyword" placeholder="搜索链路编号或人员特征" @keyup.enter="search" /></div>
        <select v-model="chainStatus" @change="search">
          <option :value="undefined">全部状态</option>
          <option :value="1">行进中</option>
          <option :value="2">已归档</option>
        </select>
        <input v-model="startTime" type="datetime-local" style="max-width:190px" />
        <input v-model="endTime" type="datetime-local" style="max-width:190px" />
        <button class="primary" @click="search">查询</button>
        <button :disabled="exporting" @click="exportData">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>链路编号</span><span>人员特征</span><span>置信度</span><span>路径（首 → 末）</span><span>开始时间</span><span>时长</span><span>状态</span><span>操作</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!tracks.length" class="table-row"><span>暂无符合条件的轨迹链路</span></div>
        <div v-for="item in tracks" :key="item.chain_id" class="table-row">
          <span><b>{{ item.chain_unique_id }}</b><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span></span>
          <span>{{ item.appearance_desc || "未知人员" }}<em v-if="item.is_focused" class="orange">　◆重点关注</em><br />
            <small v-if="item.person_id"><button class="link" @click="detailPersonId = item.person_id">查看人员</button></small>
          </span>
          <span>{{ item.confidence != null ? (item.confidence * 100).toFixed(1) + "%" : "—" }}</span>
          <span>{{ item.first_device_name || "—" }} → {{ item.last_device_name || "—" }}<br /><small>{{ item.hop_count }} 跳</small></span>
          <span>{{ item.chain_start_time }}</span>
          <span>{{ formatDuration(item.total_duration_sec) }}</span>
          <span :class="item.chain_status === 1 ? 'warn' : 'success'">{{ item.chain_status === 1 ? "行进中" : "已归档" }}</span>
          <span><button class="btn-sm btn-assign" @click="detailChainId = item.chain_id">链路详情</button></span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadTracks()">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ Math.max(1, Math.ceil(total / size)) }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadTracks()">下一页</button>
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
</style>
