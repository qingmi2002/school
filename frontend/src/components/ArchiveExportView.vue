<template>
  <div class="stack">
    <!-- 集中导入中心（6-Sheet 一键入库） -->
    <el-card shadow="never">
      <template #header>
        <div class="head-row">
          <span>基础数据集中导入（6 合 1 Excel 一键入库）</span>
          <el-button type="primary" plain size="small" @click="openUrl('/api/v1/resources/master-import/template')">
            下载《基础数据集中导入模板.xlsx》
          </el-button>
        </div>
      </template>
      <div class="import-desc">
        一个 Excel 包含 6 个工作表：<code>1_组织机构</code>、<code>2_教学楼</code>、<code>3_教室</code>、<code>4_班级</code>、<code>5_教师</code>、<code>6_学生</code>，上传后按依赖顺序自动写入数据库（同编码幂等更新）。
      </div>
      <div class="upload-row">
        <input ref="fileInput" type="file" accept=".xlsx" @change="onFilePicked" />
        <el-button type="primary" size="small" :loading="uploading" :disabled="!pickedFile" @click="handleMasterUpload">
          一键集中导入数据库
        </el-button>
      </div>

      <div v-if="importReport" class="report-box">
        <el-alert
          :title="`导入完成：新增 ${importReport.total_inserted} 条，更新 ${importReport.total_updated} 条，异常 ${importReport.total_errors} 条`"
          :type="importReport.total_errors === 0 ? 'success' : 'warning'"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
        <el-table :data="reportRows" border size="small">
          <el-table-column prop="sheet" label="数据表" width="140" />
          <el-table-column prop="inserted" label="新增" width="80" />
          <el-table-column prop="updated" label="更新" width="80" />
          <el-table-column prop="errorText" label="异常提示" />
        </el-table>
      </div>
    </el-card>

    <!-- 教务回填导出与云盘归档 -->
    <el-card shadow="never">
      <template #header>
        <span style="font-weight: 600">课表导出、教务回填与云盘归档</span>
      </template>
      <div class="export-grid">
        <div class="ex-item">
          <div class="ex-title">教务系统标准回填</div>
          <div class="btn-row">
            <el-button type="primary" size="small" @click="openUrl('/api/v1/export/plans/1/edu-backfill?vendor=ZHENGFANG')">正方模板</el-button>
            <el-button type="primary" plain size="small" @click="openUrl('/api/v1/export/plans/1/edu-backfill?vendor=QINGGUO')">青果模板</el-button>
            <el-button type="primary" plain size="small" @click="openUrl('/api/v1/export/plans/1/edu-backfill?vendor=QIANGZHI')">强智模板</el-button>
          </div>
        </div>
        <div class="ex-item">
          <div class="ex-title">课表报表与云盘归档</div>
          <div class="btn-row">
            <el-button size="small" @click="openUrl('/api/v1/export/plans/1/multi-view')">多维度总课表</el-button>
            <el-button size="small" @click="openUrl('/api/v1/export/plans/1/report.pdf')">自检报告 PDF</el-button>
            <el-button size="small" @click="openUrl('/api/v1/export/plans/1/calendar.ics')">日历 (.ics)</el-button>
            <el-button type="success" size="small" :loading="archiving" @click="handleArchive">归档至云盘/NAS</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { triggerArchivePlan } from "../api/client";
import { uploadMasterImport, type MasterImportReport } from "../api/resources";

const emit = defineEmits<{ (e: "data-imported"): void }>();

const pickedFile = ref<File | null>(null);
const uploading = ref(false);
const archiving = ref(false);
const importReport = ref<MasterImportReport | null>(null);

const reportRows = computed(() => {
  if (!importReport.value) return [];
  return Object.entries(importReport.value.sheets).map(([sheet, v]) => ({
    sheet,
    inserted: v.inserted,
    updated: v.updated,
    errorText: v.errors.length ? v.errors.join("；") : "全部正常",
  }));
});

function openUrl(url: string): void {
  window.open(url, "_blank");
}

function onFilePicked(ev: Event): void {
  const input = ev.target as HTMLInputElement;
  pickedFile.value = input.files?.[0] || null;
}

async function handleMasterUpload(): Promise<void> {
  if (!pickedFile.value) return;
  uploading.value = true;
  try {
    importReport.value = await uploadMasterImport(pickedFile.value);
    ElMessage.success("集中导入执行完毕");
    emit("data-imported");
  } catch {
    ElMessage.error("集中导入失败，请核对模板格式");
  } finally {
    uploading.value = false;
  }
}

async function handleArchive(): Promise<void> {
  archiving.value = true;
  try {
    const res = await triggerArchivePlan(1, "ZHENGFANG");
    ElMessage.success(`归档完成（状态：${res.status}）`);
  } catch {
    ElMessage.error("归档失败");
  } finally {
    archiving.value = false;
  }
}
</script>

<style scoped>
.stack { display: flex; flex-direction: column; gap: 12px; }
.head-row { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 14px; }
.import-desc { font-size: 12px; color: #606266; margin-bottom: 10px; }
.upload-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.report-box { margin-top: 12px; }
.export-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.ex-item { border: 1px solid #ebeef5; border-radius: 6px; padding: 12px; background: #fafafa; }
.ex-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.btn-row { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
