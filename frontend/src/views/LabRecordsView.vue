<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import type { LabRecordItem } from "../api";

const router = useRouter();
const records = ref<LabRecordItem[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(10);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const res = await api.labRecords({ page: page.value, size: size.value });
    records.value = res.list;
    total.value = res.total;
  } catch (e: any) {
    alert(e?.message || "加载记录失败");
  } finally {
    loading.value = false;
  }
}

function restore(id: number) {
  router.push(`/lab/simulation?recordId=${id}`);
}

async function publish(id: number) {
  const rec = records.value.find((r) => r.record_id === id);
  if (!rec) return;
  if (rec.is_published) {
    alert("该记录已发布到业务库。");
    return;
  }
  if (!confirm(`确认将记录「${rec.record_name}」发布到业务库？`)) return;
  try {
    await api.labRecordPublish(id);
    rec.is_published = 1;
    alert("已发布到业务库");
  } catch (e: any) {
    alert(e?.message || "发布失败");
  }
}

async function unpublish(id: number) {
  const rec = records.value.find((r) => r.record_id === id);
  if (!rec) return;
  if (!rec.is_published) {
    alert("该记录尚未发布。");
    return;
  }
  if (!confirm(`确认将撤销「${rec.record_name}」的发布？这将删除已生成的模拟业务数据。`)) return;
  try {
    // 假设后端有撤销发布的接口，或者我们重新发布并覆盖（逻辑上需要一个删除接口）
    // 这里先假设调用一个 unpublish 接口
    await api.labRecordUnpublish(id); // 后端需要新增此接口
    rec.is_published = 0;
    alert("已撤销发布，相关模拟数据已清除。");
  } catch (e: any) {
    alert(e?.message || "撤销失败");
  }
}

async function remove(id: number) {
  if (!confirm("确认删除该模拟记录？此操作将同时清除关联的模拟数据（如果已发布）。")) return;
  try {
    await api.labRecordDelete(id);
    records.value = records.value.filter((r) => r.record_id !== id);
  } catch (e: any) {
    alert(e?.message || "删除失败");
  }
}

async function clearAll() {
  if (!confirm("⚠️ 警告：此操作将删除【所有用户】的全部模拟数据（包括已发布的），且不可恢复！\n\n确认继续吗？")) return;
  if (!confirm("请再次确认：真的要清空全部模拟实验室数据吗？")) return;
  try {
    await api.labClearSandbox();
    alert("所有模拟数据已清空！");
    load(); // 刷新列表
  } catch (e: any) {
    alert(e?.message || "清空失败");
  }
}

function onPageChange(next: number) {
  page.value = next;
  load();
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-heading">
      <div>
        <h2>我的模拟记录</h2>
        <p>查看已保存的模拟实验记录，可发布、撤销或删除。<strong>注意</strong>：发布的模拟数据会在业务列表中带“模拟”标签展示。</p>
      </div>
    </div>

    <div class="panel data-panel">
      <div class="toolbar">
        <button class="primary" @click="$router.push('/lab/simulation')">新建模拟</button>
        <button class="danger" style="margin-left: auto" @click="clearAll">清空全部模拟数据</button>
      </div>
      <div class="table full">
        <div class="table-head">
          <span>记录名称</span>
          <span>模拟设备</span>
          <span>创建时间</span>
          <span>事件数</span>
          <span>轨迹数</span>
          <span>发布状态</span>
          <span>操作</span>
        </div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!records.length" class="table-row"><span>暂无模拟记录</span></div>
        <div v-for="rec in records" :key="rec.record_id" class="table-row">
          <span>{{ rec.record_name }}</span>
          <span>{{ rec.device_id ? `设备 ID ${rec.device_id}` : '—' }}</span>
          <span>{{ rec.create_time }}</span>
          <span>{{ rec.event_count }}</span>
          <span>{{ rec.track_count }}</span>
          <span>
            <span v-if="rec.is_published" style="color: #52c41a; font-weight: bold;">● 已发布</span>
            <span v-else style="color: #faad14;">● 未发布</span>
          </span>
          <span>
            <button class="link" @click="restore(rec.record_id)">查看</button>
            <button v-if="!rec.is_published" class="link" style="color: #52c41a" @click="publish(rec.record_id)">发布</button>
            <button v-else class="link" style="color: #fa8c16" @click="unpublish(rec.record_id)">撤销发布</button>
            <button class="link" style="color: #ff4d4f" @click="remove(rec.record_id)">删除</button>
          </span>
        </div>
      </div>
      <div class="pagination" v-if="total > size">
        <button :disabled="page === 1" @click="onPageChange(page - 1)">上一页</button>
        <span>{{ page }} / {{ Math.ceil(total / size) }}</span>
        <button :disabled="page * size >= total" @click="onPageChange(page + 1)">下一页</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.table-row span:last-child {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.table-row .link {
  padding: 4px 10px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
}
</style>
