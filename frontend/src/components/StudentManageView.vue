<template>
  <div class="split-layout">
    <el-card shadow="never" class="sub-nav">
      <div class="sub-title">按班级导航</div>
      <div class="nav-item" :class="{ active: selectedCohortId === null }" @click="selectedCohortId = null">全部在校班级</div>
      <div
        v-for="c in cohorts"
        :key="c.id"
        class="nav-item"
        :class="{ active: selectedCohortId === c.id }"
        @click="selectedCohortId = c.id"
      >
        <span>{{ c.cohort_name }}</span>
        <span class="muted">{{ c.grade_year }}级</span>
      </div>
    </el-card>

    <el-card shadow="never" class="sub-main">
      <div class="bar">
        <strong>学生名单（共 {{ filteredStudents.length }} 人）</strong>
        <div style="display: flex; gap: 8px">
          <el-button size="small" @click="downloadDomainExcel('students')">导出学生 Excel</el-button>
          <el-upload :show-file-list="false" accept=".xlsx" :http-request="handleImport">
            <el-button size="small" type="warning">批量导入</el-button>
          </el-upload>
          <el-button size="small" type="primary" @click="dialog = true">+ 新增学生</el-button>
        </div>
      </div>

      <el-table :data="filteredStudents" size="small" border stripe>
        <el-table-column prop="username" label="学号" width="140" />
        <el-table-column prop="real_name" label="姓名" width="130" />
        <el-table-column label="所属班级">
          <template #default="{ row }">{{ cohortName(row.cohort_id) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleDelete(row.id)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" title="新增学生" width="400px">
      <el-form :model="form" label-width="76px" size="small">
        <el-form-item label="学号"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.real_name" /></el-form-item>
        <el-form-item label="所属班级">
          <el-select v-model="form.cohort_id" style="width: 100%">
            <el-option v-for="c in cohorts" :key="c.id" :label="`${c.cohort_name} (${c.grade_year}级)`" :value="c.id" />
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
import { apiClient } from "../api/client";
import { addStudent, deleteStudent, downloadDomainExcel, getCohorts, getStudents, type CohortItem, type StudentItem } from "../api/resources";

const cohorts = ref<CohortItem[]>([]);
const students = ref<StudentItem[]>([]);
const selectedCohortId = ref<number | null>(null);
const dialog = ref(false);
const form = reactive({ username: "", real_name: "", cohort_id: undefined as number | undefined });

const filteredStudents = computed(() =>
  selectedCohortId.value ? students.value.filter((s) => s.cohort_id === selectedCohortId.value) : students.value
);

function cohortName(cid?: number | null) {
  return cohorts.value.find((c) => c.id === cid)?.cohort_name || "-";
}

async function loadAll() {
  const [cList, sList] = await Promise.all([getCohorts(), getStudents()]);
  cohorts.value = cList;
  students.value = sList;
  if (!form.cohort_id && cList[0]) form.cohort_id = cList[0].id;
}

async function handleImport(opt: any) {
  const fd = new FormData();
  fd.append("file", opt.file);
  await apiClient.post("/resources/master-import/upload", fd);
  ElMessage.success("导入完成");
  await loadAll();
}

async function handleCreate() {
  if (!form.username || !form.real_name || !form.cohort_id) return;
  const c = cohorts.value.find((x) => x.id === form.cohort_id);
  await addStudent({ username: form.username, real_name: form.real_name, org_node_id: c?.org_node_id || 1, cohort_id: form.cohort_id });
  ElMessage.success("学生已添加");
  dialog.value = false;
  form.username = "";
  form.real_name = "";
  await loadAll();
}

async function handleDelete(id: number) {
  await deleteStudent(id);
  ElMessage.success("已移除");
  await loadAll();
}

onMounted(loadAll);
</script>

<style scoped>
.split-layout { display: flex; gap: 12px; align-items: flex-start; }
.sub-nav { width: 220px; flex-shrink: 0; }
.sub-main { flex: 1; min-width: 0; }
.sub-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.nav-item { display: flex; justify-content: space-between; padding: 7px 10px; border-radius: 5px; cursor: pointer; font-size: 13px; }
.nav-item:hover { background: #f1f5f9; }
.nav-item.active { background: #eff6ff; color: #1d4ed8; font-weight: 600; }
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.muted { color: #64748b; font-size: 12px; }
</style>
