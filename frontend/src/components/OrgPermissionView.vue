<template>
  <div class="org-grid">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>组织机构自定义管理与能力开关</span>
          <div class="head-btns">
            <el-button v-if="canEdit" type="primary" size="small" @click="openAddDialog">+ 新增下级机构</el-button>
            <el-button v-if="canEdit && selectedNode" size="small" @click="openRenameDialog">重命名</el-button>
            <el-button v-if="canEdit && selectedNode && selectedNode.parent_id" type="danger" plain size="small" @click="handleDelete">删除节点</el-button>
          </div>
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
          <span>专属场地池 (has_room_pool)</span>
          <el-switch v-model="selectedNode.has_room_pool" :disabled="!canEdit" @change="saveFlags" />
        </div>
        <div class="flag-row">
          <span>物理校区边界 (is_campus_boundary)</span>
          <el-switch v-model="selectedNode.is_campus_boundary" :disabled="!canEdit" @change="saveFlags" />
        </div>
      </div>
      <div v-else class="muted">请在左侧树形导航中选择任意组织节点，或点击右上角新增机构。</div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>当前权限范围下的分级账号</span>
          <el-tag type="info" size="small">共 {{ users.length }} 人</el-tag>
        </div>
      </template>
      <el-table :data="users" border stripe size="small">
        <el-table-column prop="username" label="工号/学号" width="120" />
        <el-table-column prop="real_name" label="姓名" width="140" />
        <el-table-column prop="role_label" label="分级角色" width="130" />
        <el-table-column prop="org_node_name" label="所属机构" />
        <el-table-column prop="cohort_name" label="行政班">
          <template #default="{ row }">{{ row.cohort_name || "-" }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="addDialog" title="自定义新增组织机构" width="420px">
      <el-form :model="addForm" label-width="84px" size="small">
        <el-form-item label="上级机构">
          <el-input :model-value="selectedNode ? selectedNode.node_name : '顶层根节点'" disabled />
        </el-form-item>
        <el-form-item label="机构编码"><el-input v-model="addForm.node_code" placeholder="如 COL_MATH" /></el-form-item>
        <el-form-item label="机构名称"><el-input v-model="addForm.node_name" placeholder="如 数学学院" /></el-form-item>
        <el-form-item label="机构类型">
          <el-select v-model="addForm.node_type_code" style="width: 100%">
            <el-option label="学校 (SCHOOL)" value="SCHOOL" />
            <el-option label="校区 (CAMPUS)" value="CAMPUS" />
            <el-option label="学院 (COLLEGE)" value="COLLEGE" />
            <el-option label="教学系 (DEPT)" value="DEPT" />
            <el-option label="专业 (MAJOR)" value="MAJOR" />
            <el-option label="公共教学部 (PUBLIC_DEPT)" value="PUBLIC_DEPT" />
            <el-option label="实训中心 (TRAINING_CENTER)" value="TRAINING_CENTER" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="addDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitAdd">确定新增</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="renameDialog" title="重命名组织机构" width="380px">
      <el-input v-model="renameName" size="small" />
      <template #footer>
        <el-button size="small" @click="renameDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitRename">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchScopedUsers, updateOrgNodeFlags, type OrgNodeTreeItem, type UserProfile } from "../api/client";
import { createOrgNodeApi, deleteOrgNodeApi, renameOrgNodeApi } from "../api/resources";

const props = defineProps<{ selectedNode: OrgNodeTreeItem | null; canEdit: boolean }>();
const emit = defineEmits<{ (e: "tree-changed"): void }>();

const users = ref<UserProfile[]>([]);
const addDialog = ref(false);
const renameDialog = ref(false);
const renameName = ref("");
const addForm = reactive({ node_code: "", node_name: "", node_type_code: "DEPT" });

function openAddDialog(): void {
  addForm.node_code = "";
  addForm.node_name = "";
  addDialog.value = true;
}

function openRenameDialog(): void {
  if (!props.selectedNode) return;
  renameName.value = props.selectedNode.node_name;
  renameDialog.value = true;
}

async function submitAdd(): Promise<void> {
  await createOrgNodeApi({
    parent_id: props.selectedNode ? props.selectedNode.id : null,
    ...addForm,
  });
  addDialog.value = false;
  ElMessage.success("组织机构已新增入库");
  emit("tree-changed");
}

async function submitRename(): Promise<void> {
  if (!props.selectedNode) return;
  await renameOrgNodeApi(props.selectedNode.id, renameName.value);
  renameDialog.value = false;
  ElMessage.success("机构名称已更新");
  emit("tree-changed");
}

async function handleDelete(): Promise<void> {
  if (!props.selectedNode) return;
  try {
    await deleteOrgNodeApi(props.selectedNode.id);
    ElMessage.success("节点已停用移除");
    emit("tree-changed");
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "删除失败";
    ElMessage.error(msg);
  }
}

async function saveFlags(): Promise<void> {
  if (!props.selectedNode) return;
  await updateOrgNodeFlags(props.selectedNode.id, {
    is_scheduling_unit: props.selectedNode.is_scheduling_unit,
    is_public_provider: props.selectedNode.is_public_provider,
    has_student_cohort: props.selectedNode.has_student_cohort,
    has_room_pool: props.selectedNode.has_room_pool,
    is_campus_boundary: props.selectedNode.is_campus_boundary,
  });
  ElMessage.success("开关配置已保存到数据库");
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
.org-grid { display: flex; flex-direction: column; gap: 12px; }
.card-head { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 14px; }
.head-btns { display: flex; gap: 8px; }
.flags-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }
.flag-row { display: flex; justify-content: space-between; align-items: center; background: #f8fafc; padding: 8px 12px; border-radius: 6px; border: 1px solid #e2e8f0; font-size: 13px; }
.muted { color: #64748b; font-size: 13px; }
</style>
