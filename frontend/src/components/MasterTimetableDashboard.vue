<template>
  <div class="dash-wrap">
    <el-card shadow="never">
      <div class="bar">
        <strong>全院二维总课表与排课质量看板</strong>
        <el-select v-model="selectedPlanId" size="small" style="width: 240px" @change="loadAnalytics">
          <el-option v-for="p in plans" :key="p.id" :label="`${p.is_published ? '[已发布] ' : ''}${p.plan_name}`" :value="p.id" />
        </el-select>
      </div>

      <div v-if="stats" class="kpi-row">
        <div class="kpi"><div class="k-label">排课完成率</div><div class="k-val">{{ stats.completion_rate }}%</div></div>
        <div class="kpi"><div class="k-label">教室平均利用率</div><div class="k-val">{{ stats.avg_room_utilization }}%</div></div>
        <div class="kpi"><div class="k-label">已排总课次</div><div class="k-val">{{ stats.scheduled_sessions }}</div></div>
        <div class="kpi"><div class="k-label">合班课次</div><div class="k-val">{{ stats.combined_sessions_count }}</div></div>
        <div class="kpi"><div class="k-label">晚间课次</div><div class="k-val">{{ stats.evening_sessions_count }}</div></div>
      </div>

      <el-tabs v-model="tab" style="margin-top: 12px">
        <el-tab-pane label="全院班级二维总课表" name="matrix">
          <el-table :data="stats?.master_matrix || []" size="small" border stripe max-height="480">
            <el-table-column prop="cohort_name" label="班级" width="120" fixed />
            <el-table-column v-for="col in dayCols" :key="col.key" :label="col.label" min-width="150">
              <template #default="{ row }">
                <span class="cell-txt">{{ row.slots[col.key] || "-" }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="教室/机房利用率排行" name="util">
          <el-table :data="stats?.room_utilization || []" size="small" border stripe>
            <el-table-column prop="room_code" label="教室编号" width="120" />
            <el-table-column prop="building" label="教学楼" width="140" />
            <el-table-column prop="room_type" label="类型" width="130" />
            <el-table-column prop="used_slots" label="周占用大节" width="100" />
            <el-table-column label="利用率">
              <template #default="{ row }">
                <el-progress :percentage="Math.min(100, row.utilization_pct)" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchPlanAnalytics, fetchSchedulePlans, type PlanAnalyticsResponse, type SchedulePlanSummary } from "../api/client";

const tab = ref("matrix");
const plans = ref<SchedulePlanSummary[]>([]);
const selectedPlanId = ref<number | undefined>(undefined);
const stats = ref<PlanAnalyticsResponse | null>(null);

const dayCols = [1, 2, 3, 4, 5].flatMap((d) =>
  [1, 2, 3, 4].map((p) => ({
    key: `${d}-${p}`,
    label: `周${["一", "二", "三", "四", "五"][d - 1]}·${p * 2 - 1}-${p * 2}节`,
  }))
);

async function loadAnalytics() {
  if (!selectedPlanId.value) return;
  stats.value = await fetchPlanAnalytics(selectedPlanId.value);
}

onMounted(async () => {
  plans.value = await fetchSchedulePlans();
  if (plans.value.length) {
    selectedPlanId.value = plans.value[0].id;
    await loadAnalytics();
  }
});
</script>

<style scoped>
.bar { display: flex; justify-content: space-between; align-items: center; }
.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 12px; }
.kpi { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; }
.k-label { font-size: 12px; color: #64748b; }
.k-val { font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 4px; }
.cell-txt { font-size: 12px; color: #334155; }
</style>
