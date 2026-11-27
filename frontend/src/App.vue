<template>
  <LoginView v-if="!currentUser" @logged-in="onLoggedIn" />

  <el-container v-else class="erp-shell">
    <el-header height="48px" class="erp-header">
      <div class="h-left">
        <span class="sys-name">{{ siteName }}</span>
        <span class="divider">|</span>
        <span class="node-tag">{{ selectedNode?.node_name || currentUser.org_node_name }}</span>
      </div>

      <div class="h-right">
        <el-badge :is-dot="Boolean(versionInfo?.has_update)">
          <el-button size="small" link style="color: #e2e8f0" @click="upgradeDialogVisible = true">
            {{ versionInfo?.has_update ? `新版本 ${versionInfo.latest_version}` : (versionInfo?.current_version || "v1.5.1") }}
          </el-button>
        </el-badge>
        <span class="user-info">{{ currentUser.real_name }}（{{ currentUser.role_label }}）</span>
        <el-button size="small" link style="color: #fca5a5" @click="handleLogout">退出</el-button>
      </div>
    </el-header>

    <el-container class="erp-body">
      <el-aside width="210px" class="erp-aside">
        <el-menu :default-active="activeMenu" class="erp-menu" @select="(idx: string) => (activeMenu = idx)">
          <template v-if="isAdminRole">
            <el-menu-item index="workbench">排课工作台</el-menu-item>
            <el-menu-item index="resources">基础数据</el-menu-item>
            <el-menu-item index="curriculum">课程与合班</el-menu-item>
            <el-menu-item index="teacher-grid">教师禁排</el-menu-item>
            <el-menu-item index="rules">周期与规则</el-menu-item>
            <el-menu-item index="org">组织权限</el-menu-item>
            <el-menu-item index="rooms">机房规则</el-menu-item>
            <el-menu-item index="export">导入导出</el-menu-item>
            <el-menu-item v-if="currentUser.role_code === 'SUPER_ADMIN'" index="settings">系统设置</el-menu-item>
          </template>
          <template v-else-if="currentUser.role_code === 'TEACHING_LEAD'">
            <el-menu-item index="my-schedule">我的课表</el-menu-item>
            <el-menu-item index="teacher-grid">本组禁排管理</el-menu-item>
            <el-menu-item index="curriculum">课程与合班</el-menu-item>
            <el-menu-item index="workbench">排课工作台</el-menu-item>
          </template>
          <template v-else-if="currentUser.role_code === 'TEACHER'">
            <el-menu-item index="my-schedule">我的课表</el-menu-item>
            <el-menu-item index="teacher-grid">禁排填报</el-menu-item>
          </template>
          <template v-else>
            <el-menu-item index="my-schedule">班级课表</el-menu-item>
          </template>
        </el-menu>

        <div v-if="isAdminRole" class="tree-panel">
          <div class="tree-title">组织架构</div>
          <el-tree
            :data="orgTree"
            node-key="id"
            default-expand-all
            highlight-current
            :props="{ label: 'node_name', children: 'children' }"
            @node-click="(n: OrgNodeTreeItem) => (selectedNode = n)"
          />
        </div>
      </el-aside>

      <el-main class="erp-main">
        <ScheduleWorkbench v-if="activeMenu === 'workbench'" />
        <ResourceManageView v-else-if="activeMenu === 'resources'" :active-org-id="selectedNode?.id || currentUser.org_node_id" />
        <CurriculumTaskView v-else-if="activeMenu === 'curriculum'" />
        <CycleAndRuleView v-else-if="activeMenu === 'rules'" />
        <OrgPermissionView
          v-else-if="activeMenu === 'org'"
          :selected-node="selectedNode"
          :can-edit="currentUser.role_code === 'SUPER_ADMIN'"
          @tree-changed="reloadOrgTree"
        />
        <RoomRuleManager v-else-if="activeMenu === 'rooms'" />
        <ArchiveExportView v-else-if="activeMenu === 'export'" @data-imported="reloadOrgTree" />
        <SystemSettingView v-else-if="activeMenu === 'settings'" @updated="(n: string) => (siteName = n)" />
        <TeacherUnavailableGrid v-else-if="activeMenu === 'teacher-grid'" />
        <PersonalScheduleView v-else-if="activeMenu === 'my-schedule'" />
      </el-main>
    </el-container>

    <el-dialog v-model="upgradeDialogVisible" title="版本检测与手动升级" width="520px">
      <div v-if="versionInfo" style="display: flex; flex-direction: column; gap: 10px">
        <el-alert
          :title="versionInfo.has_update ? `发现新版本 ${versionInfo.latest_version}` : `当前版本 ${versionInfo.current_version} 已是最新`"
          :type="versionInfo.has_update ? 'warning' : 'success'"
          :description="versionInfo.release_notes"
          show-icon
          :closable="false"
        />
        <el-input :model-value="versionInfo.linux_upgrade_cmd" readonly size="small" />
      </div>
      <template #footer>
        <el-button size="small" @click="checkUpdate(true)">重新检测</el-button>
        <el-button type="primary" size="small" @click="upgradeDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  fetchMeApi,
  fetchOrgTree,
  fetchSystemVersion,
  type OrgNodeTreeItem,
  type UserProfile,
  type VersionInfo,
} from "./api/client";
import { getSiteConfig } from "./api/resources";
import LoginView from "./components/LoginView.vue";
import ScheduleWorkbench from "./components/ScheduleWorkbench.vue";
import CurriculumTaskView from "./components/CurriculumTaskView.vue";
import ResourceManageView from "./components/ResourceManageView.vue";
import CycleAndRuleView from "./components/CycleAndRuleView.vue";
import OrgPermissionView from "./components/OrgPermissionView.vue";
import RoomRuleManager from "./components/RoomRuleManager.vue";
import ArchiveExportView from "./components/ArchiveExportView.vue";
import SystemSettingView from "./components/SystemSettingView.vue";
import TeacherUnavailableGrid from "./components/TeacherUnavailableGrid.vue";
import PersonalScheduleView from "./components/PersonalScheduleView.vue";

