<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand">高校分级智能排课系统（多级通用版）</div>
      <el-tag type="success" effect="plain">M2 里程碑 · 约束采集端</el-tag>
    </el-header>
    <el-main class="app-main">
      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane label="教师禁排填报 (H5)" name="teacher">
          <TeacherUnavailableGrid />
        </el-tab-pane>
        <el-tab-pane label="机房标签与黑白名单" name="rooms">
          <RoomRuleManager />
        </el-tab-pane>
      </el-tabs>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from "vue";
import TeacherUnavailableGrid from "./components/TeacherUnavailableGrid.vue";
import RoomRuleManager from "./components/RoomRuleManager.vue";

const activeTab = ref("teacher");
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f3f4f6;
}
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  padding: 0 20px;
}
.brand {
  font-weight: 600;
  font-size: 17px;
  color: #111827;
}
.app-main {
  max-width: 1120px;
  width: 100%;
  margin: 0 auto;
  padding: 16px;
}
</style>
