<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ raw: string | null }>();
const emit = defineEmits<{ (e: "close"): void }>();

const pretty = computed(() => {
  if (!props.raw) return "—";
  try {
    return JSON.stringify(JSON.parse(props.raw), null, 2);
  } catch {
    return props.raw;
  }
});
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal wide">
      <button class="close" @click="emit('close')">×</button>
      <h2>事件原始证据</h2>
      <pre class="evidence-json">{{ pretty }}</pre>
    </div>
  </div>
</template>

<style scoped>
.evidence-json {
  max-height: 60vh;
  overflow: auto;
  background: #f6f8fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
