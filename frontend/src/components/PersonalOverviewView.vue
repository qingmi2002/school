<template>
  <div v-if="data" class="ov-wrap">
    <template v-if="data.view_type === 'STUDENT'">
      <el-card shadow="never">
        <div class="ov-head">
          <div>
            <h3>欢迎，{{ data.profile.real_name }} 同学</h3>
            <div class="muted">
              学号：{{ data.profile.username }} · 所属：{{ data.profile.org_node_name }} · 当前学期：{{ data.semester_name }}
            </div>
          </div>
          <div style="display: flex; gap: 8px">
            <el-button type="primary" size="small" @click="$emit('navigate', 'my-schedule')">查看我的课表</el-button>
            <el-button size="small" @click="$emit('navigate', 'free-rooms')">查空教室自习</el-button>
          </div>
        </div>

        <div v-if="data.cohort_lifecycle" class="kpi-row">
          <div class="kpi"><div class="kl">行政班级</div><div class="kv">{{ data.cohort_lifecycle.cohort_name }}</div></div>
          <div class="kpi"><div class="kl">入学—毕业周期</div><div class="kv">{{ data.cohort_lifecycle.enroll_year }} — {{ data.cohort_lifecycle.graduation_year }}届（{{ data.cohort_lifecycle.study_years }}年制）</div></div>
          <div class="kpi"><div class="kl">班级固定教室</div><div class="kv">{{ data.cohort_lifecycle.fixed_room_code }}</div></div>
          <div class="kpi"><div class="kl">本学期修读课程</div><div class="kv">{{ data.my_courses.length }} 门</div></div>
        </div>

        <el-alert
          v-if="data.block_notices?.length"
          type="warning"
          :title="`本学期整周实训 / 考试安排：${data.block_notices.join('；')}`"
          show-icon
          :closable="false"
          style="margin-top: 12px"
        />

        <el-table :data="data.my_courses" size="small" border stripe style="margin-top: 12px">
          <el-table-column prop="course_code" label="课程代码" width="120" />
          <el-table-column prop="course_name" label="课程名称" min-width="180" />
          <el-table-column prop="teacher_name" label="任课教师" width="120" />
          <el-table-column prop="weekly_sessions" label="周节次" width="90" />
          <el-table-column prop="total_hours" label="学期总学时" width="110" />
          <el-table-column label="授课形式" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_combined ? 'warning' : 'success'">{{ row.is_combined ? "合班课" : "单班课" }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <template v-else>
      <el-card shadow="never">
        <div class="ov-head">
          <div>
            <h3>欢迎，{{ data.profile.real_name }} 老师</h3>
            <div class="muted">
              工号：{{ data.profile.username }} · 所属：{{ data.profile.org_node_name }} · 当前学期：{{ data.semester_name }}
              <el-tag v-for="m in data.profile.managed_nodes || []" :key="m.org_node_id" size="small" type="warning" style="margin-left: 6px">
                {{ m.org_node_name }} · {{ m.title_name }}
              </el-tag>
            </div>
          </div>
          <div style="display: flex; gap: 8px">
            <el-button type="primary" size="small" @click="$emit('navigate', 'my-schedule')">我的课表</el-button>
            <el-button type="warning" size="small" @click="$emit('navigate', 'teacher-grid')">禁排填报</el-button>
            <el-button size="small" @click="$emit('navigate', 'free-rooms')">查空教室</el-button>
          </div>
        </div>

        <div class="kpi-row">
          <div class="kpi"><div class="kl">本学期任教课程</div><div class="kv">{{ data.my_courses.length }} 项</div></div>
          <div class="kpi"><div class="kl">周总大节</div><div class="kv">{{ data.total_weekly_sessions }} 节</div></div>
          <div class="kpi"><div class="kl">学期总学时</div><div class="kv">{{ data.total_semester_hours }} 学时</div></div>
          <div class="kpi"><div class="kl">禁排自助填报窗口</div><div class="kv">{{ data.unavail_window_open ? "开放中" : "已关闭" }}</div></div>
        </div>

        <el-table :data="data.my_courses" size="small" border stripe style="margin-top: 12px">
          <el-table-column prop="course_code" label="课程代码" width="120" />
          <el-table-column prop="course_name" label="课程名称" min-width="180" />
          <el-table-column label="任教班级" min-width="200">
            <template #default="{ row }">{{ (row.cohorts || []).join(" + ") }}</template>
          </el-table-column>
          <el-table-column prop="weekly_sessions" label="周节次" width="90" />
          <el-table-column prop="total_hours" label="总学时" width="95" />
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchMyPersonalOverview } from "../api/client";

defineEmits<{ (e: "navigate", menu: string): void }>();
const data = ref<any>(null);

onMounted(async () => {
  data.value = await fetchMyPersonalOverview();
});
</script>

<style scoped>
.ov-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.ov-head h3 { margin: 0 0 4px 0; font-size: 16px; }
.muted { color: #64748b; font-size: 12px; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 12px; }
.kpi { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; }
.kl { font-size: 12px; color: #64748b; }
.kv { font-size: 17px; font-weight: 700; color: #0f172a; margin-top: 4px; }
</style>
