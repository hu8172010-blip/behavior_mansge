<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api, type AccountItem, type MetaEnums, type PermItem } from "../api";
import { useAuthStore } from "../stores/auth";
import { usePermissionTree } from "../composables/usePermissionTree";

const auth = useAuthStore();

const keyword = ref("");
const typeId = ref<number | undefined>(undefined);
const status = ref<number | undefined>(undefined);
const page = ref(1);
const size = 10;
const total = ref(0);
const accounts = ref<AccountItem[]>([]);
const loading = ref(false);
const errorText = ref("");
const notice = ref("");
const submitting = ref(false);
const enums = ref<MetaEnums | null>(null);

const showCreate = ref(false);
const showPerm = ref(false);
const form = reactive({ login_name: "", password: "", real_name: "", dept: "", phone: "", type_id: 0 });
const permAccount = ref<AccountItem | null>(null);
const permissions = ref<PermItem[]>([]);
const useCustom = ref(0);
const permChecked = ref<Set<number>>(new Set());
const permLoading = ref(false);

const { indeterminate, toggle: togglePerm, initChecked, vIndeterminate } = usePermissionTree(permissions, permChecked);

async function loadAccounts() {
  loading.value = true;
  try {
    const result = await api.accounts({ keyword: keyword.value || undefined, type_id: typeId.value, status: status.value, page: page.value, size });
    accounts.value = result.list;
    total.value = result.total;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  loadAccounts();
}

const menuGroups = computed(() => {
  const menus = permissions.value.filter((item) => item.perm_type === 1);
  return menus.map((menu) => ({
    menu,
    children: permissions.value.filter((item) => item.parent_id === menu.perm_id),
  }));
});

async function openPermissions(item: AccountItem) {
  permAccount.value = item;
  showPerm.value = true;
  useCustom.value = item.use_custom || 0;
  permChecked.value = new Set();
  permissions.value = [];
  permLoading.value = true;
  errorText.value = "";
  notice.value = "";
  try {
    const [permList, info] = await Promise.all([api.permissions(), api.accountPermissions(item.account_id)]);
    permissions.value = permList;
    useCustom.value = info.use_custom;
    const base = useCustom.value ? info.custom_perm_ids : info.role_perm_ids;
    initChecked(base);
  } catch (error: any) {
    errorText.value = error.message;
    showPerm.value = false;
  } finally {
    permLoading.value = false;
  }
}


async function savePermissions() {
  const account = permAccount.value;
  if (!account) return;
  if (useCustom.value && !permChecked.value.size) {
    errorText.value = "自定义权限模式下至少需要选择一项权限";
    return;
  }
  permLoading.value = true;
  try {
    await api.saveAccountPermissions(account.account_id, { use_custom: useCustom.value, perm_ids: Array.from(permChecked.value) });
    account.use_custom = useCustom.value;
    notice.value = `${account.login_name} 的权限已保存`;
    showPerm.value = false;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    permLoading.value = false;
  }
}

async function deleteAccount(item: AccountItem) {
  if (!confirm(`确定删除账号 ${item.login_name} 吗？`)) return;
  submitting.value = true;
  try {
    await api.deleteAccount(item.account_id);
    notice.value = `账号 ${item.login_name} 已删除`;
    await loadAccounts();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

function openCreate() {
  Object.assign(form, { login_name: "", password: "", real_name: "", dept: "", phone: "", type_id: enums.value?.roles[0]?.id ?? 0 });
  showCreate.value = true;
}

async function submitCreate() {
  if (!form.login_name.trim() || !form.password.trim() || !form.real_name.trim() || !form.type_id) {
    errorText.value = "请完整填写登录名、密码、姓名与角色";
    return;
  }
  submitting.value = true;
  try {
    await api.createAccount({ ...form, dept: form.dept || undefined, phone: form.phone || undefined });
    showCreate.value = false;
    notice.value = `账号 ${form.login_name} 已创建`;
    await loadAccounts();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

async function toggleStatus(item: AccountItem) {
  submitting.value = true;
  try {
    const next = item.status === 1 ? 0 : 1;
    await api.toggleAccountStatus(item.account_id, next);
    item.status = next;
    notice.value = next === 1 ? `账号 ${item.login_name} 已启用` : `账号 ${item.login_name} 已停用`;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  try {
    enums.value = await api.enums();
  } catch {
    enums.value = null;
  }
  await loadAccounts();
});
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>账号管理</h2><p>系统账号台账、新增账号与启停用管理</p></div>
      <div class="tabs">
        <button v-if="auth.hasPermission('system:user:create')" @click="openCreate">+ 新增账号</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="notice" class="success" style="margin-bottom: 10px" @click="notice = ''">{{ notice }}</div>

    <div class="panel data-panel">
      <div class="toolbar">
        <div class="search"><span>⌕</span><input v-model="keyword" placeholder="搜索登录名 / 姓名 / 部门" @keyup.enter="search" /></div>
        <select v-model="typeId" @change="search">
          <option :value="undefined">全部角色</option>
          <option v-for="item in enums?.roles || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <select v-model="status" @change="search">
          <option :value="undefined">全部状态</option>
          <option :value="1">启用</option>
          <option :value="0">停用</option>
        </select>
        <button class="primary" @click="search">查询</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>登录名</span><span>姓名 / 部门</span><span>角色</span><span>电话</span><span>最近登录</span><span>状态</span><span>操作</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!accounts.length" class="table-row"><span>暂无符合条件的账号</span></div>
        <div v-for="item in accounts" :key="item.account_id" class="table-row">
          <span><b>{{ item.login_name }}</b></span>
          <span>{{ item.real_name }}<br /><small>{{ item.dept || "—" }}</small></span>
          <span>{{ item.type_name }}</span>
          <span><small>{{ item.phone || "—" }}</small></span>
          <span><small>{{ item.last_login_time || "从未登录" }}</small></span>
          <span :class="item.status === 1 ? 'success' : 'danger'">● {{ item.status === 1 ? "启用" : "停用" }}</span>
          <span>
            <template v-if="item.account_id !== 1 && item.account_id !== auth.accountId">
              <button v-if="item.status === 1" class="btn-sm btn-ignore" :disabled="submitting" @click="toggleStatus(item)">停用</button>
              <button v-else class="btn-sm btn-confirm" :disabled="submitting" @click="toggleStatus(item)">启用</button>
              <button v-if="auth.typeId === 1" class="btn-sm btn-ignore" @click="openPermissions(item)">权限</button>
              <button v-if="auth.typeId === 1" class="btn-sm btn-ignore" :disabled="submitting" @click="deleteAccount(item)">删除</button>
            </template>
            <span v-else>—</span>
          </span>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 12px">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadAccounts()">上一页</button>
        <span>第 {{ page }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadAccounts()">下一页</button>
      </div>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <button class="close" @click="showCreate = false">×</button>
        <h2>新增账号</h2>
        <label>登录名</label>
        <input v-model="form.login_name" placeholder="登录用户名，全局唯一" />
        <label>初始密码</label>
        <input v-model="form.password" type="password" placeholder="Mock 阶段明文存储" />
        <label>姓名</label>
        <input v-model="form.real_name" />
        <label>角色</label>
        <select v-model="form.type_id" class="role-select">
          <option v-for="item in enums?.roles || []" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <label>部门（可选）</label>
        <input v-model="form.dept" />
        <label>电话（可选）</label>
        <input v-model="form.phone" />
        <button class="primary" :disabled="submitting" @click="submitCreate">确认创建</button>
      </div>
    </div>

    <div v-if="showPerm" class="modal-mask" @click.self="showPerm = false">
      <div class="modal" style="width: 600px; max-width: 90vw">
        <button class="close" @click="showPerm = false">×</button>
        <h2>{{ permAccount?.login_name }} 的权限配置</h2>
        <p v-if="permAccount?.use_custom" style="color: #409eff">当前使用自定义权限</p>
        <p v-else style="color: #93a0b2">当前继承角色默认权限</p>
        <label>
          <input v-model="useCustom" type="checkbox" :true-value="1" :false-value="0" />
          使用自定义权限（勾选后覆盖角色权限）
        </label>
        <div v-if="permLoading">加载中...</div>
        <div v-else class="perm-panel">
          <div v-for="group in menuGroups" :key="group.menu.perm_id" class="perm-group">
            <div class="perm-group-head">
              <label>
                <input
                  type="checkbox"
                  :checked="permChecked.has(group.menu.perm_id)"
                  v-indeterminate="indeterminate.has(group.menu.perm_id)"
                  :disabled="!useCustom"
                  @change="togglePerm(group.menu.perm_id)"
                />
                <b>{{ group.menu.perm_name }}</b>
                <small>{{ group.menu.perm_key }}</small>
              </label>
              <button v-if="group.children.length" class="link" :disabled="!useCustom" @click="togglePerm(group.menu.perm_id)">全选/清空子项</button>
            </div>
            <div v-if="group.children.length" class="perm-children">
              <label v-for="child in group.children" :key="child.perm_id">
                <input
                  type="checkbox"
                  :checked="permChecked.has(child.perm_id)"
                  :disabled="!useCustom"
                  @change="togglePerm(child.perm_id)"
                />
                {{ child.perm_name }}
                <small>{{ child.perm_type === 2 ? "按钮" : "数据" }}</small>
              </label>
            </div>
          </div>
        </div>
        <div class="toolbar" style="margin-top: 16px">
          <button class="primary" :disabled="permLoading" @click="savePermissions">
            {{ permLoading ? "保存中..." : "保存" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
