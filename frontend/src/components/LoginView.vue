<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-hero">
        <div class="hero-badge">多级通用版 · V1.1</div>
        <h1>高校分级智能排课系统</h1>
        <p class="hero-desc">
          面向校级教务处、二级学院、教学系部及专业教研室的全流程智能排课平台。支持四级排课权限隔离、OR-Tools 确定性无冲突求解、教师自助禁排与学生班级课表查询。
        </p>
        <div class="hero-features">
          <div class="feat-item">✓ 校 / 院 / 系 / 专业四级独立与统筹排课</div>
          <div class="feat-item">✓ 教师专属个人课表与 5×5 禁排填报</div>
          <div class="feat-item">✓ 学生专属行政班课表与手机日历订阅</div>
        </div>
      </div>

      <div class="login-card">
        <h2>统一身份认证登录</h2>
        <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
          <el-form-item label="工号 / 学号 / 管理员账号">
            <el-input v-model="form.username" placeholder="请输入账号，如 admin / T1001 / S202401" size="large" />
          </el-form-item>
          <el-form-item label="登录密码">
            <el-input v-model="form.password" type="password" show-password placeholder="默认演示密码 123456" size="large" />
          </el-form-item>
          <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleLogin">
            登录系统
          </el-button>
        </el-form>

        <div class="quick-box">
          <div class="quick-title">快捷体验账号（统一密码 123456，点击自动填充）：</div>
          <div class="quick-grid">
            <button
              v-for="acc in demoAccounts"
              :key="acc.username"
              type="button"
              class="quick-btn"
              @click="fillAndLogin(acc.username)"
            >
              <span class="q-role">{{ acc.role }}</span>
              <span class="q-user">{{ acc.username }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { loginApi, type UserProfile } from "../api/client";

const emit = defineEmits<{
  (e: "logged-in", user: UserProfile): void;
}>();

const form = reactive({
  username: "admin",
  password: "123456",
});
const loading = ref(false);

const demoAccounts = [
  { role: "校级排课管理员", username: "admin" },
  { role: "院级排课管理员", username: "college_admin" },
  { role: "系级排课管理员", username: "dept_admin" },
  { role: "专业级排课管理员", username: "major_admin" },
  { role: "任课教师", username: "T1001" },
  { role: "在校学生", username: "S202401" },
];

async function handleLogin(): Promise<void> {
  if (!form.username || !form.password) {
    ElMessage.warning("请输入账号与密码");
    return;
  }
  loading.value = true;
  try {
    const res = await loginApi(form.username, form.password);
    localStorage.setItem("ss_token", res.access_token);
    ElMessage.success(`欢迎回来，${res.user.real_name}（${res.user.role_label}）`);
    emit("logged-in", res.user);
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "登录失败，请检查账号密码";
    ElMessage.error(msg);
  } finally {
    loading.value = false;
  }
}

function fillAndLogin(username: string): void {
  form.username = username;
  form.password = "123456";
  void handleLogin();
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #1d4ed8 100%);
  padding: 24px;
}
.login-container {
  max-width: 980px;
  width: 100%;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 25px 60px rgba(0, 0, 0, 0.35);
  background: #ffffff;
}
@media (max-width: 820px) {
  .login-container { grid-template-columns: 1fr; }
}
.login-hero {
  background: linear-gradient(160deg, #0f172a, #1e293b);
  color: #f8fafc;
  padding: 44px 36px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.hero-badge {
  display: inline-block;
  align-self: flex-start;
  background: rgba(59, 130, 246, 0.25);
  border: 1px solid rgba(96, 165, 250, 0.5);
  color: #93c5fd;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  margin-bottom: 16px;
}
.login-hero h1 { font-size: 28px; margin: 0 0 14px; line-height: 1.3; }
.hero-desc { font-size: 14px; color: #cbd5e1; line-height: 1.7; margin-bottom: 24px; }
.hero-features { display: flex; flex-direction: column; gap: 10px; font-size: 13px; color: #93c5fd; }
.login-card { padding: 40px 34px; }
.login-card h2 { margin: 0 0 22px; font-size: 20px; color: #0f172a; }
.quick-box { margin-top: 22px; padding-top: 16px; border-top: 1px solid #e5e7eb; }
.quick-title { font-size: 12px; color: #64748b; margin-bottom: 10px; }
.quick-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.quick-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  cursor: pointer;
  transition: all 0.15s;
}
.quick-btn:hover { border-color: #2563eb; background: #eff6ff; }
.q-role { font-size: 12px; font-weight: 600; color: #1e293b; }
.q-user { font-size: 11px; color: #64748b; }
</style>
