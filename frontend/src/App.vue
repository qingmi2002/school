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
            {{ versionInfo?.has_update ? `新版本 ${versionInfo.latest_version}` : (versionInfo?.current_version || "v2.0.1") }}
          </el-button>
        </el-badge>
        <span class="user-info">{{ currentUser.real_name }}（{{ currentUser.role_label }}）</span>
        <el-button size="small" link style="color: #cbd5e1" @click="pwdDialogVisible = true">改密</el-button>
        <el-button size="small" link style="color: #fca5a5" @click="handleLogout">退出</el-button>
      </div>
    </el-header>

    <el-container class="erp-body">
      <el-aside width="196px" class="erp-aside">
        <el-menu :default-active="activeMenu" class="erp-menu" @select="(idx: string) => (activeMenu = idx)">
          <template v-if="isAdminRole">
            <el-menu-item index="workbench">排课工作台</el-menu-item>
            <el-menu-item index="master-dash">总课表看板</el-menu-item>
            <el-menu-item index="curriculum">课程与开课</el-menu-item>
            <el-menu-item index="teachers">教师管理</el-menu-item>
            <el-menu-item index="students">学生管理</el-menu-item>
            <el-menu-item index="cohorts">班级管理</el-menu-item>
            <el-menu-item index="classrooms">教室管理</el-menu-item>
            <el-menu-item index="labs">机房管理</el-menu-item>
            <el-menu-item index="rules">周期与规则</el-menu-item>
            <el-menu-item index="org">组织管理</el-menu-item>
            <el-menu-item v-if="currentUser.role_code === 'SUPER_ADMIN'" index="settings">系统设置</el-menu-item>
          </template>
          <template v-else-if="currentUser.role_code === 'TEACHING_LEAD' || (currentUser.managed_nodes && currentUser.managed_nodes.length > 0)">
            <el-menu-item index="my-overview">我的工作台</el-menu-item>
            <el-menu-item index="my-schedule">我的课表</el-menu-item>
            <el-menu-item index="teacher-grid">禁排填报</el-menu-item>
            <el-menu-item index="curriculum">课程与开课</el-menu-item>
            <el-menu-item index="teachers">本组教师</el-menu-item>
            <el-menu-item index="workbench">排课工作台</el-menu-item>
            <el-menu-item index="free-rooms">空教室查询</el-menu-item>
          </template>
          <template v-else-if="currentUser.role_code === 'TEACHER'">
            <el-menu-item index="my-overview">我的工作台</el-menu-item>
            <el-menu-item index="my-schedule">我的课表</el-menu-item>
            <el-menu-item index="teacher-grid">禁排填报</el-menu-item>
            <el-menu-item index="free-rooms">空教室查询</el-menu-item>
          </template>
          <template v-else>
            <el-menu-item index="my-overview">我的学业概览</el-menu-item>
            <el-menu-item index="my-schedule">我的课表</el-menu-item>
            <el-menu-item index="free-rooms">空教室自习</el-menu-item>
          </template>
        </el-menu>
      </el-aside>

      <el-main class="erp-main">
        <ScheduleWorkbench v-if="activeMenu === 'workbench'" />
        <MasterTimetableDashboard v-else-if="activeMenu === 'master-dash'" />
        <CurriculumTaskView v-else-if="activeMenu === 'curriculum'" />
        <TeacherManageView v-else-if="activeMenu === 'teachers'" />
        <StudentManageView v-else-if="activeMenu === 'students'" />
        <CohortManageView v-else-if="activeMenu === 'cohorts'" />
        <ClassroomManageView v-else-if="activeMenu === 'classrooms'" />
        <RoomRuleManager v-else-if="activeMenu === 'labs'" />
        <CycleAndRuleView v-else-if="activeMenu === 'rules'" />
        <div v-else-if="activeMenu === 'org'" class="org-split">
          <el-card shadow="never" style="width: 240px; flex-shrink: 0">
            <div style="font-weight: 600; font-size: 13px; margin-bottom: 8px">多级组织架构树</div>
            <el-tree
              :data="orgTree"
              node-key="id"
              default-expand-all
              highlight-current
              :props="{ label: 'node_name', children: 'children' }"
              @node-click="(n: OrgNodeTreeItem) => (selectedNode = n)"
            />
          </el-card>
          <div style="flex: 1; min-width: 0">
            <OrgPermissionView
              :selected-node="selectedNode"
              :can-edit="currentUser.role_code === 'SUPER_ADMIN'"
              @tree-changed="reloadOrgTree"
            />
          </div>
        </div>
        <SystemSettingView v-else-if="activeMenu === 'settings'" @updated="(n: string) => (siteName = n)" />
        <PersonalOverviewView v-else-if="activeMenu === 'my-overview'" @navigate="(m: string) => (activeMenu = m)" />
        <PersonalScheduleView v-else-if="activeMenu === 'my-schedule'" />
        <TeacherUnavailableGrid v-else-if="activeMenu === 'teacher-grid'" />
        <FreeRoomView v-else-if="activeMenu === 'free-rooms'" />
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

    <el-dialog v-model="pwdDialogVisible" title="修改个人密码" width="380px">
      <el-form label-width="76px" size="small">
        <el-form-item label="原密码"><el-input v-model="pwdForm.oldPwd" type="password" show-password /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="pwdForm.newPwd" type="password" show-password placeholder="至少 6 位" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="pwdDialogVisible = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleChangePwd">保存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  changeMyPassword,
  fetchMeApi,
  fetchOrgTree,
  fetchSystemVersion,
  type OrgNodeTreeItem,
  type UserProfile,
  type VersionInfo,
} from "./api/client";
import { getSiteConfig } from "./api/resources";
import ClassroomManageView from "./components/ClassroomManageView.vue";
import CohortManageView from "./components/CohortManageView.vue";
import CurriculumTaskView from "./components/CurriculumTaskView.vue";
import CycleAndRuleView from "./components/CycleAndRuleView.vue";
import FreeRoomView from "./components/FreeRoomView.vue";
import LoginView from "./components/LoginView.vue";
import MasterTimetableDashboard from "./components/MasterTimetableDashboard.vue";
import OrgPermissionView from "./components/OrgPermissionView.vue";
import PersonalOverviewView from "./components/PersonalOverviewView.vue";
import PersonalScheduleView from "./components/PersonalScheduleView.vue";
import RoomRuleManager from "./components/RoomRuleManager.vue";
import ScheduleWorkbench from "./components/ScheduleWorkbench.vue";
import StudentManageView from "./components/StudentManageView.vue";
import SystemSettingView from "./components/SystemSettingView.vue";
import TeacherManageView from "./components/TeacherManageView.vue";
import TeacherUnavailableGrid from "./components/TeacherUnavailableGrid.vue";

