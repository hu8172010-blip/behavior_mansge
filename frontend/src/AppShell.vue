<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "./stores/auth";
import { useSettingsStore } from "./stores/settings";
import { api } from "./api";
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

// —— 修改密码（用户自己改自己的密码）——
const showChangePwd = ref(false);
const showHelp = ref(false);
const pwdForm = reactive({ old_password: "", new_password: "", confirm_password: "" });
const pwdSubmitting = ref(false);
const pwdError = ref("");
// 超管改密码免原密码（type_id=1）
const pwdIsSuper = computed(() => auth.typeId === 1);
const pwdShowOld = computed(() => !pwdIsSuper.value);

function openChangePwd() {
  pwdForm.old_password = "";
  pwdForm.new_password = "";
  pwdForm.confirm_password = "";
  pwdError.value = "";
  showChangePwd.value = true;
}

async function submitChangePwd() {
  pwdError.value = "";
  if (pwdShowOld.value && !pwdForm.old_password) { pwdError.value = "请输入原密码"; return; }
  if (pwdForm.new_password.length < 6) { pwdError.value = "新密码至少 6 个字符"; return; }
  if (pwdForm.new_password !== pwdForm.confirm_password) { pwdError.value = "两次输入的新密码不一致"; return; }
  pwdSubmitting.value = true;
  try {
    await api.changeAccountPassword(auth.accountId, {
      old_password: pwdShowOld.value ? pwdForm.old_password : undefined,
      new_password: pwdForm.new_password,
    });
    showChangePwd.value = false;
    // 提示用户重新登录
    alert("密码已修改，请重新登录");
    auth.logout();
    router.push("/login");
  } catch (error: any) {
    pwdError.value = error.message || "修改失败";
  } finally {
    pwdSubmitting.value = false;
  }
}

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
        <button class="help" @click="showHelp = true">需要帮助？<small>查看操作手册　→</small></button>
        <div class="profile"><span>{{ avatarText }}</span><div><b>{{ auth.realName }}</b><small>{{ auth.roleName || "—" }}</small></div><button @click="logout">退出</button></div>
      </div>
    </aside>
    <main class="main">
      <header>
        <div><small>工作台 / {{ pageTitle }}</small><h1>{{ pageTitle }}</h1></div>
        <div class="header-actions">
          <button class="change-pwd-btn" @click="openChangePwd">修改密码</button>
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

    <!-- 修改密码弹窗（用户自己改自己的密码） -->
    <div v-if="showChangePwd" class="modal-mask" @click.self="showChangePwd = false">
      <div class="modal pwd-modal">
        <button class="close" @click="showChangePwd = false">×</button>
        <h2>修改密码</h2>
        <div class="pwd-form">
          <div v-if="pwdShowOld" class="pwd-field">
            <label>原密码</label>
            <input v-model="pwdForm.old_password" type="password" placeholder="请输入当前密码" />
          </div>
          <div class="pwd-field">
            <label>新密码</label>
            <input v-model="pwdForm.new_password" type="password" placeholder="至少 6 个字符" />
          </div>
          <div class="pwd-field">
            <label>确认新密码</label>
            <input v-model="pwdForm.confirm_password" type="password" placeholder="再次输入新密码" />
          </div>
        </div>
        <div v-if="pwdError" class="error pwd-error">{{ pwdError }}</div>
        <button class="primary pwd-submit" :disabled="pwdSubmitting" @click="submitChangePwd">{{ pwdSubmitting ? "提交中..." : "确认修改" }}</button>
      </div>
    </div>

    <!-- 帮助弹窗 -->
    <div v-if="showHelp" class="modal-mask" @click.self="showHelp = false">
      <div class="modal" style="width: 520px; max-width: 90vw">
        <button class="close" @click="showHelp = false">×</button>
        <h2>操作手册</h2>
        <p style="color:#35465e;line-height:1.8">
          <b>异常行为与告警分析系统</b> - 用户操作手册<br /><br />
          1. <b>总览看板</b>：查看实时事件总数、设备健康、事件趋势<br />
          2. <b>告警待办</b>：处理预警事件、派发维修工单、跟踪处置<br />
          3. <b>设备管理</b>：查看设备列表与状态、处理维修工单<br />
          4. <b>数据管理</b>：数据备份/恢复、异常行为查询、用户资料<br />
          5. <b>权限管理</b>：账号、角色、自定义权限配置<br />
          6. <b>模拟实验室</b>：视频模拟生成业务数据，测试全流程<br /><br />
          <b>遇到问题？</b>请截图联系系统管理员。
        </p>
        <button class="primary" style="margin-top: 8px" @click="showHelp = false">知道了</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.change-pwd-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid #dbe3ed;
  border-radius: 4px;
  background: #fff;
  color: #65748a;
  font-size: 13px;
  cursor: pointer;
}
.change-pwd-btn:hover {
  border-color: #3788e8;
  color: #3788e8;
}
/* 修改密码弹窗：label 独占一行 + input 占满宽度，避免和 label 横向挤在一行 */
.pwd-modal {
  width: 380px;
  max-width: 90vw;
}
.pwd-modal h2 {
  margin-bottom: 18px;
}
.pwd-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.pwd-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pwd-field label {
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
}
.pwd-field input {
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: 1px solid #dbe3ed;
  border-radius: 5px;
  font-size: 13px;
  color: #35465e;
  box-sizing: border-box;
  outline: 0;
}
.pwd-field input:focus {
  border-color: #3788e8;
}
.pwd-error {
  margin-top: 12px;
  color: #e23b3b;
  font-size: 12px;
}
.pwd-submit {
  width: 100%;
  height: 38px;
  margin-top: 18px;
}
/* "需要帮助？查看操作手册" 按钮：恢复 .help 原本的深底色样式（避免全局 button 清除背景） */
:deep(.side-footer .help) {
  padding: 13px;
  border-radius: 6px;
  background: #26384d;
  color: #dbe4ef;
  font-size: 12px;
  border: 0;
  width: 100%;
  text-align: left;
  cursor: pointer;
}
:deep(.side-footer .help small) {
  display: block;
  margin-top: 6px;
  color: #8ea0b7;
}
:deep(.side-footer .help:hover) {
  background: #2c415a;
}
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
