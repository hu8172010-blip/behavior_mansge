<template>
  <div>
    <div class="page-heading">
      <div><h2>数据管理</h2><p>系统数据总量、类型分布、区域分布与近7天趋势概览</p></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-else-if="loading" class="panel" style="padding: 40px; text-align: center">数据加载中...</div>

    <template v-else-if="data">
      <div class="stats">
        <div><small>异常行为</small><strong>{{ data.total.behavior_count }}</strong><em>条记录</em></div>
        <div><small>轨迹链路</small><strong>{{ data.total.track_count }}</strong><em>条链路</em></div>
        <div><small>预警事件</small><strong>{{ data.total.alert_count }}</strong><em>条预警</em></div>
        <div><small>处置工单</small><strong>{{ data.total.work_order_count }}</strong><em>张工单</em></div>
        <div><small>匿名人员</small><strong>{{ data.total.person_count }}</strong><em>人</em></div>
        <div><small>设备总数</small><strong>{{ data.total.device_count }}</strong><em>台设备</em></div>
      </div>

      <div class="dashboard-grid">
        <article class="panel">
          <div class="panel-title">
            <div><h3>行为类型分布</h3><p>按异常行为类型统计</p></div>
          </div>
          <div class="dist-list" v-if="data.type_distribution.length">
            <div v-for="item in data.type_distribution" :key="item.name" class="dist-item">
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
            <div><h3>区域分布</h3><p>按设备所属区域统计</p></div>
          </div>
          <div class="dist-list" v-if="data.region_distribution.length">
            <div v-for="item in data.region_distribution" :key="item.name" class="dist-item">
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
          <div class="fake-chart">
            <i v-for="point in data.seven_day_trend" :key="point.date" :style="{ height: barHeight(point.count) }" :title="`${point.date}：${point.count}起`"></i>
            <i v-if="!data.seven_day_trend.length" style="height: 8%"></i>
          </div>
          <div class="chart-labels">
            <span v-for="point in data.seven_day_trend" :key="'label-' + point.date">{{ point.date.slice(5) }}</span>
            <span v-if="!data.seven_day_trend.length">暂无数据</span>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type DataIndexSummary } from "../api";

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
  return `${Math.max(8, Math.round((count / max) * 90))}%`;
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
.dist-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dist-item {
  display: grid;
  grid-template-columns: 100px 1fr 50px;
  align-items: center;
  gap: 10px;
}
.dist-name {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
