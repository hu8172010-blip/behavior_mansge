<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, type PersonItem } from "../api";

const keyword = ref("");
const isFocused = ref<number | undefined>(undefined);
const page = ref(1);
const size = 10;
const total = ref(0);
const persons = ref<PersonItem[]>([]);
const loading = ref(false);
const errorText = ref("");
const notice = ref("");
const submitting = ref(false);
const exporting = ref(false);
const jumpPage = ref<number | null>(null);

async function loadPersons() {
  loading.value = true;
  try {
    const result = await api.persons({ keyword: keyword.value || undefined, is_focused: isFocused.value, page: page.value, size });
    persons.value = result.list;
    total.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  loadPersons();
}

async function exportData() {
  exporting.value = true;
  try {
    await api.exportPersons({ keyword: keyword.value || undefined, is_focused: isFocused.value });
    notice.value = "人员资料已导出为 CSV 文件";
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

function goToPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / size));
  let p = Number(jumpPage.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === page.value) return;
  page.value = p;
  jumpPage.value = null;
  loadPersons();
}

async function toggleFocus(item: PersonItem) {
  submitting.value = true;
  try {
    const next = item.is_focused === 1 ? 0 : 1;
    await api.togglePersonFocus(item.person_id, next);
    item.is_focused = next;
    notice.value = next === 1 ? `人员 #${item.person_id} 已标记重点关注` : `人员 #${item.person_id} 已取消重点关注`;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

onMounted(loadPersons);
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>用户资料管理</h2><p>ReID 匿名人员档案，含行为与轨迹统计、重点关注标记</p></div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <div class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="keyword" placeholder="搜索体貌特征关键字" @keyup.enter="search" /></div>
        <select v-model="isFocused" @change="search">
          <option :value="undefined">全部人员</option>
          <option :value="1">仅重点关注</option>
          <option :value="0">仅普通人员</option>
        </select>
        <button class="primary" @click="search">查询</button>
        <button :disabled="exporting" @click="exportData">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>人员编号</span><span>体貌特征</span><span>首次出现</span><span>最近出现</span><span>异常行为</span><span>轨迹数</span><span>匹配账号</span><span>操作</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!persons.length" class="table-row"><span>暂无符合条件的人员</span></div>
        <div v-for="item in persons" :key="item.person_id" class="table-row">
          <span><b>P-{{ item.person_id }}</b><em v-if="item.is_focused" class="orange">　◆重点关注</em><span v-if="item.is_lab === 1" class="tag tag-lab">模拟</span></span>
          <span>{{ item.appearance_desc || "—" }}</span>
          <span><small>{{ item.first_seen_at || "—" }}</small></span>
          <span><small>{{ item.last_seen_at || "—" }}</small></span>
          <span :class="item.behavior_count > 0 ? 'danger' : ''">{{ item.behavior_count }}</span>
          <span>{{ item.track_count }}</span>
          <span>{{ item.matched_user_name || "未匹配" }}<br /><small v-if="item.match_confidence != null">置信度 {{ (item.match_confidence * 100).toFixed(1) }}%</small></span>
          <span>
            <button v-if="item.is_focused === 0" class="btn-sm btn-ignore" :disabled="submitting" @click="toggleFocus(item)">标记关注</button>
            <button v-else class="btn-sm btn-assign" :disabled="submitting" @click="toggleFocus(item)">取消关注</button>
          </span>
        </div>
      </div>
      <div class="pager">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadPersons()">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ Math.max(1, Math.ceil(total / size)) }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadPersons()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="jumpPage" type="number" min="1" :max="Math.max(1, Math.ceil(total / size))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToPage" />
        <span>页</span>
        <button @click="goToPage" :disabled="!jumpPage">GO</button>
      </div>
    </div>
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
