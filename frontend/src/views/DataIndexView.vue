<template>
  <div>
    <div class="page-heading">
      <div><h2>数据管理</h2><p>系统数据总量、类型分布、区域分布与近7天趋势概览（点击卡片或分布条可跳转明细）</p></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-else-if="loading" class="panel" style="padding: 40px; text-align: center">数据加载中...</div>

    <template v-else-if="data">
      <div class="stats">
        <div class="stat-card" @click="go('/data/abnormal-record')"><small>异常行为</small><strong>{{ data.total.behavior_count }}</strong><em>条记录</em></div>
        <div class="stat-card" @click="go('/data/track-record')"><small>轨迹链路</small><strong>{{ data.total.track_count }}</strong><em>条链路</em></div>
        <div class="stat-card" @click="go('/alarm/todo')"><small>预警事件</small><strong>{{ data.total.alert_count }}</strong><em>条预警</em></div>
        <div class="stat-card" @click="go('/alarm/todo')"><small>处置工单</small><strong>{{ data.total.work_order_count }}</strong><em>张工单</em></div>
        <div class="stat-card" @click="go('/data/user-profile')"><small>匿名人员</small><strong>{{ data.total.person_count }}</strong><em>人</em></div>
        <div class="stat-card" @click="go('/device/list')"><small>设备总数</small><strong>{{ data.total.device_count }}</strong><em>台设备</em></div>
      </div>

      <div class="dashboard-grid">
        <article class="panel">
          <div class="panel-title">
            <div><h3>行为类型分布</h3><p>按异常行为类型统计（点击可查看该类型明细）</p></div>
          </div>
          <div class="dist-list" v-if="data.type_distribution.length">
            <div v-for="item in data.type_distribution" :key="item.name" class="dist-item clickable" :title="`查看「${item.name}」记录`" @click="go('/data/abnormal-record', { type_id: item.id })">
              <span class="dist-name">{{ item.name }}</span>
              <div class="dist-bar-wrap">
                <div class="dist-bar" :style="{ width: barWidth(item.value, maxTypeValue) }"></div>
              </div>
              <span class="dist-value">{{ item.value }}</span>
            </div>
          </div>
          <p v-else class="empty-text">暂无数据</p>
        </article>

        <article class="panel">
          <div class="panel-title">
            <div><h3>区域分布</h3><p>按设备所属区域统计（点击可查看该区域记录）</p></div>
          </div>
          <div class="dist-list" v-if="data.region_distribution.length">
            <div v-for="item in data.region_distribution" :key="item.name" class="dist-item clickable" :title="`查看「${item.name}」区域记录`" @click="go('/data/abnormal-record', { region: item.name })">
              <span class="dist-name">{{ item.name }}</span>
              <div class="dist-bar-wrap">
                <div class="dist-bar" :style="{ width: barWidth(item.value, maxRegionValue) }"></div>
              </div>
              <span class="dist-value">{{ item.value }}</span>
            </div>
          </div>
          <p v-else class="empty-text">暂无数据</p>
        </article>
      </div>

      <div class="dashboard-grid lower">
        <article class="panel chart-panel">
          <div class="panel-title">
            <div><h3>近7天事件趋势</h3><p>每日异常行为检出量</p></div>
          </div>
          <div class="big-number">{{ totalWeekEvents }} <small>近7天累计</small></div>
          <div class="trend-chart">
            <div v-for="point in data.seven_day_trend" :key="point.date" class="trend-col">
              <div class="trend-bar" :style="{ height: barHeight(point.count) }" :title="`${point.date}：${point.count}起`"></div>
              <div class="trend-label">{{ point.date.slice(5) }}</div>
            </div>
            <div v-if="!data.seven_day_trend.length" class="trend-empty">暂无数据</div>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api, type DataIndexSummary } from "../api";

const router = useRouter();

function go(path: string, query?: Record<string, string | number>) {
  router.push(query ? { path, query } : { path });
}

const data = ref<DataIndexSummary | null>(null);
const loading = ref(true);
const errorText = ref("");

const maxTypeValue = computed(() => Math.max(1, ...(data.value?.type_distribution.map((i) => i.value) || [1])));
const maxRegionValue = computed(() => Math.max(1, ...(data.value?.region_distribution.map((i) => i.value) || [1])));
const totalWeekEvents = computed(() => data.value?.seven_day_trend.reduce((sum, item) => sum + item.count, 0) || 0);

function barWidth(value: number, max: number): string {
  return `${Math.max(4, Math.round((value / max) * 100))}%`;
}

function barHeight(count: number): string {
  const max = Math.max(1, ...(data.value?.seven_day_trend.map((i) => i.count) || [1]));
  return `${Math.max(8, Math.round((count / max) * 75))}%`;
}

onMounted(async () => {
  try {
    data.value = await api.dataIndex();
  } catch (error: any) {
    errorText.value = error.message || "数据加载失败";
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
/* 两个分布面板等宽（全局 .dashboard-grid 是 1.65fr/0.85fr，这里覆盖为 1:1） */
.dashboard-grid {
  grid-template-columns: 1fr 1fr;
}
.dashboard-grid.lower {
  grid-template-columns: 1fr;
}

/* 顶部 6 张统计卡片：3 列 + 可点击 */
.stats {
  grid-template-columns: repeat(3, 1fr);
}
.stat-card {
  padding: 18px;
  border: 1px solid #e3eaf2;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.stat-card:hover {
  box-shadow: 0 5px 15px #e0eaf8;
  border-color: #3788e8;
}
.stat-card small {
  display: block;
  color: #8c99aa;
  font-size: 11px;
}
.stat-card strong {
  display: block;
  margin: 8px 0;
  font-size: 27px;
  color: #25364d;
}
.stat-card em {
  font-style: normal;
  color: #3788e8;
  font-size: 11px;
}

.dist-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dist-item {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 1fr 50px;
  align-items: center;
  gap: 10px;
}
.dist-item.clickable {
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  transition: background 0.15s;
}
.dist-item.clickable:hover {
  background: #f0f6ff;
}
.dist-name {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 近 7 天趋势图：面板与分布面板同宽，不再铺满整页 */
.dashboard-grid.lower {
  justify-content: flex-start;
}
.chart-panel {
  max-width: 480px;
}

/* 近 7 天趋势图：柱子 + 日期标签同列对齐 */
.trend-chart {
  height: 130px;
  display: flex;
  align-items: stretch;
  gap: 8px;
  padding: 0 2px;
  border-bottom: 1px solid #e9eef4;
}
.trend-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  min-width: 0;
}
.trend-bar {
  width: 100%;
  max-width: 28px;
  min-height: 6px;
  border-radius: 3px 3px 0 0;
  background: linear-gradient(#6e9cf3, #a9c3fa);
  transition: background 0.15s;
}
.trend-col:hover .trend-bar {
  background: linear-gradient(#3788e8, #6e9cf3);
}
.trend-label {
  margin-top: 6px;
  font-size: 11px;
  color: #9ca8b6;
  white-space: nowrap;
}
.trend-empty {
  width: 100%;
  text-align: center;
  color: #9aa6b5;
  font-size: 12px;
  padding: 20px 0;
}
.dist-bar-wrap {
  height: 8px;
  background: #eef2f7;
  border-radius: 4px;
  overflow: hidden;
}
.dist-bar {
  height: 100%;
  background: linear-gradient(90deg, #3788e8, #5ca8f0);
  border-radius: 4px;
}
.dist-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
}
.empty-text {
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
