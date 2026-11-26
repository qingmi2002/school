<template>
  <LoginView v-if="!currentUser" @logged-in="onLoggedIn" />

  <el-container v-else class="layout-root">
    <!-- 左侧专业深色导航 + 组织架构树 -->
    <el-aside width="268px" class="sidebar">
      <div class="sidebar-logo">
        <div class="logo-title">高校智能排课系统</div>
        <div class="logo-sub">{{ currentUser.role_label }}</div>
      </div>

      <div class="menu-section-title">功能导航</div>
      <el-menu
        :default-active="activeMenu"
        background-color="#0f172a"
        text-color="#cbd5e1"
        active-text-color="#60a5fa"
        class="side-menu"
        @select="handleMenuSelect"
      >
        <template v-if="isAdminRole">
          <el-menu-item index="workbench">📅 二维课表拖拽工作台</el-menu-item>
          <el-menu-item index="org">🏛️ 组织架构与分级权限</el-menu-item>
          <el-menu-item index="rooms">🖥️ 机房标签与黑白名单</el-menu-item>
          <el-menu-item index="export">📦 教务导出与云盘归档</el-menu-item>
          <el-menu-item index="teacher-grid">📝 教师禁排网格(预览)</el-menu-item>
        </template>

        <template v-else-if="currentUser.role_code === 'TEACHER'">
          <el-menu-item index="my-schedule">📅 我的个人教学课表</el-menu-item>
          <el-menu-item index="teacher-grid">📝 禁排时间填报 (5×5)</el-menu-item>
        </template>

        <template v-else>
          <el-menu-item index="my-schedule">🎓 我的班级学期课表</el-menu-item>
        </template>
      </el-menu>

      <!-- 管理员专属：左侧多级组织架构树 -->
      <div v-if="isAdminRole" class="tree-box">
        <div class="menu-section-title">组织架构树（按权限范围）</div>
        <el-tree
          :data="orgTree"
          node-key="id"
          default-expand-all
          highlight-current
          :props="{ label: 'node_name', children: 'children' }"
          class="dark-tree"
          @node-click="onTreeNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node-row">
              <span>{{ data.node_name }}</span>
              <span class="tree-badge">{{ nodeTypeLabel(data.node_type_code) }}</span>
            </span>
          </template>
        </el-tree>
      </div>
    </el-aside>

    <!-- 右侧主工作区 -->
    <el-container class="right-shell">
      <el-header class="top-header">
        <div class="header-left">
          <span class="crumb-main">{{ currentMenuTitle }}</span>
          <el-tag v-if="selectedNode" size="small" effect="plain" type="primary">
            当前节点：{{ selectedNode.node_name }}
          </el-tag>
        </div>

        <div class="header-right">
          <el-badge :is-dot="Boolean(versionInfo?.has_update)">
            <el-button
              size="small"
              :type="versionInfo?.has_update ? 'warning' : 'default'"
              @click="upgradeDialogVisible = true"
            >
              {{ versionInfo?.has_update ? `发现新版本 ${versionInfo.latest_version}` : (versionInfo?.current_version || "v1.1.0") }}
            </el-button>
          </el-badge>

          <el-tag type="info" effect="light">
            {{ currentUser.real_name }} · {{ currentUser.org_node_name }}
          </el-tag>
          <el-button size="small" type="danger" plain @click="handleLogout">切换账号</el-button>
        </div>
      </el-header>

      <el-main class="workspace-main">
        <ScheduleWorkbench v-if="activeMenu === 'workbench'" />
        <OrgPermissionView
          v-else-if="activeMenu === 'org'"
          :selected-node="selectedNode"
          :can-edit="currentUser.role_code === 'SUPER_ADMIN'"
        />
        <RoomRuleManager v-else-if="activeMenu === 'rooms'" />
        <ArchiveExportView v-else-if="activeMenu === 'export'" />
        <TeacherUnavailableGrid v-else-if="activeMenu === 'teacher-grid'" />
        <PersonalScheduleView v-else-if="activeMenu === 'my-schedule'" />
      </el-main>
    </el-container>

    <!-- 手动确认升级弹窗 -->
    <el-dialog v-model="upgradeDialogVisible" title="版本检测与手动确认升级" width="560px">
      <div v-if="versionInfo" class="upgrade-box">
        <el-alert
          :title="versionInfo.has_update ? `检测到新版本 ${versionInfo.latest_version}` : `当前版本 ${versionInfo.current_version} 已是最新`"
          :type="versionInfo.has_update ? 'warning' : 'success'"
          :description="versionInfo.release_notes"
          show-icon
          :closable="false"
        />
        <div class="sec-label">Linux 服务器手动升级命令（先自动热备数据库）：</div>
        <el-input :model-value="versionInfo.linux_upgrade_cmd" readonly size="small" />
        <div class="sec-label">NAS 手动升级指引：</div>
        <div class="nas-tip">{{ versionInfo.nas_upgrade_tip }}</div>
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
import LoginView from "./components/LoginView.vue";
import ScheduleWorkbench from "./components/ScheduleWorkbench.vue";
import OrgPermissionView from "./components/OrgPermissionView.vue";
import RoomRuleManager from "./components/RoomRuleManager.vue";
import ArchiveExportView from "./components/ArchiveExportView.vue";
import TeacherUnavailableGrid from "./components/TeacherUnavailableGrid.vue";
import PersonalScheduleView from "./components/PersonalScheduleView.vue";

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

