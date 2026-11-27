<template>
  <el-card shadow="never" class="grid-card">
    <template #header>
      <div class="card-header">
        <div>
          <div class="title">教师禁排与偏好时间填报</div>
          <div class="subtitle">点击网格循环切换：空闲 → 绝对禁排（红） → 尽量不排（橙）</div>
        </div>
        <div class="actions">
          <el-switch
            v-if="isAdmin"
            v-model="windowOpen"
            active-text="开放教师自助填报"
            inactive-text="已关闭填报"
            style="margin-right: 8px"
            @change="handleToggleWindow"
          />
          <el-select
            v-if="canSwitchTeacher"
            v-model="selectedTeacherId"
            size="small"
            placeholder="选择教师"
            style="width: 170px"
            @change="loadSavedGrid"
          >
            <el-option
              v-for="t in teachers"
              :key="t.id"
              :label="`${t.real_name} (${t.role_code === 'TEACHING_LEAD' ? '教研室主任' : '教师'})`"
              :value="t.id"
            />
          </el-select>
          <el-tag v-else-if="me" size="small" type="info">{{ me.real_name }}（本人填报）</el-tag>
          <el-button size="small" @click="clearAll">清空</el-button>
          <el-button type="primary" size="small" :loading="saving" @click="handleSubmit">
            提交禁排
          </el-button>
        </div>
      </div>
    </template>

    <el-alert
      v-if="!windowOpen && me?.role_code === 'TEACHER'"
      type="warning"
      title="管理员当前已关闭教师自助禁排填报窗口，如需调整请联系教研室主任或排课管理员。"
      show-icon
      :closable="false"
      style="margin-bottom: 10px"
    />

    <div class="legend-row">
      <span class="legend-item"><i class="dot free" /> 可排</span>
      <span class="legend-item"><i class="dot hard" /> 绝对禁排 (HARD)</span>
      <span class="legend-item"><i class="dot soft" /> 尽量不排 (SOFT)</span>
    </div>

    <div class="matrix-scroll">
      <table class="slot-matrix">
        <thead>
          <tr>
            <th class="period-col">节次</th>
            <th v-for="d in days" :key="d.value">{{ d.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in periods" :key="p.value">
            <td class="period-col">{{ p.label }}</td>
            <td v-for="d in days" :key="`${d.value}-${p.value}`">
              <button
                type="button"
                class="slot-cell"
                :class="cellClass(slotId(d.value, p.value))"
                @click="toggleCell(slotId(d.value, p.value))"
              >
                {{ cellLabel(slotId(d.value, p.value)) }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="reason-row" style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
      <el-radio-group v-model="weekRangeMode" size="small">
        <el-radio-button value="ALL">全学期生效</el-radio-button>
        <el-radio-button value="RANGE">指定周次生效</el-radio-button>
      </el-radio-group>
      <template v-if="weekRangeMode === 'RANGE'">
        <el-input-number v-model="startWeek" :min="1" :max="24" size="small" style="width: 90px" />
        <span>至</span>
        <el-input-number v-model="endWeek" :min="1" :max="24" size="small" style="width: 90px" />
        <span>周</span>
      </template>
      <el-input
        v-model="reason"
        style="flex: 1; min-width: 220px"
        size="small"
        placeholder="选填禁排原因（如：教研室例会、出差调研、跨校区通勤）"
        clearable
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  apiClient,
  fetchMeApi,
  fetchTeacherUnavailWindow,
  saveTeacherUnavailableGrid,
  setTeacherUnavailWindow,
  type ConstraintLevel,
  type TeacherUnavailableSlotPayload,
  type UserProfile,
} from "../api/client";

const days = [
  { value: 1, label: "周一" },
  { value: 2, label: "周二" },
  { value: 3, label: "周三" },
  { value: 4, label: "周四" },
  { value: 5, label: "周五" },
];

const periods = [
  { value: 1, label: "1-2节" },
  { value: 2, label: "3-4节" },
  { value: 3, label: "5-6节" },
  { value: 4, label: "7-8节" },
  { value: 5, label: "9-10节" },
];

const me = ref<UserProfile | null>(null);
const semesterId = ref<number>(1);
const selectedTeacherId = ref<number>(1);
const teachers = ref<Array<{ id: number; real_name: string; role_code: string }>>([]);
const windowOpen = ref<boolean>(true);
const selected = reactive<Record<number, ConstraintLevel>>({});
const reason = ref("");
const saving = ref(false);
const weekRangeMode = ref<"ALL" | "RANGE">("ALL");
const startWeek = ref(1);
const endWeek = ref(8);

function buildMask(s: number, e: number): number {
  let m = 0;
  for (let w = Math.max(1, s); w <= Math.min(30, e); w++) m |= 1 << (w - 1);
  return m;
}

const isAdmin = computed(() =>
  Boolean(me.value && ["SUPER_ADMIN", "COLLEGE_SCHEDULER", "DEPT_SCHEDULER", "MAJOR_SCHEDULER"].includes(me.value.role_code))
);
const canSwitchTeacher = computed(() => Boolean(isAdmin.value || me.value?.role_code === "TEACHING_LEAD"));

function slotId(day: number, period: number): number {
  return (day - 1) * 5 + period;
}

function toggleCell(id: number): void {
  const cur = selected[id];
  if (!cur) {
    selected[id] = "HARD";
  } else if (cur === "HARD") {
    selected[id] = "SOFT";
  } else {
    delete selected[id];
  }
}

function cellClass(id: number): string {
  const cur = selected[id];
  if (cur === "HARD") return "is-hard";
  if (cur === "SOFT") return "is-soft";
  return "is-free";
}

function cellLabel(id: number): string {
  const cur = selected[id];
  if (cur === "HARD") return "禁排";
  if (cur === "SOFT") return "偏好避";
  return "可排";
}

function clearAll(): void {
  Object.keys(selected).forEach((k) => delete selected[Number(k)]);
}

async function loadSavedGrid() {
  clearAll();
  if (!selectedTeacherId.value) return;
  try {
    const { data } = await apiClient.get("/constraints/teacher-unavailable", {
      params: { semester_id: semesterId.value, teacher_id: selectedTeacherId.value },
    });
    for (const row of data || []) {
      selected[row.timeslot_id] = row.constraint_level as ConstraintLevel;
      if (row.reason && !reason.value) reason.value = row.reason;
    }
  } catch {
    // 忽略未初始化场景
  }
}

async function handleToggleWindow(val: string | number | boolean) {
  try {
    await setTeacherUnavailWindow(Boolean(val));
    ElMessage.success(Boolean(val) ? "已开放教师自助禁排填报" : "已关闭教师自助禁排填报");
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "切换窗口状态失败");
  }
}

async function handleSubmit(): Promise<void> {
  const computedMask = weekRangeMode.value === "RANGE" ? buildMask(startWeek.value, endWeek.value) : undefined;
  const slots: TeacherUnavailableSlotPayload[] = Object.entries(selected).map(([id, level]) => ({
    timeslot_id: Number(id),
    constraint_level: level,
    reason: reason.value || undefined,
    week_mask: computedMask,
  }));
  saving.value = true;
  try {
    await saveTeacherUnavailableGrid(semesterId.value, selectedTeacherId.value, slots);
    ElMessage.success(`已提交 ${slots.length} 个禁排/偏好时段`);
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "提交失败，请检查权限或填报窗口状态");
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    const [profile, semRes, winRes] = await Promise.all([
      fetchMeApi(),
      apiClient.get("/resources/semesters"),
      fetchTeacherUnavailWindow(),
    ]);
    me.value = profile;
    windowOpen.value = winRes.is_open;
    const sems = semRes.data || [];
    const cur = sems.find((s: any) => s.is_current) || sems[0];
    if (cur) semesterId.value = cur.id;

    if (canSwitchTeacher.value) {
      const tRes = await apiClient.get("/resources/teachers");
      teachers.value = tRes.data || [];
      selectedTeacherId.value = teachers.value[0]?.id || profile.id;
    } else {
      selectedTeacherId.value = profile.id;
    }
    await loadSavedGrid();
  } catch {
    // 保留默认状态
  }
});
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.title { font-weight: 600; font-size: 16px; }
.subtitle { font-size: 12px; color: #6b7280; margin-top: 2px; }
.actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.legend-row { display: flex; gap: 16px; margin-bottom: 12px; font-size: 13px; color: #374151; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot.free { background: #e5e7eb; }
.dot.hard { background: #ef4444; }
.dot.soft { background: #f59e0b; }
.matrix-scroll { overflow-x: auto; }
.slot-matrix { width: 100%; border-collapse: collapse; min-width: 520px; }
.slot-matrix th, .slot-matrix td { border: 1px solid #e5e7eb; text-align: center; padding: 6px; }
.period-col { width: 80px; background: #f9fafb; font-weight: 600; font-size: 13px; }
.slot-cell { width: 100%; min-height: 44px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.15s ease; }
.slot-cell.is-free { background: #f8fafc; color: #64748b; }
.slot-cell.is-hard { background: #fee2e2; color: #b91c1c; }
.slot-cell.is-soft { background: #fef3c7; color: #b45309; }
.reason-row { margin-top: 12px; }
</style>
