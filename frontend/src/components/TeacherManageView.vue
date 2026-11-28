<template>
  <div class="split-layout">
    <el-card shadow="never" class="sub-nav">
      <div class="sub-title">按组织架构筛选</div>
      <el-button link size="small" type="primary" style="margin-bottom: 6px" @click="selectedOrgId = null">全部组织</el-button>
      <el-tree
        :data="orgTree"
        node-key="id"
        default-expand-all
        highlight-current
        :props="{ label: 'node_name', children: 'children' }"
        @node-click="(n: OrgNodeTreeItem) => (selectedOrgId = n.id)"
      />
    </el-card>

    <el-card shadow="never" class="sub-main">
      <el-tabs v-model="tab">
        <el-tab-pane label="教师档案与导入导出" name="list">
          <div class="bar">
            <span class="muted">共 {{ filteredTeachers.length }} 位教师</span>
            <div style="display: flex; gap: 8px">
              <el-button size="small" @click="downloadDomainExcel('teachers')">导出教师 Excel</el-button>
              <el-button size="small" @click="downloadMasterTemplate">下载导入模板</el-button>
              <el-upload :show-file-list="false" accept=".xlsx" :http-request="handleImport">
                <el-button size="small" type="warning">批量导入</el-button>
              </el-upload>
              <el-button size="small" type="primary" @click="dialog = true">+ 新增教师</el-button>
            </div>
          </div>
          <el-table :data="filteredTeachers" size="small" border stripe>
            <el-table-column prop="username" label="工号" width="120" />
            <el-table-column prop="real_name" label="姓名" width="120" />
            <el-table-column label="权限级别" width="150">
              <template #default="{ row }">
                <el-tag size="small" :type="row.role_code === 'TEACHING_LEAD' ? 'warning' : 'info'">
                  {{ row.role_code === "TEACHING_LEAD" ? "教研室主任" : "普通教师" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="排课优先级" width="120">
              <template #default="{ row }">L{{ row.teacher_priority || 1 }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button link type="danger" size="small" @click="handleDelete(row.id)">停用</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="教师禁排与填报窗口" name="grid">
          <TeacherUnavailableGrid />
        </el-tab-pane>
        <el-tab-pane label="教师多课多班学时负荷" name="workload">
          <el-table :data="workloads" size="small" border stripe>
            <el-table-column prop="teacher_name" label="教师" width="110" />
            <el-table-column label="所带课程" min-width="180"><template #default="{ row }">{{ row.courses.join("、") }}</template></el-table-column>
            <el-table-column label="所带班级" min-width="180"><template #default="{ row }">{{ row.cohorts.join("、") }}</template></el-table-column>
            <el-table-column prop="total_weekly_sessions" label="周节次" width="85" />
            <el-table-column prop="total_semester_hours" label="学期总学时" width="100" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="dialog" title="新增教师" width="420px">
      <el-form :model="form" label-width="88px" size="small">
        <el-form-item label="工号"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.real_name" /></el-form-item>
        <el-form-item label="权限级别">
          <el-select v-model="form.role_code" style="width: 100%">
            <el-option label="普通教师 (TEACHER)" value="TEACHER" />
            <el-option label="教研室主任 / 课程组长 (TEACHING_LEAD)" value="TEACHING_LEAD" />
          </el-select>
        </el-form-item>
        <el-form-item label="排课优先级">
          <el-select v-model="form.teacher_priority" style="width: 100%">
            <el-option label="1 - 普通教师" :value="1" />
            <el-option label="2 - 骨干 / 教授" :value="2" />
            <el-option label="3 - 外聘 / 特聘高优" :value="3" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="dialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleCreate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { apiClient, fetchOrgTree, fetchTeacherWorkload, type OrgNodeTreeItem, type TeacherWorkloadItem } from "../api/client";
import { addTeacher, deleteTeacher, downloadDomainExcel, getTeachers, type TeacherItem } from "../api/resources";
import TeacherUnavailableGrid from "./TeacherUnavailableGrid.vue";

const tab = ref("list");
const orgTree = ref<OrgNodeTreeItem[]>([]);
const selectedOrgId = ref<number | null>(null);
const teachers = ref<TeacherItem[]>([]);
const workloads = ref<TeacherWorkloadItem[]>([]);
const dialog = ref(false);
const form = reactive({ username: "", real_name: "", role_code: "TEACHER", teacher_priority: 1 });

const filteredTeachers = computed(() =>
  selectedOrgId.value ? teachers.value.filter((t) => t.org_node_id === selectedOrgId.value) : teachers.value
);

async function loadAll() {
  const [tree, tList, wl] = await Promise.all([fetchOrgTree(), getTeachers(), fetchTeacherWorkload()]);
  orgTree.value = tree;
  teachers.value = tList;
  workloads.value = wl;
}

function downloadMasterTemplate() {
  window.open("/api/v1/resources/master-import/template", "_blank");
}

async function handleImport(opt: any) {
  const fd = new FormData();
  fd.append("file", opt.file);
  await apiClient.post("/resources/master-import/upload", fd);
  ElMessage.success("导入完成");
  await loadAll();
}

async function handleCreate() {
  if (!form.username || !form.real_name) return;
  await addTeacher({ ...form, org_node_id: selectedOrgId.value || orgTree.value[0]?.id || 1 });
  ElMessage.success("教师已添加");
  dialog.value = false;
  form.username = "";
  form.real_name = "";
  await loadAll();
}

async function handleDelete(id: number) {
  await deleteTeacher(id);
  ElMessage.success("已停用");
  await loadAll();
}

onMounted(loadAll);
</script>

<style scoped>
.split-layout { display: flex; gap: 12px; align-items: flex-start; }
.sub-nav { width: 220px; flex-shrink: 0; }
.sub-main { flex: 1; min-width: 0; }
.sub-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.muted { color: #64748b; font-size: 12px; }
</style>
