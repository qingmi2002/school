<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">教务系统批量回填导出、PDF 自检报告与云盘版本化归档</div>
    </template>
    <div class="export-grid">
      <div class="ex-item">
        <div class="ex-title">1. 教务系统标准批量回填模板</div>
        <div class="ex-desc">零改造对接学校现有教务平台，导出标准格式 Excel：</div>
        <div class="btn-row">
          <el-button type="primary" size="small" @click="openUrl('/api/v1/export/plans/1/edu-backfill?vendor=ZHENGFANG')">正方教务模板</el-button>
          <el-button type="primary" plain size="small" @click="openUrl('/api/v1/export/plans/1/edu-backfill?vendor=QINGGUO')">青果教务模板</el-button>
          <el-button type="primary" plain size="small" @click="openUrl('/api/v1/export/plans/1/edu-backfill?vendor=QIANGZHI')">强智教务模板</el-button>
        </div>
      </div>

      <div class="ex-item">
        <div class="ex-title">2. 多维度总课表、PDF 报告与日历订阅</div>
        <div class="ex-desc">支持按班级/教师/机房 3-Sheet 导出与 RFC 5545 手机日历订阅：</div>
        <div class="btn-row">
          <el-button size="small" @click="openUrl('/api/v1/export/plans/1/multi-view')">多维度总课表 (.xlsx)</el-button>
          <el-button size="small" @click="openUrl('/api/v1/export/plans/1/report.pdf')">排课自检报告 (.pdf)</el-button>
          <el-button size="small" @click="openUrl('/api/v1/export/plans/1/calendar.ics')">全表日历 (.ics)</el-button>
        </div>
      </div>

      <div class="ex-item">
        <div class="ex-title">3. 云盘 / NAS 独立文件夹自动归档</div>
        <div class="ex-desc">按“学期 / 排课单元 / 版本+时间戳”自动建隔离目录留存全部 5 类产物：</div>
        <div class="btn-row">
          <el-button type="success" size="small" :loading="archiving" @click="handleArchive">
            立即执行一键归档至 NAS / 云盘
          </el-button>
        </div>
      </div>

      <div class="ex-item">
        <div class="ex-title">4. 双模式 Excel 导入标准模板下载</div>
        <div class="ex-desc">供各院系线下填写教学任务书或预排草稿后上传碰撞检测：</div>
        <div class="btn-row">
          <el-button size="small" @click="openUrl('/api/v1/import/template/TASK_ONLY')">下载《教学任务书模板.xlsx》</el-button>
          <el-button size="small" @click="openUrl('/api/v1/import/template/PRE_SCHEDULED')">下载《预排课表模板.xlsx》</el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { triggerArchivePlan } from "../api/client";

const archiving = ref(false);

function openUrl(url: string): void {
  window.open(url, "_blank");
}

async function handleArchive(): Promise<void> {
  archiving.value = true;
  try {
    const res = await triggerArchivePlan(1, "ZHENGFANG");
    ElMessage.success(`归档完成（状态：${res.status}），路径：${res.archive_path || res.staging_dir}`);
  } catch {
    ElMessage.error("归档请求失败，请检查后端服务状态");
  } finally {
    archiving.value = false;
  }
}
</script>

<style scoped>
.head { font-weight: 600; font-size: 15px; }
.export-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
.ex-item { border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; background: #f8fafc; }
.ex-title { font-weight: 600; font-size: 14px; color: #0f172a; margin-bottom: 6px; }
.ex-desc { font-size: 12px; color: #64748b; margin-bottom: 12px; }
.btn-row { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
