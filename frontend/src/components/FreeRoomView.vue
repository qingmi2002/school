<template>
  <el-card shadow="never">
    <template #header>
      <div class="bar">
        <strong>空教室实时查询（按周次 / 星期 / 节次精准检索）</strong>
        <el-tag type="success" size="small" v-if="result">
          共 {{ result.total_rooms }} 间 · 空闲 {{ result.free_count }} 间 · 占用 {{ result.occupied_count }} 间
        </el-tag>
      </div>
    </template>

    <div class="filters">
      <span>第</span>
      <el-input-number v-model="q.week_no" :min="1" :max="24" size="small" style="width: 90px" />
      <span>周</span>
      <el-select v-model="q.day_of_week" size="small" style="width: 100px">
        <el-option v-for="d in 7" :key="d" :label="`周${['一','二','三','四','五','六','日'][d-1]}`" :value="d" />
      </el-select>
      <el-select v-model="q.period_index" size="small" style="width: 110px">
        <el-option label="1-2节" :value="1" />
        <el-option label="3-4节" :value="2" />
        <el-option label="5-6节" :value="3" />
        <el-option label="7-8节" :value="4" />
        <el-option label="9-10节" :value="5" />
      </el-select>
      <el-select v-model="q.room_type" size="small" clearable placeholder="全部类型" style="width: 130px">
        <el-option label="普通教室" value="NORMAL" />
        <el-option label="计算机机房" value="COMPUTER_LAB" />
        <el-option label="专业实验室" value="NETWORK_LAB" />
        <el-option label="阶梯大教室" value="LECTURE_HALL" />
      </el-select>
      <el-input-number v-model="q.min_capacity" :min="0" :max="500" :step="10" size="small" style="width: 120px" />
      <span class="muted">座以上</span>
      <el-button type="primary" size="small" :loading="loading" @click="handleSearch">查询空教室</el-button>
    </div>

    <el-table :data="result?.free_rooms || []" size="small" border stripe style="margin-top: 12px">
      <el-table-column prop="room_code" label="教室编号" width="120" />
      <el-table-column prop="building" label="教学楼" width="140" />
      <el-table-column prop="room_type" label="教室类型" width="130" />
      <el-table-column prop="capacity" label="座位数" width="90" />
      <el-table-column label="使用模式" width="160">
        <template #default="{ row }">
          <el-tag size="small" :type="row.usage_mode === 'FIXED' ? 'warning' : 'success'">
            {{ row.usage_mode === "FIXED" ? `固定班(${row.fixed_cohort_name || ""})` : "流动可借用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sharing_policy" label="共享策略" />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { queryFreeRooms, type FreeRoomsResponse } from "../api/client";

const q = reactive({ week_no: 1, day_of_week: 1, period_index: 1, room_type: "", min_capacity: 0 });
const loading = ref(false);
const result = ref<FreeRoomsResponse | null>(null);

async function handleSearch() {
  loading.value = true;
  try {
    result.value = await queryFreeRooms({
      week_no: q.week_no,
      day_of_week: q.day_of_week,
      period_index: q.period_index,
      room_type: q.room_type || undefined,
      min_capacity: q.min_capacity,
    });
  } finally {
    loading.value = false;
  }
}

onMounted(handleSearch);
</script>

<style scoped>
.bar { display: flex; justify-content: space-between; align-items: center; }
.filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.muted { color: #64748b; font-size: 12px; }
</style>
