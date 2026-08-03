<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, type TrackDetail } from "../api";

const props = defineProps<{ chainId: number }>();
const emit = defineEmits<{ (e: "close"): void }>();

const detail = ref<TrackDetail | null>(null);
const errorText = ref("");

function formatDuration(sec: number): string {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}分${s}秒` : `${s}秒`;
}

onMounted(async () => {
  try {
    detail.value = await api.trackDetail(props.chainId);
  } catch (error: any) {
    errorText.value = error.message;
  }
});
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal wide">
      <button class="close" @click="emit('close')">×</button>
      <h2>轨迹链路详情</h2>
      <div v-if="errorText" class="error">{{ errorText }}</div>
      <div v-else-if="!detail">加载中...</div>
      <template v-else>
        <p>
          <b>链路编号：</b>{{ detail.chain_unique_id }}　<b>状态：</b
          ><span :class="detail.chain_status === 1 ? 'warn' : 'success'">{{ detail.chain_status === 1 ? "行进中" : "已归档" }}</span>
        </p>
        <p>
          <b>人员特征：</b>{{ detail.appearance_desc || "未知人员"
          }}<em v-if="detail.is_focused" class="orange">　◆重点关注</em>　<b>匹配置信度：</b
          >{{ detail.confidence != null ? (detail.confidence * 100).toFixed(1) + "%" : "—" }}
        </p>
        <p>
          <b>开始时间：</b>{{ detail.chain_start_time }}　<b>结束时间：</b>{{ detail.chain_end_time || "进行中" }}　<b>总时长：</b
          >{{ formatDuration(detail.total_duration_sec) }}
        </p>
        <div class="track-steps">
          <div v-for="(item, index) in detail.items" :key="item.item_id" class="track-step">
            <div class="step-node"><i>{{ index + 1 }}</i><span v-if="index < detail.items.length - 1" class="step-line"></span></div>
            <div class="step-body">
              <b>{{ item.device_name }}</b><small>{{ item.device_code }} · {{ item.region_name || "—" }} · {{ item.location_text || "—" }}</small>
              <small>出现 {{ item.appear_time }}　离开 {{ item.disappear_time || "仍在画面中" }}　停留 {{ formatDuration(item.stay_duration_sec) }}</small>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
