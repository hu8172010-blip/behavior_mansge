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
const jumpPage = ref<number | null>(null);
const accounts = ref<AccountItem[]>([]);
const loading = ref(false);
const exporting = ref(false);
const errorText = ref("");
const notice = ref("");
const submitting = ref(false);
const enums = ref<MetaEnums | null>(null);

const showCreate = ref(false);
const showPerm = ref(false);
const showChangePwd = ref(false);
const pwdAccount = ref<AccountItem | null>(null);
const pwdForm = reactive({ old_password: "", new_password: "", confirm_password: "" });
const pwdSubmitting = ref(false);
// 超管改密码永远免原密码（type_id=1）；其他用户改自己仍需校验
const pwdIsSelf = computed(() => pwdAccount.value?.account_id === auth.accountId);
const pwdIsSuper = computed(() => auth.typeId === 1);
const pwdShowOld = computed(() => pwdIsSelf.value && !pwdIsSuper.value);
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

function resetAccountFilter() {
  keyword.value = "";
  typeId.value = undefined;
  status.value = undefined;
  page.value = 1;
  jumpPage.value = null;
  loadAccounts();
}

function goToPage() {
  const maxPage = Math.max(1, Math.ceil(total.value / size));
  let p = Number(jumpPage.value);
  if (!Number.isFinite(p) || p < 1) p = 1;
  if (p > maxPage) p = maxPage;
  if (p === page.value) return;
  page.value = p;
  jumpPage.value = null;
  loadAccounts();
}

async function exportAccounts() {
  exporting.value = true;
  try {
    await api.exportAccounts({ keyword: keyword.value || undefined, type_id: typeId.value, status: status.value });
    notice.value = "账号已导出为 CSV 文件";
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    exporting.value = false;
  }
}

const menuGroups = computed(() => {
  const menus = permissions.value.filter((item) => item.perm_type === 1);
  return menus.map((menu) => ({
    menu,
    children: permissions.value.filter((item) => item.parent_id === menu.perm_id),
  }));
});

function openChangePwd(item: AccountItem) {
  pwdAccount.value = item;
  pwdForm.old_password = "";
  pwdForm.new_password = "";
  pwdForm.confirm_password = "";
  showChangePwd.value = true;
}

