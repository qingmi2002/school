<template>
  <el-card shadow="never" class="grid-card">
    <template #header>
      <div class="card-header">
        <div>
          <div class="title">教师禁排与偏好时间填报（微信 H5 适配）</div>
          <div class="subtitle">点击网格循环切换：空闲 → 绝对禁排（红） → 尽量不排（橙）</div>
        </div>
        <div class="actions">
          <el-button size="small" @click="clearAll">清空</el-button>
          <el-button type="primary" size="small" :loading="saving" @click="handleSubmit">
            提交禁排
          </el-button>
        </div>
      </div>
    </template>

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

    <div class="reason-row">
      <el-input
        v-model="reason"
        placeholder="选填禁排原因（如：教研室例会、跨校区通勤、科研项目）"
        clearable
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  saveTeacherUnavailableGrid,
  type ConstraintLevel,
  type TeacherUnavailableSlotPayload,
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

const selected = reactive<Record<number, ConstraintLevel>>({});
const reason = ref("");
const saving = ref(false);

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

async function handleSubmit(): Promise<void> {
  const slots: TeacherUnavailableSlotPayload[] = Object.entries(selected).map(([id, level]) => ({
    timeslot_id: Number(id),
    constraint_level: level,
    reason: reason.value || undefined,
  }));
  saving.value = true;
  try {
    await saveTeacherUnavailableGrid(1, 1, slots);
    ElMessage.success(`已提交 ${slots.length} 个禁排/偏好时段`);
  } catch {
    ElMessage.warning(`后端未初始化基础数据时仅作前端校验（已勾选 ${slots.length} 个时段）`);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.title {
  font-weight: 600;
  font-size: 16px;
}
.subtitle {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}
.legend-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 13px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot.free { background: #e5e7eb; }
.dot.hard { background: #ef4444; }
.dot.soft { background: #f59e0b; }
.matrix-scroll {
  overflow-x: auto;
}
.slot-matrix {
  width: 100%;
  border-collapse: collapse;
  min-width: 320px;
}
.slot-matrix th,
.slot-matrix td {
  border: 1px solid #e5e7eb;
  padding: 6px;
  text-align: center;
}
.period-col {
  width: 72px;
  background: #f9fafb;
  font-size: 12px;
  font-weight: 500;
}
.slot-cell {
  width: 100%;
  min-height: 44px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s ease;
}
.slot-cell.is-free {
  background: #f3f4f6;
  color: #6b7280;
}
.slot-cell.is-hard {
  background: #fee2e2;
  color: #b91c1c;
  font-weight: 600;
}
.slot-cell.is-soft {
  background: #fef3c7;
  color: #b45309;
  font-weight: 600;
}
.reason-row {
  margin-top: 14px;
}
</style>
