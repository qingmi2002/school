<template>
  <el-card shadow="never">
    <template #header>
      <div class="header-bar">
        <div>
          <div class="title">
            {{ schedule?.owner_type === "STUDENT" ? "我的班级课表" : "我的个人教学课表" }}
          </div>
          <div class="sub">{{ schedule?.owner_name }} · {{ schedule?.sub_title }}</div>
        </div>
        <div class="actions">
          <el-button size="small" @click="loadData">刷新课表</el-button>
          <el-button v-if="schedule?.plan_id" type="primary" size="small" @click="downloadIcs">
            订阅到手机日历 (.ics)
          </el-button>
        </div>
      </div>
    </template>

    <div class="table-wrap">
      <table class="week-table">
        <thead>
          <tr>
            <th class="p-col">节次</th>
            <th v-for="d in days" :key="d.v">{{ d.l }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in periods" :key="p.v">
            <td class="p-col">{{ p.l }}</td>
            <td v-for="d in days" :key="`${d.v}-${p.v}`" class="cell">
              <div
                v-for="(c, idx) in cardsAt(d.v, p.v)"
                :key="idx"
                class="course-box"
                :class="c.is_public_lock ? 'is-pub' : 'is-pro'"
              >
                <div class="c-name">
                  {{ c.course_name }}
                  <el-tag v-if="c.week_type !== 0" size="small" :type="c.week_type === 1 ? 'warning' : 'success'">
                    {{ c.week_type === 1 ? "单周" : "双周" }}
                  </el-tag>
                </div>
                <div class="c-meta">📍 {{ c.building }} {{ c.room_code }}</div>
                <div class="c-meta">👨‍🏫 {{ c.teacher_name }}</div>
                <div v-if="c.cohort_names.length" class="c-meta">🎓 {{ c.cohort_names.join(" / ") }}</div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchMySchedule, type PersonalCourseCard, type PersonalSchedule } from "../api/client";

const days = [
  { v: 1, l: "周一" },
  { v: 2, l: "周二" },
  { v: 3, l: "周三" },
  { v: 4, l: "周四" },
  { v: 5, l: "周五" },
];
const periods = [
  { v: 1, l: "1-2节" },
  { v: 2, l: "3-4节" },
  { v: 3, l: "5-6节" },
  { v: 4, l: "7-8节" },
  { v: 5, l: "9-10节" },
];

const schedule = ref<PersonalSchedule | null>(null);

async function loadData(): Promise<void> {
  schedule.value = await fetchMySchedule();
}

function cardsAt(day: number, period: number): PersonalCourseCard[] {
  return (schedule.value?.cards || []).filter((c) => c.day_of_week === day && c.period_index === period);
}

function downloadIcs(): void {
  if (!schedule.value?.plan_id) return;
  window.open(`/api/v1/export/plans/${schedule.value.plan_id}/calendar.ics`, "_blank");
}

onMounted(() => {
  void loadData();
});
</script>

<style scoped>
.header-bar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.title { font-size: 16px; font-weight: 600; color: #0f172a; }
.sub { font-size: 12px; color: #64748b; margin-top: 2px; }
.actions { display: flex; gap: 8px; }
.table-wrap { overflow-x: auto; }
.week-table { width: 100%; border-collapse: collapse; min-width: 640px; table-layout: fixed; }
.week-table th, .week-table td { border: 1px solid #e2e8f0; padding: 8px; vertical-align: top; }
.week-table th { background: #f8fafc; font-weight: 600; color: #334155; }
.p-col { width: 76px; text-align: center; background: #f8fafc; font-size: 12px; font-weight: 600; }
.cell { height: 108px; }
.course-box { border-radius: 6px; padding: 7px 8px; margin-bottom: 6px; font-size: 12px; border-left: 4px solid #2563eb; background: #eff6ff; }
.course-box.is-pub { border-left-color: #64748b; background: #f1f5f9; }
.c-name { font-weight: 600; color: #0f172a; margin-bottom: 4px; display: flex; justify-content: space-between; gap: 4px; }
.c-meta { font-size: 11px; color: #475569; margin-top: 2px; }
</style>