const siteName = ref("智能排课系统");
const currentUser = ref<UserProfile | null>(null);
const activeMenu = ref("workbench");
const orgTree = ref<OrgNodeTreeItem[]>([]);
const selectedNode = ref<OrgNodeTreeItem | null>(null);
const versionInfo = ref<VersionInfo | null>(null);
const upgradeDialogVisible = ref(false);

const isAdminRole = computed(() => {
  const r = currentUser.value?.role_code || "";
  return r === "SUPER_ADMIN" || r.includes("SCHEDULER") || r === "LAB_ADMIN";
});

async function reloadOrgTree(): Promise<void> {
  try {
    const tree = await fetchOrgTree();
    orgTree.value = tree;
    if (tree[0] && !selectedNode.value) selectedNode.value = tree[0];
  } catch {
    orgTree.value = [];
  }
}

async function initAfterLogin(user: UserProfile): Promise<void> {
  currentUser.value = user;
  activeMenu.value = isAdminRole.value ? "workbench" : "my-schedule";
  if (isAdminRole.value) {
    await reloadOrgTree();
  }
  void checkUpdate(false);
}

function onLoggedIn(user: UserProfile): void {
  void initAfterLogin(user);
}

function handleLogout(): void {
  localStorage.removeItem("ss_token");
  currentUser.value = null;
  orgTree.value = [];
  selectedNode.value = null;
}

async function checkUpdate(force = false): Promise<void> {
  try {
    versionInfo.value = await fetchSystemVersion(force);
  } catch {
    // 忽略
  }
}

onMounted(async () => {
  try {
    const cfg = await getSiteConfig();
    siteName.value = cfg.site_name;
  } catch {
    // 忽略
  }
  const token = localStorage.getItem("ss_token");
  if (token) {
    try {
      const me = await fetchMeApi();
      await initAfterLogin(me);
    } catch {
      localStorage.removeItem("ss_token");
    }
  }
});
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; }
</style>

<style scoped>
.erp-shell { min-height: 100vh; display: flex; flex-direction: column; }
.erp-header { background: #1e3a5f; color: #ffffff; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; }
.h-left, .h-right { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.sys-name { font-size: 15px; font-weight: 600; }
.divider { opacity: 0.4; }
.node-tag { font-size: 12px; color: #bfdbfe; }
.user-info { font-size: 12px; color: #e2e8f0; }
.erp-body { flex: 1; }
.erp-aside { background: #ffffff; border-right: 1px solid #dcdfe6; display: flex; flex-direction: column; }
.erp-menu { border-right: none; }
:deep(.erp-menu .el-menu-item) { height: 40px; line-height: 40px; font-size: 13px; }
.tree-panel { border-top: 1px solid #ebeef5; padding: 10px 8px; flex: 1; overflow-y: auto; }
.tree-title { font-size: 12px; font-weight: 600; color: #606266; padding: 0 8px 6px; }
.erp-main { padding: 12px; background: #f0f2f5; }
</style>