async function submitChangePwd() {
  if (!pwdAccount.value) return;
  if (!pwdForm.new_password || pwdForm.new_password.length < 6) {
    errorText.value = "新密码至少 6 个字符";
    return;
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    errorText.value = "两次输入的新密码不一致";
    return;
  }
  pwdSubmitting.value = true;
  try {
    await api.changeAccountPassword(pwdAccount.value.account_id, {
      old_password: pwdShowOld.value ? pwdForm.old_password : undefined,
      new_password: pwdForm.new_password,
    });
    notice.value = `账号「${pwdAccount.value.login_name}」密码已修改`;
    showChangePwd.value = false;
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    pwdSubmitting.value = false;
  }
}

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
        <button @click="resetAccountFilter">重置</button>
        <button :disabled="exporting" @click="exportAccounts">{{ exporting ? "导出中..." : "导出 CSV" }}</button>
      </div>
      <div class="table full">
        <div class="table-head"><span>登录名</span><span>密码</span><span>姓名 / 部门</span><span>角色</span><span>电话</span><span>最近登录</span><span>状态</span><span>操作</span></div>
        <div v-if="loading" class="table-row"><span>加载中...</span></div>
        <div v-else-if="!accounts.length" class="table-row"><span>暂无符合条件的账号</span></div>
        <div v-for="item in accounts" :key="item.account_id" class="table-row">
          <span><b>{{ item.login_name }}</b></span>
          <span><span style="font-family:Menlo,Consolas,monospace;color:#25364d;font-size:12px;background:#f6f9fc;padding:2px 8px;border-radius:3px;border:1px solid #eef2f8;">{{ item.password || "—" }}</span></span>
          <span>{{ item.real_name }}<br /><small>{{ item.dept || "—" }}</small></span>
          <span>{{ item.type_name }}</span>
          <span><small>{{ item.phone || "—" }}</small></span>
          <span><small>{{ item.last_login_time || "从未登录" }}</small></span>
          <span :class="item.status === 1 ? 'success' : 'danger'">● {{ item.status === 1 ? "启用" : "停用" }}</span>
          <span>
            <template v-if="item.account_id !== 1 && item.account_id !== auth.accountId">
              <button v-if="item.status === 1" class="btn-sm btn-ignore" :disabled="submitting" @click="toggleStatus(item)">停用</button>
              <button v-else class="btn-sm btn-confirm" :disabled="submitting" @click="toggleStatus(item)">启用</button>
              <button class="btn-sm btn-assign" @click="openChangePwd(item)">修改密码</button>
              <button v-if="auth.typeId === 1" class="btn-sm btn-ignore" @click="openPermissions(item)">权限</button>
              <button v-if="auth.typeId === 1" class="btn-sm btn-ignore" :disabled="submitting" @click="deleteAccount(item)">删除</button>
            </template>
            <button v-else class="btn-sm btn-assign" @click="openChangePwd(item)">修改密码</button>
          </span>
        </div>
      </div>
      <div class="pager">
        <span>共 {{ total }} 条</span>
        <button :disabled="page <= 1" @click="page--; loadAccounts()">上一页</button>
        <span>第 {{ page }} 页 / 共 {{ Math.max(1, Math.ceil(total / size)) }} 页</span>
        <button :disabled="page * size >= total" @click="page++; loadAccounts()">下一页</button>
        <span style="margin-left: 8px">跳转到</span>
        <input v-model.number="jumpPage" type="number" min="1" :max="Math.max(1, Math.ceil(total / size))" style="width: 64px; height: 32px; line-height: 30px; padding: 0; text-align: center; border: 1px solid #dbe3ed; border-radius: 4px; flex-shrink: 0;" @keyup.enter="goToPage" />
        <span>页</span>
        <button @click="goToPage" :disabled="!jumpPage">GO</button>
      </div>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal wide">
        <button class="close" @click="showCreate = false">×</button>
        <h2>新增账号</h2>
        <div class="form-grid">
          <div class="form-cell">
            <label>登录名</label>
            <input v-model="form.login_name" placeholder="登录用户名，全局唯一" />
          </div>
          <div class="form-cell">
            <label>初始密码</label>
            <input v-model="form.password" type="password" placeholder="Mock 阶段明文存储" />
          </div>
          <div class="form-cell">
            <label>姓名</label>
            <input v-model="form.real_name" />
          </div>
          <div class="form-cell">
            <label>角色</label>
            <select v-model="form.type_id" class="role-select">
              <option v-for="item in enums?.roles || []" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </div>
          <div class="form-cell">
            <label>部门（可选）</label>
            <input v-model="form.dept" />
          </div>
          <div class="form-cell">
            <label>电话（可选）</label>
            <input v-model="form.phone" />
          </div>
        </div>
        <div class="form-actions">
          <button @click="showCreate = false">取消</button>
          <button class="primary" :disabled="submitting" @click="submitCreate">确认创建</button>
        </div>
      </div>
    </div>

    <div v-if="showChangePwd" class="modal-mask" @click.self="showChangePwd = false">
      <div class="modal wide">
        <button class="close" @click="showChangePwd = false">×</button>
        <h2>修改密码 - {{ pwdAccount?.login_name }}</h2>
        <div class="form-grid">
          <div v-if="pwdShowOld" class="form-cell full">
            <label>原密码</label>
            <input v-model="pwdForm.old_password" type="password" placeholder="请输入当前密码" />
          </div>
          <div class="form-cell">
            <label>新密码</label>
            <input v-model="pwdForm.new_password" type="password" placeholder="至少 6 个字符" />
          </div>
          <div class="form-cell">
            <label>确认新密码</label>
            <input v-model="pwdForm.confirm_password" type="password" placeholder="再次输入新密码" />
          </div>
        </div>
        <div class="form-actions">
          <button @click="showChangePwd = false">取消</button>
          <button class="primary" :disabled="pwdSubmitting" @click="submitChangePwd">{{ pwdSubmitting ? "提交中..." : "确认修改" }}</button>
        </div>
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
<style scoped>
.modal.wide { width: 640px; max-width: 92%; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; margin: 16px 0; }
.form-cell { display: flex; flex-direction: column; gap: 4px; }
.form-cell label { font-size: 12px; color: var(--text-secondary); }
.form-cell input, .form-cell select { width: 100%; padding: 8px 10px; border: 1px solid #dbe3ed; border-radius: 5px; font-size: 13px; color: #35465e; box-sizing: border-box; outline: 0; }
.form-cell input:focus, .form-cell select:focus { border-color: #3788e8; }
.form-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 8px; border-top: 1px solid #eef2f8; }
.form-actions .primary { height: 36px; padding: 0 18px; font-size: 13px; color: #fff; background: #3788e8; border-radius: 5px; }
.form-actions button:not(.primary) { height: 36px; padding: 0 14px; font-size: 13px; border: 1px solid #dbe3ed; border-radius: 5px; background: #fff; color: #65748a; }
</style>
