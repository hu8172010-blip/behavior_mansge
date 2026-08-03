<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api, type EnumOption } from "../api";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();

const authMode = ref<"login" | "register">("login");
const username = ref("admin");
const password = ref("admin123");
const registerForm = ref({ name: "", username: "", password: "", confirmPassword: "", typeId: 0 });
const roleOptions = ref<EnumOption[]>([]);
const message = ref("");
const messageType = ref<"error" | "success">("error");
const submitting = ref(false);

onMounted(async () => {
  try {
    roleOptions.value = await api.registerRoles();
    if (roleOptions.value.length) registerForm.value.typeId = roleOptions.value[0].id;
  } catch {
    roleOptions.value = [];
  }
});

function showMessage(text: string, type: "error" | "success" = "error") {
  message.value = text;
  messageType.value = type;
}

async function login() {
  if (!username.value || !password.value) {
    showMessage("请输入用户名和密码");
    return;
  }
  submitting.value = true;
  try {
    await auth.login(username.value, password.value);
    router.push("/dashboard");
  } catch (error: any) {
    showMessage(error.message || "登录失败");
  } finally {
    submitting.value = false;
  }
}

async function register() {
  const form = registerForm.value;
  if (!form.name || !form.username || !form.password || !form.confirmPassword) {
    showMessage("请完整填写注册信息");
    return;
  }
  if (form.password !== form.confirmPassword) {
    showMessage("两次输入的密码不一致");
    return;
  }
  submitting.value = true;
  try {
    await api.register({ real_name: form.name, login_name: form.username, password: form.password, type_id: form.typeId });
    username.value = form.username;
    password.value = "";
    authMode.value = "login";
    showMessage("注册成功，请使用新账号登录", "success");
  } catch (error: any) {
    showMessage(error.message || "注册失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section class="login-page">
    <div class="login-brand"><span>观</span><div><b>智行观测</b><small>跨摄像头异常行为轨迹分析系统</small></div></div>
    <div class="login-layout">
      <div class="login-intro">
        <small>BEHAVIOR INSIGHT PLATFORM</small>
        <h1>让园区安全<br /><em>看得见、管得住</em></h1>
        <p>连接视频资源，洞察异常行为，构建跨摄像头的智能轨迹分析与告警处置体系。</p>
        <div class="login-tags"><i>多源视频接入</i><i>跨摄像头轨迹</i><i>AI 异常识别</i></div>
      </div>
      <div class="login-card">
        <div class="auth-tabs">
          <button :class="{ selected: authMode === 'login' }" @click="authMode = 'login'; message = ''">登录系统</button>
          <button :class="{ selected: authMode === 'register' }" @click="authMode = 'register'; message = ''">注册账号</button>
        </div>
        <template v-if="authMode === 'login'">
          <div class="card-kicker">统一身份认证</div>
          <h2>欢迎回来</h2>
          <p>登录您的行为管理工作台</p>
          <label>用户名</label>
          <input v-model="username" placeholder="请输入用户名" />
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入密码" @keyup.enter="login" />
          <div v-if="message" :class="messageType === 'error' ? 'error' : 'success'">{{ message }}</div>
          <button class="primary" :disabled="submitting" @click="login">{{ submitting ? "登录中..." : "登录系统" }}</button>
          <div class="demo-account">演示账号：admin　密码：admin123</div>
        </template>
        <template v-else>
          <div class="card-kicker">创建工作台账号</div>
          <h2>注册账号</h2>
          <p>请选择适合您的用户类型</p>
          <label>姓名</label>
          <input v-model="registerForm.name" placeholder="请输入真实姓名" />
          <label>用户名</label>
          <input v-model="registerForm.username" placeholder="设置登录用户名" />
          <label>密码</label>
          <input v-model="registerForm.password" type="password" placeholder="设置登录密码" />
          <label>确认密码</label>
          <input v-model="registerForm.confirmPassword" type="password" placeholder="再次输入密码" />
          <label>用户类型</label>
          <select v-model="registerForm.typeId" class="role-select">
            <option v-for="role in roleOptions" :key="role.id" :value="role.id">{{ role.name }}</option>
          </select>
          <div v-if="message" :class="messageType === 'error' ? 'error' : 'success'">{{ message }}</div>
          <button class="primary" :disabled="submitting" @click="register">{{ submitting ? "提交中..." : "注册账号" }}</button>
        </template>
      </div>
    </div>
  </section>
</template>
