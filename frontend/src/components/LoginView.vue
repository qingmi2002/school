<template>
  <div class="login-wrap">
    <div class="login-box">
      <div class="login-head">
        <h1>{{ siteConfig.site_name }}</h1>
        <p>{{ siteConfig.site_subtitle }}</p>
      </div>

      <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="账号（工号 / 学号）">
          <el-input v-model="form.username" placeholder="请输入账号" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" size="large" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleLogin">
          登 录
        </el-button>
      </el-form>

      <div v-if="siteConfig.show_demo_accounts" class="demo-bar">
        <div class="demo-tip">快捷体验（密码 123456，可在系统设置中关闭）</div>
        <div class="demo-grid">
          <el-button v-for="acc in demoAccounts" :key="acc.u" size="small" plain @click="quickLogin(acc.u)">
            {{ acc.label }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { loginApi, type UserProfile } from "../api/client";
import { getSiteConfig, type SiteConfig } from "../api/resources";

const emit = defineEmits<{ (e: "logged-in", user: UserProfile): void }>();

const siteConfig = ref<SiteConfig>({
  site_name: "智能排课系统",
  site_subtitle: "高校与院系分级智能排课管理平台",
  show_demo_accounts: true,
});

const form = reactive({ username: "admin", password: "123456" });
const loading = ref(false);

const demoAccounts = [
  { label: "校级管理", u: "admin" },
  { label: "院级排课", u: "college_admin" },
  { label: "系级排课", u: "dept_admin" },
  { label: "专业排课", u: "major_admin" },
  { label: "教师端", u: "T1001" },
  { label: "学生端", u: "S202401" },
];

async function handleLogin(): Promise<void> {
  if (!form.username || !form.password) {
    ElMessage.warning("请输入账号和密码");
    return;
  }
  loading.value = true;
  try {
    const res = await loginApi(form.username, form.password);
    localStorage.setItem("ss_token", res.access_token);
    emit("logged-in", res.user);
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "登录失败";
    ElMessage.error(msg);
  } finally {
    loading.value = false;
  }
}

function quickLogin(u: string): void {
  form.username = u;
  form.password = "123456";
  void handleLogin();
}

onMounted(async () => {
  try {
    siteConfig.value = await getSiteConfig();
  } catch {
    // 保留默认标题
  }
});
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
  padding: 20px;
}
.login-box {
  width: 100%;
  max-width: 400px;
  background: #ffffff;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 32px 28px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}
.login-head { text-align: center; margin-bottom: 24px; }
.login-head h1 { margin: 0; font-size: 22px; color: #1f2937; font-weight: 600; }
.login-head p { margin: 6px 0 0; font-size: 13px; color: #6b7280; }
.demo-bar { margin-top: 20px; padding-top: 14px; border-top: 1px solid #ebeef5; }
.demo-tip { font-size: 12px; color: #909399; margin-bottom: 8px; text-align: center; }
.demo-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.demo-grid .el-button { margin-left: 0; }
</style>
