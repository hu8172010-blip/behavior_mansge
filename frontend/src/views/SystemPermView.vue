<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api, type PermItem, type RoleItem } from "../api";
import { useAuthStore } from "../stores/auth";
import { usePermissionTree } from "../composables/usePermissionTree";

const route = useRoute();
const auth = useAuthStore();

const roles = ref<RoleItem[]>([]);
const permissions = ref<PermItem[]>([]);
const currentTypeId = ref<number | null>(null);
const checked = ref<Set<number>>(new Set());
const loading = ref(false);
const saving = ref(false);
const errorText = ref("");
const notice = ref("");

const canConfig = computed(() => auth.hasPermission("system:role:config"));
const currentRole = computed(() => roles.value.find((item) => item.type_id === currentTypeId.value) || null);

const { indeterminate, toggle: togglePerm, initChecked, vIndeterminate } = usePermissionTree(permissions, checked);

const menuGroups = computed(() => {
  const menus = permissions.value.filter((item) => item.perm_type === 1);
  return menus.map((menu) => ({
    menu,
    children: permissions.value.filter((item) => item.parent_id === menu.perm_id),
  }));
});

function selectRole(role: RoleItem) {
  currentTypeId.value = role.type_id;
  initChecked(role.perm_ids);
  notice.value = "";
}


async function save() {
  if (!currentTypeId.value) return;
  saving.value = true;
  try {
    await api.saveRolePermissions(currentTypeId.value, Array.from(checked.value));
    notice.value = "权限配置已保存，相关账号重新登录后生效";
    roles.value = await api.roles();
    const role = roles.value.find((item) => item.type_id === currentTypeId.value);
    if (role) initChecked(role.perm_ids);
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    const [roleList, permList] = await Promise.all([api.roles(), api.permissions()]);
    roles.value = roleList;
    permissions.value = permList;
    const fromQuery = Number(route.query.type_id);
    const target = roleList.find((item) => item.type_id === fromQuery) || roleList.find((item) => !item.is_super) || null;
    if (target) selectRole(target);
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>权限管理</h2><p>按角色配置菜单、按钮操作与数据查询权限</p></div>
      <div class="tabs">
        <button v-if="canConfig && currentRole && !currentRole.is_super" class="selected" :disabled="saving" @click="save">{{ saving ? "保存中..." : "保存配置" }}</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>
    <div v-if="loading">加载中...</div>

    <div v-else class="perm-layout">
      <div class="panel role-list">
        <button
          v-for="role in roles"
          :key="role.type_id"
          :class="{ active: role.type_id === currentTypeId }"
          @click="selectRole(role)"
        >
          <b>{{ role.type_name }}</b>
          <small>{{ role.is_super ? "全部权限（内置）" : role.perm_ids.length + " 项权限" }}</small>
        </button>
      </div>

      <div class="panel data-panel perm-panel">
        <template v-if="currentRole">
          <p v-if="currentRole.is_super" style="color:#93a0b2">超级管理员默认放行全部权限，不读取也不保存权限配置。</p>
          <template v-else>
            <div v-for="group in menuGroups" :key="group.menu.perm_id" class="perm-group">
              <div class="perm-group-head">
                <label><input
                  type="checkbox"
                  :checked="checked.has(group.menu.perm_id)"
                  v-indeterminate="indeterminate.has(group.menu.perm_id)"
                  :disabled="!canConfig"
                  @change="togglePerm(group.menu.perm_id)"
                /><b>{{ group.menu.perm_name }}</b><small>{{ group.menu.perm_key }}</small></label>
                <button v-if="group.children.length && canConfig" class="link" @click="togglePerm(group.menu.perm_id)">全选/清空子项</button>
              </div>
              <div v-if="group.children.length" class="perm-children">
                <label v-for="child in group.children" :key="child.perm_id">
                  <input type="checkbox" :checked="checked.has(child.perm_id)" :disabled="!canConfig" @change="togglePerm(child.perm_id)" />
                  {{ child.perm_name }}
                  <small>{{ child.perm_type === 2 ? "按钮" : "数据" }}</small>
                </label>
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>
