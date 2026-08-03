<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api, type DashboardSummary } from "../api";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const summary = ref<DashboardSummary | null>(null);
const loading = ref(true);
const errorText = ref("");

const today = new Date();
const dateLabel = today.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" });

const maxTrend = computed(() => Math.max(1, ...(summary.value?.trend.map((item) => item.count) || [1])));

function barHeight(count: number): string {
  return `${Math.max(8, Math.round((count / maxTrend.value) * 90))}%`;
}

function healthCount(key: string): number {
  return summary.value?.device_health?.[key] ?? 0;
}

onMounted(async () => {
  try {
    summary.value = await api.dashboard();
  } catch (error: any) {
    errorText.value = error.message || "看板数据加载失败";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="dashboard">
    <div class="welcome">
      <div>
        <small>{{ dateLabel }}</small>
        <h2>你好，{{ auth.realName || "用户" }} <em>✦</em></h2>
        <p>今日园区运行状态概览，数据来自实时业务库。</p>
      </div>
      <button class="primary" @click="router.push('/track/history')">＋ 新建轨迹检索</button>
    </div>

    <div v-if="errorText" class="error">{{ errorText }}</div>
    <div v-else-if="loading" class="panel" style="padding: 40px; text-align: center">数据加载中...</div>

    <template v-else-if="summary">
      <div class="stats">
        <div class="clickable" @click="router.push('/data/abnormal-record')"><small>今日识别事件</small><strong>{{ summary.today_events }}</strong><em>累计 {{ summary.total_events }}</em></div>
        <div class="clickable" @click="router.push('/alarm/todo')"><small>待确认预警</small><strong>{{ summary.pending_alerts }}</strong><em class="orange">需要关注</em></div>
        <div class="clickable" @click="router.push('/track/realtime')"><small>活跃轨迹</small><strong>{{ summary.active_tracks }}</strong><em>实时同步</em></div>
        <div class="clickable" @click="router.push('/device/list')"><small>设备在线率</small><strong>{{ summary.device_online_rate }}%</strong><em class="green">共 {{ summary.device_total }} 台</em></div>
      </div>

      <div class="dashboard-grid">
        <article class="panel chart-panel">
          <div class="panel-title">
            <div><h3>事件趋势</h3><p>今日各小时异常行为检出量</p></div>
            <div class="tabs"><button class="selected">今日</button></div>
          </div>
          <div class="big-number">{{ summary.total_events }} <small>累计事件量</small></div>
          <div class="fake-chart">
            <i v-for="point in summary.trend" :key="point.hour" :style="{ height: barHeight(point.count) }" :title="`${point.hour}时：${point.count}起`"></i>
            <i v-if="!summary.trend.length" style="height: 8%"></i>
          </div>
          <div class="chart-labels">
            <span v-for="point in summary.trend" :key="'label-' + point.hour">{{ point.hour }}:00</span>
            <span v-if="!summary.trend.length">今日暂无事件</span>
          </div>
        </article>
        <article class="panel">
          <div class="panel-title">
            <div><h3>设备健康状态</h3><p>实时统计</p></div>
          </div>
          <div class="health"><strong>{{ summary.device_online_rate }}%</strong><small>设备在线</small></div>
          <div class="health-list">
            <span>● 在线运行 <b>{{ healthCount("ONLINE") }}</b></span>
            <span class="warn">● 故障/离线 <b>{{ healthCount("FAULT") + healthCount("OFFLINE") }}</b></span>
            <span class="danger">● 已停用 <b>{{ healthCount("DISABLED") }}</b></span>
          </div>
          <button class="link" @click="router.push('/device/list')">查看设备详情 →</button>
        </article>
      </div>

      <div class="dashboard-grid lower">
        <article class="panel">
          <div class="panel-title">
            <div><h3>实时预警 <mark>● LIVE</mark></h3><p>待确认预警最新 5 条</p></div>
            <button class="link" @click="router.push('/alarm/todo')">全部待办 →</button>
          </div>
          <div class="table full">
            <div class="table-head"><span>时间</span><span>事件类型</span><span>级别</span><span>位置</span></div>
            <div v-for="item in summary.latest_alerts" :key="item.alert_id" class="table-row" @click="router.push('/alarm/todo')">
              <span>{{ item.alert_time.slice(11) }}</span>
              <span><b>{{ item.type_name }}</b></span>
              <span :class="item.level_name === '高' ? 'danger' : item.level_name === '中' ? 'warn' : ''">{{ item.level_name }}</span>
              <span>{{ item.region_name || item.device_name || "—" }}</span>
            </div>
            <div v-if="!summary.latest_alerts.length" class="table-row"><span>当前无待确认预警</span></div>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.stats > div.clickable {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}
.stats > div.clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(35, 45, 69, 0.12);
}
</style>
