<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { api, type RoleItem } from "../api";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();

const roles = ref<RoleItem[]>([]);
const loading = ref(false);
const deleting = ref(false);
const submitting = ref(false);
const errorText = ref("");
const showCreate = ref(false);
const form = reactive({ type_name: "", type_desc: "" });

async function loadRoles() {
  loading.value = true;
  try {
    roles.value = await api.roles();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, { type_name: "", type_desc: "" });
  showCreate.value = true;
}

async function submitCreate() {
  if (!form.type_name.trim()) {
    errorText.value = "请输入角色名称";
    return;
  }
  submitting.value = true;
  try {
    await api.createRole({ type_name: form.type_name.trim(), type_desc: form.type_desc.trim() || undefined });
    showCreate.value = false;
    await loadRoles();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    submitting.value = false;
  }
}

async function deleteRole(role: RoleItem) {
  if (role.account_count > 0) {
    errorText.value = "该角色下存在账号，无法删除";
    return;
  }
  if (!confirm(`确定删除角色「${role.type_name}」吗？`)) return;
  deleting.value = true;
  try {
    await api.deleteRole(role.type_id);
    await loadRoles();
  } catch (error: any) {
    errorText.value = error.message;
  } finally {
    deleting.value = false;
  }
}

onMounted(loadRoles);
</script>

<template>
  <div>
    <div class="page-heading">
      <div><h2>角色管理</h2><p>预置角色总览，点击配置权限跳转权限管理</p></div>
      <div class="tabs">
        <button v-if="auth.typeId === 1" @click="openCreate">+ 新增角色</button>
      </div>
    </div>

    <div v-if="errorText" class="error" @click="errorText = ''">{{ errorText }}</div>
    <div v-if="loading">加载中...</div>

    <div v-else class="role-grid">
      <div v-for="role in roles" :key="role.type_id" class="panel role-card">
        <div class="role-head">
          <b>{{ role.type_name }}</b>
          <span v-if="role.is_super" class="role-super">内置</span>
        </div>
        <p>{{ role.type_desc || "—" }}</p>
        <div class="role-meta">
          <span>账号数 <b>{{ role.account_count }}</b></span>
          <span>权限项 <b>{{ role.is_super ? "全部" : role.perm_ids.length }}</b></span>
        </div>
        <button v-if="!role.is_super" class="btn-sm btn-assign" @click="router.push('/system/index?type_id=' + role.type_id)">配置权限</button>
        <button
          v-if="!role.is_super && auth.typeId === 1"
          class="btn-sm btn-ignore"
          :disabled="role.account_count > 0 || deleting"
          @click="deleteRole(role)"
        >
          删除
        </button>
        <small v-else style="color:#93a0b2">超级管理员默认放行全部权限，无需配置</small>
      </div>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal wide">
        <button class="close" @click="showCreate = false">×</button>
        <h2>新增角色</h2>
        <div class="form-grid">
          <div class="form-cell full">
            <label>角色名称</label>
            <input v-model="form.type_name" placeholder="如：实习生" />
          </div>
          <div class="form-cell full">
            <label>角色描述（可选）</label>
            <input v-model="form.type_desc" placeholder="简要说明该角色职责" />
          </div>
        </div>
        <div class="form-actions">
          <button @click="showCreate = false">取消</button>
          <button class="primary" :disabled="submitting" @click="submitCreate">确认创建</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* 角色弹窗：宽屏+两列布局 */
.modal.wide {
  width: 560px;
  max-width: 92%;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
  margin: 16px 0;
}
.form-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-cell.full {
  grid-column: 1 / -1;
}
.form-cell label {
  font-size: 12px;
  color: var(--text-secondary);
}
.form-cell input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #dbe3ed;
  border-radius: 5px;
  font-size: 13px;
  color: #35465e;
  box-sizing: border-box;
  outline: 0;
}
.form-cell input:focus {
  border-color: #3788e8;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid #eef2f8;
}
.form-actions .primary {
  height: 36px;
  padding: 0 18px;
  font-size: 13px;
  color: #fff;
  background: #3788e8;
  border-radius: 5px;
}
.form-actions button:not(.primary) {
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
  border: 1px solid #dbe3ed;
  border-radius: 5px;
  background: #fff;
  color: #65748a;
}
</style>
