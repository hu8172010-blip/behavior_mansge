import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { api, type LoginResult } from "../api";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem("token") || "");
  const accountId = ref<number | null>(null);
  const loginName = ref("");
  const realName = ref("");
  const dept = ref<string | null>(null);
  const typeId = ref<number | null>(null);
  const roleName = ref<string | null>(null);
  const permissions = ref<string[]>([]);
  const pendingAlertCount = ref(0);

  const isLoggedIn = computed(() => Boolean(token.value));

  function applyUser(user: Omit<LoginResult, "token">) {
    accountId.value = user.account_id;
    loginName.value = user.login_name;
    realName.value = user.real_name;
    dept.value = user.dept;
    typeId.value = user.type_id;
    roleName.value = user.role_name;
    permissions.value = user.permissions;
  }

  function restore() {
    const raw = localStorage.getItem("user");
    if (token.value && raw) {
      try {
        applyUser(JSON.parse(raw));
      } catch {
        logout();
      }
    }
  }

  async function login(name: string, password: string) {
    const result = await api.login(name, password);
    token.value = result.token;
    localStorage.setItem("token", result.token);
    applyUser(result);
    localStorage.setItem("user", JSON.stringify({ ...result, token: undefined }));
    await refreshPendingCount();
  }

  async function refreshPendingCount() {
    try {
      const result = await api.todoCount();
      pendingAlertCount.value = result.count;
    } catch {
      pendingAlertCount.value = 0;
    }
  }

  async function refreshPermissions() {
    try {
      const user = await api.me();
      applyUser(user);
      localStorage.setItem("user", JSON.stringify({ ...user, token: undefined }));
    } catch {
      logout();
    }
  }

  function hasPermission(key: string): boolean {
    if (!key) return true;
    return permissions.value.includes(key);
  }

  function logout() {
    token.value = "";
    accountId.value = null;
    loginName.value = "";
    realName.value = "";
    dept.value = null;
    typeId.value = null;
    roleName.value = null;
    permissions.value = [];
    pendingAlertCount.value = 0;
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  }

  return {
    token,
    accountId,
    loginName,
    realName,
    dept,
    typeId,
    roleName,
    permissions,
    pendingAlertCount,
    isLoggedIn,
    restore,
    login,
    logout,
    hasPermission,
    refreshPendingCount,
    refreshPermissions,
  };
});
