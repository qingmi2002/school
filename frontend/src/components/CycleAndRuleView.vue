<template>
  <div class="split-stack">
    <!-- 1. 排课大时间周期（学期） -->
    <el-card shadow="never">
      <template #header>
        <div class="head-bar">
          <span>排课大周期（学期设置）</span>
          <el-button type="primary" size="small" @click="semDialog = true">+ 新增学期</el-button>
        </div>
      </template>
      <el-table :data="semesters" border stripe size="small">
        <el-table-column prop="code" label="学期代码" width="130" />
        <el-table-column prop="name" label="学期名称" />
        <el-table-column prop="total_weeks" label="总周数" width="80" />
        <el-table-column prop="start_date" label="开始日期" width="110" />
        <el-table-column prop="end_date" label="结束日期" width="110" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.is_current" type="success" size="small">当前排课周期</el-tag>
            <el-button v-else link type="primary" size="small" @click="onSetCurrent(row.id)">设为当前</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 2. 自定义必排 / 禁排 / 优先规则（全局及单实体） -->
    <el-card shadow="never">
      <template #header>
        <div class="head-bar">
          <span>时段必排与单独调整规则</span>
          <div class="btn-group">
            <el-button size="small" type="warning" plain @click="quickMustFirstPeriod">
              快捷：每天 1-2 节必排
            </el-button>
            <el-button size="small" type="primary" @click="ruleDialog = true">+ 自定义规则</el-button>
          </div>
        </div>
      </template>
      <el-table :data="rules" border stripe size="small">
        <el-table-column label="作用对象" width="120">
          <template #default="{ row }">{{ targetLabel(row.target_type, row.target_id) }}</template>
        </el-table-column>
        <el-table-column label="规则类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.rule_type === 'MUST_SCHEDULE' ? 'success' : row.rule_type === 'FORBID_SCHEDULE' ? 'danger' : 'warning'">
              {{ ruleTypeLabel(row.rule_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="适用星期" width="90">
          <template #default="{ row }">{{ row.day_of_week === 0 ? "每天" : `周${row.day_of_week}` }}</template>
        </el-table-column>
        <el-table-column label="适用节次" width="90">
          <template #default="{ row }">第{{ row.period_index }}大节</template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="onDeleteRule(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="semDialog" title="新增排课学期" width="420px">
      <el-form :model="semForm" label-width="80px" size="small">
        <el-form-item label="学期代码"><el-input v-model="semForm.code" placeholder="2026-2027-2" /></el-form-item>
        <el-form-item label="学期名称"><el-input v-model="semForm.name" placeholder="2026-2027学年第二学期" /></el-form-item>
        <el-form-item label="教学周数"><el-input-number v-model="semForm.total_weeks" :min="4" :max="30" /></el-form-item>
        <el-form-item label="起始日期"><el-input v-model="semForm.start_date" placeholder="2027-03-01" /></el-form-item>
        <el-form-item label="结束日期"><el-input v-model="semForm.end_date" placeholder="2027-07-15" /></el-form-item>
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
            <el-option label="全局（全校/本院系）" value="GLOBAL" />
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
            <el-option label="必须有课 (MUST)" value="MUST_SCHEDULE" />
            <el-option label="禁止排课 (FORBID)" value="FORBID_SCHEDULE" />
            <el-option label="优先排课 (PREFER)" value="PREFER_SCHEDULE" />
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
            <el-option label="1-2节 (第1大节)" :value="1" />
            <el-option label="3-4节 (第2大节)" :value="2" />
            <el-option label="5-6节 (第3大节)" :value="3" />
            <el-option label="7-8节 (第4大节)" :value="4" />
            <el-option label="9-10节 (第5大节)" :value="5" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注说明"><el-input v-model="ruleForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="ruleDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
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

const semesters = ref<SemesterItem[]>([]);
const rules = ref<PolicyRuleItem[]>([]);
const currentSemId = ref(1);

const semDialog = ref(false);
const ruleDialog = ref(false);
const semForm = reactive({ code: "", name: "", total_weeks: 18, start_date: "2027-03-01", end_date: "2027-07-15", is_current: false });
const ruleForm = reactive({
  target_type: "GLOBAL" as "GLOBAL" | "TEACHER" | "COHORT" | "CLASSROOM",
  target_id: null as number | null,
  rule_type: "MUST_SCHEDULE" as "MUST_SCHEDULE" | "FORBID_SCHEDULE" | "PREFER_SCHEDULE",
  day_of_week: 0,
  period_index: 1,
  remark: "",
});

function targetLabel(t: string, id: number | null): string {
  const m: Record<string, string> = { GLOBAL: "全局", TEACHER: "教师", COHORT: "班级", CLASSROOM: "教室" };
  return id ? `${m[t] || t}#${id}` : m[t] || t;
}

function ruleTypeLabel(t: string): string {
  if (t === "MUST_SCHEDULE") return "必须有课";
  if (t === "FORBID_SCHEDULE") return "禁止排课";
  return "优先排课";
}

async function loadData(): Promise<void> {
  semesters.value = await getSemesters();
  const cur = semesters.value.find((s) => s.is_current) || semesters.value[0];
  if (cur) currentSemId.value = cur.id;
  rules.value = await getPolicyRules(currentSemId.value);
}

async function onSetCurrent(id: number): Promise<void> {
  await setCurrentSemester(id);
  ElMessage.success("已切换当前排课周期");
  await loadData();
}

async function submitSem(): Promise<void> {
  await addSemester({ ...semForm });
  semDialog.value = false;
  ElMessage.success("学期已添加");
  await loadData();
}

async function quickMustFirstPeriod(): Promise<void> {
  await addPolicyRule({
    semester_id: currentSemId.value,
    target_type: "GLOBAL",
    target_id: null,
    rule_type: "MUST_SCHEDULE",
    day_of_week: 0,
    period_index: 1,
    remark: "每天第1-2节必须排课",
  });
  ElMessage.success("已添加：每天 1-2 节必排");
  await loadData();
}

async function submitRule(): Promise<void> {
  await addPolicyRule({
    semester_id: currentSemId.value,
    ...ruleForm,
    target_id: ruleForm.target_type === "GLOBAL" ? null : ruleForm.target_id,
  });
  ruleDialog.value = false;
  ElMessage.success("规则已保存");
  await loadData();
}

async function onDeleteRule(id: number): Promise<void> {
  await deletePolicyRule(id);
  await loadData();
}

onMounted(() => { void loadData(); });
</script>

<style scoped>
.split-stack { display: flex; flex-direction: column; gap: 12px; }
.head-bar { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 14px; }
.btn-group { display: flex; gap: 8px; }
</style>
