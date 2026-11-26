<template>
  <el-card shadow="never" style="max-width: 620px">
    <template #header>
      <span style="font-weight: 600">系统定制设置（数据库保存，实时生效）</span>
    </template>
    <el-form :model="form" label-width="130px" size="small">
      <el-form-item label="自定义系统名称">
        <el-input v-model="form.site_name" placeholder="例如：XX大学智能排课系统" />
      </el-form-item>
      <el-form-item label="登录页通用副标题">
        <el-input v-model="form.site_subtitle" placeholder="简短介绍" />
      </el-form-item>
      <el-form-item label="登录页显示体验账号">
        <el-switch v-model="form.show_demo_accounts" />
        <span style="margin-left: 10px; font-size: 12px; color: #909399">正式上线发布时关闭即可</span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="handleSave">保存设置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { getSiteConfig, saveSiteConfig } from "../api/resources";

const emit = defineEmits<{ (e: "updated", name: string): void }>();

const form = reactive({
  site_name: "智能排课系统",
  site_subtitle: "高校与院系分级智能排课管理平台",
  show_demo_accounts: true,
});
const saving = ref(false);

async function handleSave(): Promise<void> {
  saving.value = true;
  try {
    const saved = await saveSiteConfig({ ...form });
    ElMessage.success("系统配置已保存");
    emit("updated", saved.site_name);
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    const cfg = await getSiteConfig();
    Object.assign(form, cfg);
  } catch {
    // 忽略
  }
});
</script>
