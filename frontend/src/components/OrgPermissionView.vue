<template>
  <div class="org-grid">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>当前选中组织节点能力开关（自由调整）</span>
          <el-tag v-if="selectedNode" type="primary">{{ selectedNode.node_name }} ({{ selectedNode.node_type_code }})</el-tag>
        </div>
      </template>
      <div v-if="selectedNode" class="flags-list">
        <div class="flag-row">
          <span>独立排课单元 (is_scheduling_unit)</span>
          <el-switch v-model="selectedNode.is_scheduling_unit" :disabled="!canEdit" @change="saveFlags" />
        </div>
        <div class="flag-row">
          <span>公共课输出方 (is_public_provider)</span>
          <el-switch v-model="selectedNode.is_public_provider" :disabled="!canEdit" @change="saveFlags" />
        </div>
        <div class="flag-row">
          <span>行政班级归属 (has_student_cohort)</span>
          <el-switch v-model="selectedNode.has_student_cohort" :disabled="!canEdit" @change="saveFlags" />
        </div>
        <div class="flag-row">
          <span>专属机房/场地池 (has_room_pool)</span>
          <el-switch v-model="selectedNode.has_room_pool" :disabled="!canEdit" @change="saveFlags" />
        </div>
        <div class="flag-row">
          <span>物理校区通勤边界 (is_campus_boundary)</span>
          <el-switch v-model="selectedNode.is_campus_boundary" :disabled="!canEdit" @change="saveFlags" />
        </div>
      </div>
      <div v-else class="muted">请在左侧树形导航中点击任意学校 / 学院 / 系部 / 专业节点查看配置。</div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>当前权限范围下的分级账号与角色</span>
          <el-tag type="info">共 {{ users.length }} 人（自动按校/院/系/专业隔离）</el-tag>
        </div>
      </template>
      <el-table :data="users" border stripe size="small">
        <el-table-column prop="username" label="工号/学号" width="120" />
        <el-table-column prop="real_name" label="姓名" width="140" />
        <el-table-column prop="role_label" label="分级角色" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="roleTagType(row.role_code)">{{ row.role_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="org_node_name" label="所属组织节点" />
        <el-table-column prop="cohort_name" label="所属行政班">
          <template #default="{ row }">{{ row.cohort_name || "-" }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  fetchScopedUsers,
  updateOrgNodeFlags,
  type OrgNodeTreeItem,
  type UserProfile,
} from "../api/client";

const props = defineProps<{
  selectedNode: OrgNodeTreeItem | null;
  canEdit: boolean;
}>();

const users = ref<UserProfile[]>([]);

function roleTagType(role: string): "danger" | "warning" | "primary" | "success" | "info" {
  if (role === "SUPER_ADMIN") return "danger";
  if (role.includes("SCHEDULER")) return "warning";
  if (role === "TEACHER") return "primary";
  if (role === "STUDENT") return "success";
  return "info";
}

async function saveFlags(): Promise<void> {
  if (!props.selectedNode) return;
  try {
    await updateOrgNodeFlags(props.selectedNode.id, {
      is_scheduling_unit: props.selectedNode.is_scheduling_unit,
      is_public_provider: props.selectedNode.is_public_provider,
      has_student_cohort: props.selectedNode.has_student_cohort,
      has_room_pool: props.selectedNode.has_room_pool,
      is_campus_boundary: props.selectedNode.is_campus_boundary,
    });
    ElMessage.success(`已保存【${props.selectedNode.node_name}】的能力开关配置`);
  } catch {
    ElMessage.error("保存失败，请确认具备该节点权限");
  }
}

onMounted(async () => {
  try {
    users.value = await fetchScopedUsers();
  } catch {
    users.value = [];
  }
});
</script>

<style scoped>
.org-grid { display: flex; flex-direction: column; gap: 14px; }
.card-head { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.flags-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.flag-row { display: flex; justify-content: space-between; align-items: center; background: #f8fafc; padding: 10px 14px; border-radius: 8px; border: 1px solid #e2e8f0; font-size: 13px; }
.muted { color: #64748b; font-size: 13px; }
</style>