const siteName = ref("智能排课系统");
const currentUser = ref<UserProfile | null>(null);
const activeMenu = ref("workbench");
const orgTree = ref<OrgNodeTreeItem[]>([]);
const selectedNode = ref<OrgNodeTreeItem | null>(null);
const versionInfo = ref<VersionInfo | null>(null);
const upgradeDialogVisible = ref(false);
const pwdDialogVisible = ref(false);
const pwdForm = reactive({ oldPwd: "", newPwd: "" });

const isAdminRole = computed(() =>
  Boolean(currentUser.value && ["SUPER_ADMIN", "COLLEGE_SCHEDULER", "DEPT_SCHEDULER", "MAJOR_SCHEDULER", "LAB_ADMIN"].includes(currentUser.value.role_code))
);

async function reloadOrgTree() {
  try {
    orgTree.value = await fetchOrgTree();
    if (!selectedNode.value && orgTree.value.length) selectedNode.value = orgTree.value[0];
  } catch {
    orgTree.value = [];
  }
}

async function checkUpdate(force = false) {
  try {
    versionInfo.value = await fetchSystemVersion(force);
  } catch {
    // ignore offline
  }
}

async function onLoggedIn(user: UserProfile) {
  currentUser.value = user;
  activeMenu.value = isAdminRole.value ? "workbench" : "my-overview";
  await reloadOrgTree();
  await checkUpdate();
}

function handleLogout() {
  localStorage.removeItem("ss_token");
  currentUser.value = null;
}

async function handleChangePwd() {
  if (pwdForm.newPwd.length < 6) {
    ElMessage.warning("新密码至少 6 位");
    return;
  }
  try {
    await changeMyPassword(pwdForm.oldPwd, pwdForm.newPwd);
    ElMessage.success("密码修改成功");
    pwdDialogVisible.value = false;
    pwdForm.oldPwd = "";
    pwdForm.newPwd = "";
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "原密码错误或修改失败");
  }
}

onMounted(async () => {
  try {
    const cfg = await getSiteConfig();
    if (cfg?.site_name) siteName.value = cfg.site_name;
  } catch {
    // ignore
  }
  if (localStorage.getItem("ss_token")) {
    try {
      const me = await fetchMeApi();
      await onLoggedIn(me);
    } catch {
      localStorage.removeItem("ss_token");
    }
  }
});
</script>

<style scoped>
.erp-shell { height: 100vh; display: flex; flex-direction: column; }
.erp-header { background: #1e293b; color: #f8fafc; display: flex; justify-content: space-between; align-items: center; padding: 0 16px; }
.h-left { display: flex; align-items: center; gap: 10px; }
.sys-name { font-weight: 700; font-size: 15px; }
.divider { color: #64748b; }
.node-tag { font-size: 13px; color: #93c5fd; }
.h-right { display: flex; align-items: center; gap: 12px; }
.user-info { font-size: 13px; color: #e2e8f0; }
.erp-body { flex: 1; min-height: 0; }
.erp-aside { background: #ffffff; border-right: 1px solid #e2e8f0; overflow-y: auto; }
.erp-menu { border-right: none; }
.erp-main { background: #f1f5f9; padding: 14px; overflow-y: auto; }
.org-split { display: flex; gap: 12px; align-items: flex-start; }
</style>
