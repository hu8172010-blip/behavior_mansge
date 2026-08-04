<template>
  <div class="modal-mask" v-if="visible" @click.self="close">
    <div class="modal person-modal">
      <div class="modal-header">
        <h3>人员详情</h3>
        <button class="modal-close" @click="close">&times;</button>
      </div>
      <div class="modal-body" v-if="detail">
        <div class="person-info-grid">
          <div class="info-item"><span class="label">人员ID</span><span class="value">{{ detail.person_id }}</span></div>
          <div class="info-item"><span class="label">是否关注</span><span class="value">{{ detail.is_focused ? "重点关注" : "普通" }}</span></div>
          <div class="info-item"><span class="label">首次出现</span><span class="value">{{ detail.first_seen_at || "-" }}</span></div>
          <div class="info-item"><span class="label">最后出现</span><span class="value">{{ detail.last_seen_at || "-" }}</span></div>
          <div class="info-item full"><span class="label">外貌特征</span><span class="value">{{ detail.appearance_desc || "-" }}</span></div>
          <div class="info-item"><span class="label">风险等级</span><span class="value">{{ detail.risk_level_name || (detail.risk_level_id ? `L${detail.risk_level_id}` : "—") }}</span></div>
          <div class="info-item"><span class="label">匹配账号</span><span class="value">{{ detail.matched_user_name || "-" }}</span></div>
          <div class="info-item"><span class="label">匹配置信度</span><span class="value">{{ detail.match_confidence ?? "-" }}</span></div>
          <div class="info-item"><span class="label">行为次数</span><span class="value">{{ detail.behavior_count }}</span></div>
          <div class="info-item"><span class="label">轨迹次数</span><span class="value">{{ detail.track_count }}</span></div>
        </div>

        <h4 class="section-title">最近行为记录</h4>
        <table class="data-table" v-if="detail.recent_behaviors.length">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>等级</th>
              <th>状态</th>
              <th>设备</th>
              <th>区域</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in detail.recent_behaviors" :key="b.behavior_id">
              <td>{{ b.detected_at }}</td>
              <td>{{ b.type_name }}</td>
              <td>{{ b.level_name }}</td>
              <td>{{ b.status_name }}</td>
              <td>{{ b.device_name || "-" }}</td>
              <td>{{ b.region_name || "-" }}</td>
            </tr>
          </tbody>
        </table>
        <p class="empty-text" v-else>暂无行为记录</p>
      </div>
      <div class="modal-body empty" v-if="loadError">{{ loadError }}</div>
      <div class="modal-body empty" v-else-if="!detail">加载中...</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { api, type PersonDetail } from "../api";

const props = defineProps<{ visible: boolean; personId: number | null }>();
const emit = defineEmits<{ (e: "update:visible", value: boolean): void }>();

const detail = ref<PersonDetail | null>(null);
const loadError = ref("");

watch(
  () => [props.visible, props.personId],
  async ([visible, personId]) => {
    if (visible && personId) {
      detail.value = null;
      loadError.value = "";
      try {
        detail.value = await api.personDetail(personId);
      } catch (error: any) {
        detail.value = null;
        loadError.value = error.message || "人员详情加载失败";
      }
    }
  },
  { immediate: true }
);

function close() {
  emit("update:visible", false);
}
</script>

<style scoped>
.person-modal {
  max-width: 720px;
  width: 90%;
  max-height: 80vh;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #e8edf3;
  background: #f8fafc;
  flex-shrink: 0;
}
.modal-header h3 {
  margin: 0;
  font-size: 15px;
  color: #25364d;
}
.modal-close {
  font-size: 20px;
  line-height: 1;
  color: #93a0af;
  background: none;
  border: 0;
  cursor: pointer;
}
.modal-close:hover {
  color: #e76b71;
}
.modal-body {
  padding: 18px 20px;
  background: #fff;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.person-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.info-item.full {
  grid-column: 1 / -1;
}
.info-item .label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.info-item .value {
  font-size: 14px;
  color: var(--text-primary);
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 12px;
  color: var(--text-primary);
}
.empty-text {
  color: var(--text-secondary);
  font-size: 13px;
}
.modal-body.empty {
  text-align: center;
  padding: 40px 0;
  color: var(--text-secondary);
}
/* 最近行为记录表格：补全 padding/边框/字号 */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.data-table th,
.data-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid #eef2f8;
  vertical-align: middle;
  color: #35465e;
}
.data-table th {
  font-weight: 600;
  color: #6b7c91;
  background: #f6f9fc;
  font-size: 11px;
  white-space: nowrap;
}
.data-table tbody tr:hover {
  background: #f9fbff;
}
</style>
