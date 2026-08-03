<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <div class="panel empty-module">
    <h2>无权限访问</h2>
    <p>当前账号的角色权限不包含该页面，如需访问请联系管理员调整权限配置。</p>
    <button class="primary" @click="router.push('/dashboard')">返回总览看板</button>
  </div>
</template>
