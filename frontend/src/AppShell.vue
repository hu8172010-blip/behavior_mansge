<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "./stores/auth";
import { useSettingsStore } from "./stores/settings";
import { connectPermissionSocket, disconnectPermissionSocket } from "./api/ws";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const settings = useSettingsStore();

interface NavItem { text: string; path: string; icon: string; perm: string }
interface NavGroup { label: string; items: NavItem[] }

const navGroups: NavGroup[] = [
  { label: "工作台", items: [{ text: "总览看板", path: "/dashboard", icon: "▦", perm: "dashboard:view" }] },
  { label: "轨迹管理", items: [{ text: "实时轨迹", path: "/track/realtime", icon: "◉", perm: "track:realtime" }, { text: "事后轨迹", path: "/track/history", icon: "⌁", perm: "track:history" }] },
  { label: "设备管理", items: [{ text: "设备列表", path: "/device/list", icon: "▣", perm: "device:view" }, { text: "维修工单", path: "/device/repair-order", icon: "⚒", perm: "device:repair" }] },
  { label: "数据管理", items: [{ text: "数据管理首页", path: "/data/index", icon: "▤", perm: "data:view" }, { text: "异常行为记录", path: "/data/abnormal-record", icon: "!", perm: "behavior:query" }, { text: "轨迹记录", path: "/data/track-record", icon: "⌁", perm: "track:query" }, { text: "备份与恢复", path: "/data/backup", icon: "↥", perm: "data:view" }, { text: "用户资料", path: "/data/user-profile", icon: "♙", perm: "person:query" }, { text: "操作日志", path: "/data/operation-log", icon: "≡", perm: "log:view" }] },
  { label: "告警与工单", items: [{ text: "告警待办", path: "/alarm/todo", icon: "⚠", perm: "alarm:view" }] },
  { label: "用户权限", items: [{ text: "权限管理", path: "/system/index", icon: "⚙", perm: "system:view" }, { text: "角色管理", path: "/system/role", icon: "◈", perm: "system:view" }, { text: "账号管理", path: "/system/user", icon: "♙", perm: "system:view" }] },
  { label: "模拟实验", items: [{ text: "模拟实验室", path: "/lab/simulation", icon: "◬", perm: "data:view" }] },
];

const visibleNavGroups = computed(() =>
  navGroups
    .map((group) => ({ ...group, items: group.items.filter((item) => auth.hasPermission(item.perm)) }))
    .filter((group) => group.items.length > 0)
);

const isLoginPage = computed(() => route.path === "/login");
const pageTitle = computed(() => (route.meta.title as string) || "总览看板");
const currentPath = computed(() => route.path);
const todayLabel = computed(() => new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }));
const avatarText = computed(() => (auth.realName || "用").slice(0, 1));

let refreshTimer: number | null = null;
let pendingCountTimer: number | null = null;

function handlePermChange() {
  if (refreshTimer) window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    auth.refreshPermissions();
  }, 500);
}

function ensureSocket() {
  if (auth.token) {
    connectPermissionSocket(auth.token, handlePermChange);
  } else {
    disconnectPermissionSocket();
  }
}

function go(path: string) { router.push(path); }
function logout() { auth.logout(); router.push("/login"); }

onMounted(async () => {
  auth.restore();
  settings.initFilterLabData();
  if (auth.isLoggedIn) {
    await auth.refreshPendingCount();
  pendingCountTimer = window.setInterval(() => {
    if (auth.isLoggedIn) auth.refreshPendingCount();
  }, 30000);
  }
});

onUnmounted(() => {et();
  if (pendingCountTimer) window.clarInervalpendingCountTimer
  disconnectPermissionSocket();
});

watch(
  auth.token,
  (newToken, oldToken) => {
    if (newToken !== oldToken) {
      disconnectPermissionSocket();
      if (newToken) {
        ensureSocket();
      }
    }
  },
  { immediate: true }
);
</script>

<template>
  <router-view v-if="isLoginPage" />
  <div v-else class="system-shell">
    <aside class="side">
      <div class="side-brand"><span>观</span><div><b>智行观测</b><small>BEHAVIOR INSIGHT</small></div></div>
      <div class="workspace"><i></i><div><small>当前工作空间</small><b>城市治理示范区</b></div></div>
      <nav>
        <template v-for="group in visibleNavGroups" :key="group.label">
          <div class="nav-group">{{ group.label }}</div>
          <button v-for="item in group.items" :key="item.path" :class="{ active: currentPath === item.path }" @click="go(item.path)">
            <span>{{ item.icon }}</span>{{ item.text }}<em v-if="item.path === '/alarm/todo' && auth.pendingAlertCount > 0">{{ auth.pendingAlertCount }}</em>
          </button>
        </template>
      </nav>
      <div class="side-footer">
        <div class="help">需要帮助？<small>查看操作手册　→</small></div>
        <div class="profile"><span>{{ avatarText }}</span><div><b>{{ auth.realName }}</b><small>{{ auth.roleName || "—" }}</small></div><button @click="logout">退出</button></div>
      </div>
    </aside>
    <main class="main">
      <header>
        <div><small>工作台 / {{ pageTitle }}</small><h1>{{ pageTitle }}</h1></div>
        <div class="header-actions">
          <div class="filter-toggle">
            <span>过滤模拟数据</span>
            <label class="switch">
              <input type="checkbox" v-model="settings.filterLabData" @change="settings.setFilterLabData(settings.filterLabData)">
              <span class="slider round"></span>
            </label>
          </div>
          <span>◷ {{ todayLabel }}</span>
          <b>{{ avatarText }}</b>
        </div>
      </header>
      <section class="page-content">
        <router-view />
      </section>
    </main>
  </div>
</template>

<style scoped>
.filter-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}
.switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: #ccc;
  transition: .4s;
  border-radius: 22px;
}
.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .4s;
  border-radius: 50%;
}
input:checked + .slider {
  background-color: #3788e8;
}
input:checked + .slider:before {
  transform: translateX(18px);
}
</style>
