<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand">高校分级智能排课系统（多级通用版）</div>
      <div class="header-right">
        <el-badge :is-dot="Boolean(versionInfo?.has_update)">
          <el-button
            size="small"
            :type="versionInfo?.has_update ? 'warning' : 'default'"
            @click="upgradeDialogVisible = true"
          >
            {{ versionInfo?.has_update ? `发现新版本 ${versionInfo.latest_version}` : `当前版本 ${versionInfo?.current_version || 'v1.0.3'}` }}
          </el-button>
        </el-badge>
      </div>
    </el-header>

    <el-main class="app-main">
      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane label="二维课表拖拽工作台" name="workbench">
          <ScheduleWorkbench />
        </el-tab-pane>
        <el-tab-pane label="教师禁排填报 (H5)" name="teacher">
          <TeacherUnavailableGrid />
        </el-tab-pane>
        <el-tab-pane label="机房标签与黑白名单" name="rooms">
          <RoomRuleManager />
        </el-tab-pane>
      </el-tabs>
    </el-main>

    <el-dialog v-model="upgradeDialogVisible" title="版本检测与手动确认升级" width="580px">
      <div v-if="versionInfo" class="upgrade-box">
        <el-alert
          :title="versionInfo.has_update ? `检测到新版本 ${versionInfo.latest_version}（当前 ${versionInfo.current_version}）` : `当前版本 ${versionInfo.current_version} 已是最新`"
          :type="versionInfo.has_update ? 'warning' : 'success'"
          :description="versionInfo.release_notes"
          show-icon
          :closable="false"
        />
        <div class="upgrade-section">
          <div class="sec-label">Linux 服务器手动确认升级（升级前自动热备数据库）：</div>
          <el-input :model-value="versionInfo.linux_upgrade_cmd" readonly size="small">
            <template #append>
              <el-button @click="copyCmd(versionInfo.linux_upgrade_cmd)">复制命令</el-button>
            </template>
          </el-input>
        </div>
        <div class="upgrade-section">
          <div class="sec-label">NAS（群晖 / 飞牛 OS）手动确认升级：</div>
          <div class="nas-tip">{{ versionInfo.nas_upgrade_tip }}</div>
        </div>
      </div>
      <template #footer>
        <el-button size="small" :loading="checkingVersion" @click="checkUpdate(true)">重新检测</el-button>
        <el-button type="primary" size="small" @click="upgradeDialogVisible = false">知道了</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchSystemVersion, type VersionInfo } from "./api/client";
import ScheduleWorkbench from "./components/ScheduleWorkbench.vue";
import TeacherUnavailableGrid from "./components/TeacherUnavailableGrid.vue";
import RoomRuleManager from "./components/RoomRuleManager.vue";

const activeTab = ref("workbench");
const upgradeDialogVisible = ref(false);
const checkingVersion = ref(false);
const versionInfo = ref<VersionInfo | null>(null);

async function checkUpdate(force = false): Promise<void> {
  checkingVersion.value = true;
  try {
    versionInfo.value = await fetchSystemVersion(force);
    if (force) {
      ElMessage.info(
        versionInfo.value.has_update
          ? `发现新版本 ${versionInfo.value.latest_version}`
          : "当前已是最新版本"
      );
    }
  } catch {
    versionInfo.value = {
      current_version: "v1.0.3",
      latest_version: "v1.0.3",
      has_update: false,
      check_status: "OFFLINE",
      release_url: "https://github.com/qingmi2002/school/releases",
      release_notes: "离线演示模式",
      linux_upgrade_cmd: "cd /opt/smart-schedule && git pull && sudo bash deploy.sh --upgrade",
      nas_upgrade_tip: "在 NAS Docker 界面重新拉取 :latest 镜像后重启即可。",
    };
  } finally {
    checkingVersion.value = false;
  }
}

async function copyCmd(cmd: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(cmd);
    ElMessage.success("升级命令已复制");
  } catch {
    ElMessage.info("请手动选中输入框复制命令");
  }
}

onMounted(() => {
  void checkUpdate(false);
});
</script>

<style scoped>
.app-shell { min-height: 100vh; background: #f3f4f6; }
.app-header { display: flex; align-items: center; justify-content: space-between; background: #ffffff; border-bottom: 1px solid #e5e7eb; padding: 0 20px; }
.brand { font-weight: 600; font-size: 17px; color: #111827; }
.header-right { display: flex; align-items: center; gap: 10px; }
.app-main { max-width: 1280px; width: 100%; margin: 0 auto; padding: 16px; }
.upgrade-box { display: flex; flex-direction: column; gap: 14px; }
.sec-label { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #1f2937; }
.nas-tip { font-size: 12px; color: #4b5563; background: #f9fafb; padding: 10px; border-radius: 6px; border: 1px solid #e5e7eb; }
</style>