const menuTitles: Record<string, string> = {
  workbench: "二维课表拖拽工作台",
  org: "组织架构与分级权限中心",
  rooms: "机房标签与黑白名单管控",
  export: "教务回填导出与云盘归档",
  "teacher-grid": "教师禁排时间填报 (5×5)",
  "my-schedule": "个人 / 班级课表查询",
};

const currentMenuTitle = computed(() => menuTitles[activeMenu.value] || "智能排课系统");

function nodeTypeLabel(code: string): string {
  const map: Record<string, string> = {
    SCHOOL: "校",
    CAMPUS: "校区",
    COLLEGE: "院",
    DEPT: "系",
    MAJOR: "专业",
    PUBLIC_DEPT: "公教",
    TRAINING_CENTER: "实训",
  };
  return map[code] || code;
}

function handleMenuSelect(index: string): void {
  activeMenu.value = index;
}

function onTreeNodeClick(node: OrgNodeTreeItem): void {
  selectedNode.value = node;
}

async function initAfterLogin(user: UserProfile): Promise<void> {
  currentUser.value = user;
  activeMenu.value = isAdminRole.value ? "workbench" : "my-schedule";
  if (isAdminRole.value) {
    try {
      const tree = await fetchOrgTree();
      orgTree.value = tree;
      if (tree[0]) selectedNode.value = tree[0];
    } catch {
      orgTree.value = [];
    }
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
    // 离线态静默忽略
  }
}

onMounted(async () => {
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
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif; }
</style>

<style scoped>
.layout-root { min-height: 100vh; }
.sidebar {
  background: #0f172a;
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #1e293b;
}
.sidebar-logo {
  padding: 20px 18px 16px;
  border-bottom: 1px solid #1e293b;
}
.logo-title { font-size: 16px; font-weight: 700; color: #f8fafc; }
.logo-sub { font-size: 12px; color: #60a5fa; margin-top: 4px; }
.menu-section-title {
  font-size: 11px;
  color: #64748b;
  padding: 14px 18px 6px;
  letter-spacing: 0.5px;
}
.side-menu { border-right: none; }
.tree-box {
  flex: 1;
  overflow-y: auto;
  border-top: 1px solid #1e293b;
  padding-bottom: 16px;
}
.dark-tree {
  background: transparent;
  color: #cbd5e1;
  padding: 0 8px;
}
:deep(.dark-tree .el-tree-node__content:hover) { background: #1e293b; }
:deep(.dark-tree .el-tree-node.is-current > .el-tree-node__content) { background: #1d4ed8; color: #ffffff; border-radius: 6px; }
.tree-node-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
  font-size: 13px;
}
.tree-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(148, 163, 184, 0.2);
  color: #93c5fd;
}
.right-shell { background: #f1f5f9; }
.top-header {
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.header-left, .header-right { display: flex; align-items: center; gap: 10px; }
.crumb-main { font-weight: 600; font-size: 15px; color: #0f172a; }
.workspace-main { padding: 16px; }
.upgrade-box { display: flex; flex-direction: column; gap: 10px; }
.sec-label { font-size: 13px; font-weight: 600; margin-top: 4px; }
.nas-tip { font-size: 12px; color: #475569; background: #f8fafc; padding: 10px; border-radius: 6px; border: 1px solid #e2e8f0; }
</style>
