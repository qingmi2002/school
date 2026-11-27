<template>
  <el-card shadow="never">
    <el-tabs v-model="tab" type="card">
      <!-- 1. 班级周历与整周实训 -->
      <el-tab-pane label="班级周历 / 整周实训" name="week-plan">
        <div class="head-bar">
          <span class="tip">点击任意班级的周次格子，可设为整周集中实训/实习/考试周（常规课自动跳过）</span>
          <el-button size="small" type="primary" @click="openWeekModal(null, 10)">+ 批量设整周实训</el-button>
        </div>

        <div class="week-scroll">
          <table class="week-grid">
            <thead>
              <tr>
                <th class="cohort-col">班级</th>
                <th class="eff-col">常规有效周</th>
                <th v-for="w in weekMatrix.total_weeks" :key="w" class="w-col">W{{ w }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in weekMatrix.rows" :key="row.cohort_id">
                <td class="cohort-col">{{ row.cohort_name }}</td>
                <td class="eff-col">{{ row.effective_regular_label }}</td>
                <td v-for="w in weekMatrix.total_weeks" :key="w" class="w-cell">
                  <button
                    type="button"
                    class="wk-btn"
                    :class="`wk-${(row.cells[w]?.week_mode || 'REGULAR').toLowerCase()}`"
                    :title="row.cells[w]?.block_course_name || modeShort(row.cells[w]?.week_mode)"
                    @click="openWeekModal(row.cohort_id, w)"
                  >
                    {{ modeShort(row.cells[w]?.week_mode) }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </el-tab-pane>

      <!-- 2. 排课大周期（学期） -->
      <el-tab-pane label="学期大周期" name="semesters">
        <div class="head-bar">
          <span class="tip">自定义排课大周期（学期起止日期与总周数）</span>
          <el-button type="primary" size="small" @click="semDialog = true">+ 新增学期</el-button>
        </div>
        <el-table :data="semesters" border stripe size="small">
          <el-table-column prop="code" label="学期代码" width="130" />
          <el-table-column prop="name" label="学期名称" />
          <el-table-column prop="total_weeks" label="总周数" width="80" />
          <el-table-column prop="start_date" label="开始日期" width="110" />
          <el-table-column prop="end_date" label="结束日期" width="110" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.is_current" type="success" size="small">当前周期</el-tag>
              <el-button v-else link type="primary" size="small" @click="onSetCurrent(row.id)">设为当前</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 3. 必排 / 禁排时段规则 -->
      <el-tab-pane label="必排与禁排规则" name="rules">
        <div class="head-bar">
          <span class="tip">支持全局或单个教师/班级/教室自定义必排或禁排时段</span>
          <div class="btn-group">
            <el-button size="small" type="warning" plain @click="quickMustFirstPeriod">快捷：每天 1-2 节必排</el-button>
            <el-button size="small" type="primary" @click="ruleDialog = true">+ 自定义规则</el-button>
          </div>
        </div>
        <el-table :data="rules" border stripe size="small">
          <el-table-column label="对象" width="110">
            <template #default="{ row }">{{ targetLabel(row.target_type, row.target_id) }}</template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.rule_type === 'MUST_SCHEDULE' ? 'success' : row.rule_type === 'FORBID_SCHEDULE' ? 'danger' : 'warning'">
                {{ ruleTypeLabel(row.rule_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="星期" width="80">
            <template #default="{ row }">{{ row.day_of_week === 0 ? "每天" : `周${row.day_of_week}` }}</template>
          </el-table-column>
          <el-table-column label="节次" width="90">
            <template #default="{ row }">第{{ row.period_index }}大节</template>
          </el-table-column>
          <el-table-column prop="remark" label="说明" />
          <el-table-column label="操作" width="70">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="onDeleteRule(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 班级整周实训/考试配置弹窗 -->
    <el-dialog v-model="weekDialog" title="设置班级周次属性（整周实训/实习/考试/常规）" width="440px">
      <el-form :model="weekForm" label-width="84px" size="small">
        <el-form-item label="目标班级">
          <el-select v-model="weekForm.cohort_id" style="width: 100%">
            <el-option v-for="r in weekMatrix.rows" :key="r.cohort_id" :label="r.cohort_name" :value="r.cohort_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="起始周 / 结束周">
          <div style="display: flex; gap: 8px; align-items: center">
            <el-input-number v-model="weekForm.start_week" :min="1" :max="weekMatrix.total_weeks" />
            <span>至</span>
            <el-input-number v-model="weekForm.end_week" :min="1" :max="weekMatrix.total_weeks" />
          </div>
        </el-form-item>
        <el-form-item label="周次性质">
          <el-select v-model="weekForm.week_mode" style="width: 100%">
            <el-option label="常规教学周 (REGULAR)" value="REGULAR" />
            <el-option label="整周集中实训 (PRACTICUM)" value="PRACTICUM" />
            <el-option label="校外实习周 (INTERNSHIP)" value="INTERNSHIP" />
            <el-option label="集中考试周 (EXAM)" value="EXAM" />
            <el-option label="停课/放假 (HOLIDAY)" value="HOLIDAY" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="weekForm.week_mode !== 'REGULAR'" label="实训/事项名">
          <el-input v-model="weekForm.block_course_name" placeholder="如：Java企业级综合实训" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="weekDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitWeekRange">保存生效</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="semDialog" title="新增排课学期" width="420px">
      <el-form :model="semForm" label-width="80px" size="small">
        <el-form-item label="学期代码"><el-input v-model="semForm.code" placeholder="2026-2027-2" /></el-form-item>
        <el-form-item label="学期名称"><el-input v-model="semForm.name" placeholder="2026-2027学年第二学期" /></el-form-item>
        <el-form-item label="教学周数"><el-input-number v-model="semForm.total_weeks" :min="4" :max="30" /></el-form-item>
        <el-form-item label="起始日期"><el-input v-model="semForm.start_date" /></el-form-item>
        <el-form-item label="结束日期"><el-input v-model="semForm.end_date" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="semDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitSem">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="ruleDialog" title="新增时段规则" width="440px">
      <el-form :model="ruleForm" label-width="80px" size="small">
        <el-form-item label="作用对象">
          <el-select v-model="ruleForm.target_type" style="width: 100%">
            <el-option label="全局" value="GLOBAL" />
            <el-option label="单个教师" value="TEACHER" />
            <el-option label="单个班级" value="COHORT" />
            <el-option label="单个教室" value="CLASSROOM" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="ruleForm.target_type !== 'GLOBAL'" label="对象 ID">
          <el-input-number v-model="ruleForm.target_id" :min="1" />
        </el-form-item>
        <el-form-item label="规则类型">
          <el-select v-model="ruleForm.rule_type" style="width: 100%">
            <el-option label="必须有课" value="MUST_SCHEDULE" />
            <el-option label="禁止排课" value="FORBID_SCHEDULE" />
            <el-option label="优先排课" value="PREFER_SCHEDULE" />
          </el-select>
        </el-form-item>
        <el-form-item label="星期">
          <el-select v-model="ruleForm.day_of_week" style="width: 100%">
            <el-option label="每天" :value="0" />
            <el-option v-for="d in 5" :key="d" :label="`周${d}`" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="节次">
          <el-select v-model="ruleForm.period_index" style="width: 100%">
            <el-option label="1-2节" :value="1" />
            <el-option label="3-4节" :value="2" />
            <el-option label="5-6节" :value="3" />
            <el-option label="7-8节" :value="4" />
            <el-option label="9-10节" :value="5" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="ruleForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="ruleDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitRule">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { apiClient } from "../api/client";
import {
  addPolicyRule,
  addSemester,
  deletePolicyRule,
  getPolicyRules,
  getSemesters,
  setCurrentSemester,
  type PolicyRuleItem,
  type SemesterItem,
} from "../api/resources";

interface WeekCell {
  week_no: number;
  week_mode: string;
  block_course_name?: string | null;
}
interface CohortWeekRow {
  cohort_id: number;
  cohort_code: string;
  cohort_name: string;
  effective_regular_label: string;
  cells: Record<number, WeekCell>;
}

const tab = ref("week-plan");
const semesters = ref<SemesterItem[]>([]);
const rules = ref<PolicyRuleItem[]>([]);
const currentSemId = ref(1);
const weekMatrix = ref<{ semester_id: number; total_weeks: number; rows: CohortWeekRow[] }>({
  semester_id: 1,
  total_weeks: 18,
  rows: [],
});

const weekDialog = ref(false);
const semDialog = ref(false);
const ruleDialog = ref(false);

const weekForm = reactive({
  cohort_id: 1,
  start_week: 10,
  end_week: 11,
  week_mode: "PRACTICUM",
  block_course_name: "",
});
const semForm = reactive({ code: "", name: "", total_weeks: 18, start_date: "2027-03-01", end_date: "2027-07-15", is_current: false });
const ruleForm = reactive({
  target_type: "GLOBAL" as "GLOBAL" | "TEACHER" | "COHORT" | "CLASSROOM",
  target_id: null as number | null,
  rule_type: "MUST_SCHEDULE" as "MUST_SCHEDULE" | "FORBID_SCHEDULE" | "PREFER_SCHEDULE",
  day_of_week: 0,
  period_index: 1,
  remark: "",
});

function modeShort(mode?: string): string {
  if (mode === "PRACTICUM") return "实训";
  if (mode === "INTERNSHIP") return "实习";
  if (mode === "EXAM") return "考试";
  if (mode === "HOLIDAY") return "停课";
  return "常";
}

function targetLabel(t: string, id: number | null): string {
  const m: Record<string, string> = { GLOBAL: "全局", TEACHER: "教师", COHORT: "班级", CLASSROOM: "教室" };
  return id ? `${m[t] || t}#${id}` : m[t] || t;
}

function ruleTypeLabel(t: string): string {
  if (t === "MUST_SCHEDULE") return "必须有课";
  if (t === "FORBID_SCHEDULE") return "禁止排课";
  return "优先排课";
}

function openWeekModal(cohortId: number | null, weekNo: number): void {
  if (cohortId) weekForm.cohort_id = cohortId;
  else if (weekMatrix.value.rows[0]) weekForm.cohort_id = weekMatrix.value.rows[0].cohort_id;
  weekForm.start_week = weekNo;
  weekForm.end_week = weekNo;
  weekDialog.value = true;
}

async function loadData(): Promise<void> {
  semesters.value = await getSemesters();
  const cur = semesters.value.find((s) => s.is_current) || semesters.value[0];
  if (cur) currentSemId.value = cur.id;
  rules.value = await getPolicyRules(currentSemId.value);
  const { data } = await apiClient.get("/week-plan/matrix", { params: { semester_id: currentSemId.value } });
  weekMatrix.value = data;
}

async function submitWeekRange(): Promise<void> {
  await apiClient.put("/week-plan/range", { semester_id: currentSemId.value, ...weekForm });
  weekDialog.value = false;
  ElMessage.success("班级周历已更新入库");
  await loadData();
}

async function onSetCurrent(id: number): Promise<void> { await setCurrentSemester(id); await loadData(); }
async function submitSem(): Promise<void> { await addSemester({ ...semForm }); semDialog.value = false; await loadData(); }
async function quickMustFirstPeriod(): Promise<void> {
  await addPolicyRule({ semester_id: currentSemId.value, target_type: "GLOBAL", target_id: null, rule_type: "MUST_SCHEDULE", day_of_week: 0, period_index: 1, remark: "每天1-2节必排" });
  ElMessage.success("已添加：每天 1-2 节必排");
  await loadData();
}
async function submitRule(): Promise<void> {
  await addPolicyRule({ semester_id: currentSemId.value, ...ruleForm, target_id: ruleForm.target_type === "GLOBAL" ? null : ruleForm.target_id });
  ruleDialog.value = false;
  await loadData();
}
async function onDeleteRule(id: number): Promise<void> { await deletePolicyRule(id); await loadData(); }

onMounted(() => { void loadData(); });
</script>

<style scoped>
.head-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 10px; flex-wrap: wrap; }
.tip { font-size: 12px; color: #606266; }
.btn-group { display: flex; gap: 8px; }
.week-scroll { overflow-x: auto; }
.week-grid { border-collapse: collapse; width: 100%; min-width: 780px; font-size: 12px; }
.week-grid th, .week-grid td { border: 1px solid #e2e8f0; padding: 4px; text-align: center; }
.cohort-col { width: 110px; background: #f8fafc; font-weight: 600; }
.eff-col { width: 110px; background: #f8fafc; color: #2563eb; font-weight: 500; }
.w-col { width: 34px; background: #f8fafc; }
.wk-btn { width: 100%; height: 28px; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; }
.wk-regular { background: #f1f5f9; color: #64748b; }
.wk-practicum { background: #fef3c7; color: #b45309; font-weight: 600; }
.wk-internship { background: #e0e7ff; color: #3730a3; font-weight: 600; }
.wk-exam { background: #fee2e2; color: #b91c1c; font-weight: 600; }
.wk-holiday { background: #e5e7eb; color: #4b5563; }
</style>
