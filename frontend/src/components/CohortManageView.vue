<template>
  <div class="split-layout">
    <el-card shadow="never" class="sub-nav">
      <div class="sub-title">按届别与学籍状态</div>
      <el-radio-group v-model="statusFilter" size="small" style="margin-bottom: 10px; width: 100%">
        <el-radio-button value="ALL">全部</el-radio-button>
        <el-radio-button value="ACTIVE">在校</el-radio-button>
        <el-radio-button value="GRADUATED">已毕业</el-radio-button>
      </el-radio-group>
      <div class="nav-item" :class="{ active: gradeFilter === null }" @click="gradeFilter = null">全部入学届别</div>
      <div
        v-for="y in enrollYears"
        :key="y"
        class="nav-item"
        :class="{ active: gradeFilter === y }"
        @click="gradeFilter = y"
      >
        {{ y }} 级入学
      </div>
    </el-card>

    <el-card shadow="never" class="sub-main">
      <div class="bar">
        <strong>班级全生命周期管理（入学至毕业，共 {{ filteredCohorts.length }} 个班）</strong>
        <div style="display: flex; gap: 8px">
          <el-button size="small" @click="downloadDomainExcel('cohorts')">导出班级 Excel</el-button>
          <el-button size="small" type="primary" @click="dialog = true">+ 新建班级</el-button>
        </div>
      </div>

      <el-table :data="filteredCohorts" size="small" border stripe>
        <el-table-column prop="cohort_code" label="班级编码" width="110" />
        <el-table-column prop="cohort_name" label="班级名称" min-width="140" />
        <el-table-column label="入学—毕业周期" width="190">
          <template #default="{ row }">
            <el-tag size="small" type="info">
              {{ row.grade_year }}年入学 → {{ row.graduation_year || (row.grade_year + (row.study_years || 4)) }}年毕业（{{ row.study_years || 4 }}年制）
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="student_count" label="人数" width="75" />
        <el-table-column label="学籍状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.cohort_status === 'GRADUATED' ? 'info' : 'success'">
              {{ row.cohort_status === "GRADUATED" ? "已毕业归档" : "在校生" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button link size="small" type="warning" @click="toggleGraduated(row)">
              {{ row.cohort_status === "GRADUATED" ? "恢复在校" : "毕业归档" }}
            </el-button>
            <el-button link size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" title="新建班级（设定入学至毕业周期）" width="440px">
      <el-form :model="form" label-width="88px" size="small">
        <el-form-item label="班级编码"><el-input v-model="form.cohort_code" placeholder="如 SE2601" /></el-form-item>
        <el-form-item label="班级名称"><el-input v-model="form.cohort_name" placeholder="如 软件工程2601班" /></el-form-item>
        <el-form-item label="入学年份"><el-input-number v-model="form.grade_year" :min="2018" :max="2035" /></el-form-item>
        <el-form-item label="学制（年）">
          <el-select v-model="form.study_years" style="width: 100%">
            <el-option label="2 年制" :value="2" />
            <el-option label="3 年制（专科）" :value="3" />
            <el-option label="4 年制（本科）" :value="4" />
            <el-option label="5 年制（本硕/医学）" :value="5" />
          </el-select>
        </el-form-item>
        <el-form-item label="预计毕业">
          <el-tag type="success">{{ form.grade_year + form.study_years }} 年夏季毕业</el-tag>
        </el-form-item>
        <el-form-item label="班级人数"><el-input-number v-model="form.student_count" :min="5" :max="120" /></el-form-item>
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
import { fetchOrgTree } from "../api/client";
import { addCohort, deleteCohort, downloadDomainExcel, getCohorts, updateCohortStatus, type CohortItem } from "../api/resources";

const cohorts = ref<CohortItem[]>([]);
const defaultOrgId = ref<number>(1);
const statusFilter = ref("ALL");
const gradeFilter = ref<number | null>(null);
const dialog = ref(false);
const form = reactive({ cohort_code: "", cohort_name: "", grade_year: 2026, study_years: 4, student_count: 42 });

const enrollYears = computed(() => Array.from(new Set(cohorts.value.map((c) => c.grade_year))).sort((a, b) => b - a));
const filteredCohorts = computed(() =>
  cohorts.value.filter((c) => {
    if (statusFilter.value !== "ALL" && (c.cohort_status || "ACTIVE") !== statusFilter.value) return false;
    if (gradeFilter.value !== null && c.grade_year !== gradeFilter.value) return false;
    return true;
  })
);

async function loadAll() {
  const [cList, tree] = await Promise.all([getCohorts(), fetchOrgTree()]);
  cohorts.value = cList;
  if (tree[0]) defaultOrgId.value = tree[0].id;
}

async function handleCreate() {
  if (!form.cohort_code || !form.cohort_name) return;
  await addCohort({
    cohort_code: form.cohort_code,
    cohort_name: form.cohort_name,
    org_node_id: defaultOrgId.value,
    grade_year: form.grade_year,
    study_years: form.study_years,
    graduation_year: form.grade_year + form.study_years,
    cohort_status: "ACTIVE",
    student_count: form.student_count,
  });
  ElMessage.success("班级已创建");
  dialog.value = false;
  form.cohort_code = "";
  form.cohort_name = "";
  await loadAll();
}

async function toggleGraduated(row: CohortItem) {
  const next = row.cohort_status === "GRADUATED" ? "ACTIVE" : "GRADUATED";
  await updateCohortStatus(row.id, next);
  ElMessage.success(next === "GRADUATED" ? "已归档为毕业班" : "已恢复为在校生");
  await loadAll();
}

async function handleDelete(id: number) {
  await deleteCohort(id);
  ElMessage.success("已删除");
  await loadAll();
}

onMounted(loadAll);
</script>

<style scoped>
.split-layout { display: flex; gap: 12px; align-items: flex-start; }
.sub-nav { width: 220px; flex-shrink: 0; }
.sub-main { flex: 1; min-width: 0; }
.sub-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.nav-item { padding: 7px 10px; border-radius: 5px; cursor: pointer; font-size: 13px; }
.nav-item:hover { background: #f1f5f9; }
.nav-item.active { background: #eff6ff; color: #1d4ed8; font-weight: 600; }
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
</style>
