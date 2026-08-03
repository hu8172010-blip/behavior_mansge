<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, type WorkOrderDetail } from "../api";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const detail = ref<WorkOrderDetail | null>(null);
const loading = ref(true);
const errorText = ref("");
const notice = ref("");
const handleResult = ref("");
const submitting = ref(false);

async function loadDetail() {
  loading.value = true;
  try {
    detail.value = await api.workOrderDetail(Number(route.params.orderId));
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function submitHandle() {
  if (!detail.value || !handleResult.value.trim()) {
    errorText.value = "请填写处置结果";
    return;
  }
  submitting.value = true;
  try {
    await api.handleWorkOrder(detail.value.work_order_id, handleResult.value.trim());
    notice.value = "处置结果已提交，工单已完成";
    handleResult.value = "";
    await Promise.all([loadDetail(), auth.refreshPendingCount()]);
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

async function submitClose() {
  if (!detail.value) return;
  submitting.value = true;
  try {
    await api.closeWorkOrder(detail.value.work_order_id);
    notice.value = "工单已关闭归档";
    await loadDetail();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

onMounted(loadDetail);
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>处置工单详情</h2><p>查看工单关联的预警与异常行为信息，执行处置与归档</p></div>
      <button class="link" @click="router.push('/alarm/todo')">← 返回待办列表</button>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>
    <div v-if="loading" class="panel" style="padding: 40px; text-align: center">加载中...</div>

    <template v-else-if="detail">
      <div class="dashboard-grid">
        <article class="panel">
          <div class="panel-title"><div><h3>工单信息</h3><p>{{ detail.work_order_no }}</p></div></div>
          <p><b>工单状态：</b><span :class="detail.work_order_status_id === 4 ? 'success' : 'warn'">{{ detail.status_name }}</span></p>
          <p><b>事件类型：</b>{{ detail.type_name }}　<b>严重级别：</b><span :class="detail.level_name === '高' ? 'danger' : detail.level_name === '中' ? 'warn' : ''">{{ detail.level_name }}</span></p>
          <p><b>事件描述：</b>{{ detail.description || "—" }}</p>
          <p><b>检出时间：</b>{{ detail.detected_at }}　<b>置信度：</b>{{ detail.confidence_score ?? "—" }}</p>
          <p><b>位置 / 设备：</b>{{ detail.region_name || "—" }}（{{ detail.camera_name || "—" }} {{ detail.camera_code || "" }}）</p>
          <p><b>人员特征：</b>{{ detail.person_desc || "—" }}</p>
          <p><b>关联轨迹：</b>{{ detail.track_id ? "轨迹链路 #" + detail.track_id : "—" }}</p>
        </article>
        <article class="panel">
          <div class="panel-title"><div><h3>处置流转</h3><p>派单 → 处置 → 归档</p></div></div>
          <p><b>派单人：</b>{{ detail.assigner_name || "—" }}　<b>派单时间：</b>{{ detail.assigned_at }}</p>
          <p><b>处理人：</b>{{ detail.assignee_name }}</p>
          <p v-if="detail.handled_at"><b>处置完成时间：</b>{{ detail.handled_at }}　<b>耗时：</b>{{ detail.handle_duration_minutes ?? "—" }} 分钟</p>
          <p v-if="detail.handle_result"><b>处置结果：</b>{{ detail.handle_result }}</p>

          <template v-if="(detail.work_order_status_id === 1 || detail.work_order_status_id === 2) && auth.hasPermission('workorder:handle')">
            <label style="display: block; margin: 14px 0 8px">填写处置结果</label>
            <input v-model="handleResult" placeholder="例如：现场核实为误入，已劝离并恢复正常" style="width: 100%; height: 40px; padding: 0 12px; border: 1px solid #dbe3ed; border-radius: 5px" />
            <button class="primary" style="margin-top: 12px" :disabled="submitting" @click="submitHandle">提交处置结果</button>
          </template>
          <button v-if="detail.work_order_status_id === 3 && auth.hasPermission('workorder:handle')" class="primary" :disabled="submitting" @click="submitClose">关闭归档</button>
          <p v-if="detail.work_order_status_id === 4" class="success">该工单已关闭归档，全流程结束。</p>
        </article>
      </div>
    </template>
  </div>
</template>
