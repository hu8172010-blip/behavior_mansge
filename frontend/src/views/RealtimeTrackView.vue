<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { api, type TrackChainItem } from "../api";
import TrackDetailModal from "../components/TrackDetailModal.vue";

const tracks = ref<TrackChainItem[]>([]);
const loading = ref(false);
const errorText = ref("");
const keyword = ref("");
const detailChainId = ref<number | null>(null);
const lastRefreshAt = ref("");
let timer: number | undefined;

async function loadTracks() {
  loading.value = true;
  try {
    const result = await api.tracks({ chain_status: 1, keyword: keyword.value || undefined, page: 1, size: 50 });
    tracks.value = result.list;
    lastRefreshAt.value = new Date().toLocaleTimeString("zh-CN");
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function elapsedLabel(startTime: string | null): string {
  if (!startTime) return "—";
  const sec = Math.max(0, Math.floor((Date.now() - new Date(startTime.replace(" ", "T")).getTime()) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}分${s}秒` : `${s}秒`;
}

onMounted(() => {
  loadTracks();
  timer = window.setInterval(loadTracks, 30000);
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>实时轨迹监测</h2><p>当前行进中的跨摄像头轨迹链路，每 30 秒自动刷新</p></div>
      <div class="tabs"><button class="selected">行进中 {{ tracks.length }}</button><button @click="loadTracks">手动刷新</button></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>

    <div class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="keyword" placeholder="搜索链路编号或人员特征" @keyup.enter="loadTracks" /></div>
        <button class="primary" @click="loadTracks">查询</button>
        <span style="color:#93a0b2;font-size:12px">上次刷新 {{ lastRefreshAt }}</span>
      </div>
      <div class="table full">
        <div class="table-head"><span>链路编号</span><span>人员特征</span><span>置信度</span><span>路径（首 → 末）</span><span>跳数</span><span>已持续</span><span>操作</span></div>
        <div v-if="loading && !tracks.length" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!tracks.length" class="table-row"><span>当前没有行进中的轨迹</span></div>
        <div v-for="item in tracks" :key="item.chain_id" class="table-row">
          <span><b>{{ item.chain_unique_id }}</b></span>
          <span>{{ item.appearance_desc || "未知人员" }}<em v-if="item.is_focused" class="orange">　◆重点关注</em></span>
          <span>{{ item.confidence != null ? (item.confidence * 100).toFixed(1) + "%" : "—" }}</span>
          <span>{{ item.first_device_name || "—" }} → {{ item.last_device_name || "—" }}<br /><small class="warn">● 行进中</small></span>
          <span>{{ item.hop_count }}</span>
          <span>{{ elapsedLabel(item.chain_start_time) }}</span>
          <span><button class="btn-sm btn-assign" @click="detailChainId = item.chain_id">链路详情</button></span>
        </div>
      </div>
    </div>

    <TrackDetailModal v-if="detailChainId" :chain-id="detailChainId" @close="detailChainId = null" />
  </div>
</template>
