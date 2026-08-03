<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => (route.meta.title as string) || "功能模块");
</script>

<template>
  <div class="panel empty-module">
    <h2>{{ title }}</h2>
    <p>该模块已预留路由与菜单入口，将在下一阶段接入真实业务数据后交付使用。</p>
  </div>
</template>
