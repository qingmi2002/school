<template>
  <el-card shadow="never" class="erp-panel">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="本学期选课与合班任务" name="tasks">
        <div class="bar">
          <div class="bar-left">
            <el-select v-model="filterCohortId" size="small" clearable placeholder="按班级筛选课程" style="width: 170px" @change="loadTasks">
              <el-option v-for="c in cohorts" :key="c.id" :label="`${c.cohort_name}(${c.student_count}人)`" :value="c.id" />
            </el-select>
            <el-button size="small" type="warning" :disabled="selectedTaskIds.length < 2" @click="handleMergeSelected">
              指定合班合并（已选 {{ selectedTaskIds.length }}）
            </el-button>
          </div>
          <div style="display: flex; gap: 8px">
            <el-button size="small" @click="cloneDialog = true">从历史学期复用</el-button>
            <el-button size="small" type="primary" @click="taskDialog = true">+ 新增班级选课 / 合班任务</el-button>
          </div>
        </div>

        <el-table :data="tasks" size="small" border stripe @selection-change="onSelectionChange">
          <el-table-column type="selection" width="42" />
          <el-table-column prop="course_name" label="课程名称" min-width="140">
            <template #default="{ row }">
              <strong>{{ row.course_name }}</strong>
              <span class="muted"> ({{ row.course_code }})</span>
            </template>
          </el-table-column>
          <el-table-column label="上课班级（单班/合班）" min-width="190">
            <template #default="{ row }">
              <el-tag :type="row.is_combined ? 'warning' : 'success'" size="small" style="margin-right: 6px">
                {{ row.is_combined ? "合班·流动教室" : "单班" }}
              </el-tag>
              <span>{{ row.cohort_names.join(" + ") }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_students" label="总人数" width="76" />
          <el-table-column prop="teacher_name" label="任课教师" width="100" />
          <el-table-column label="教室类型" width="110">
            <template #default="{ row }">{{ roomTypeLabel(row.required_room_type) }}</template>
          </el-table-column>
          <el-table-column label="学期总课时与有效周" min-width="170">
            <template #default="{ row }">
              <el-tag size="small" :type="row.hours_sufficient === false ? 'danger' : 'success'" style="margin-right: 4px">
                {{ row.planned_actual_hours || 0 }}/{{ row.total_hours || "-" }}学时
              </el-tag>
              <span class="muted">{{ row.effective_weeks_label || `${row.start_week}-${row.end_week}周` }} · 周{{ row.weekly_sessions }}次</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="handleDeleteTask(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="教师多课多班负荷" name="workload">
        <el-table :data="workloads" size="small" border stripe>
          <el-table-column prop="teacher_name" label="教师姓名" width="110" />
          <el-table-column label="权限级别" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="row.role_code === 'TEACHING_LEAD' ? 'warning' : 'info'">
                {{ row.role_code === "TEACHING_LEAD" ? "教研室主任" : "任课教师" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="所带课程" min-width="200">
            <template #default="{ row }">{{ row.courses.join("、") }}</template>
          </el-table-column>
          <el-table-column label="所带班级" min-width="200">
            <template #default="{ row }">{{ row.cohorts.join("、") }}</template>
          </el-table-column>
          <el-table-column prop="combined_task_count" label="合班任务" width="85" />
          <el-table-column prop="total_weekly_sessions" label="周总节次" width="90" />
          <el-table-column prop="total_semester_hours" label="学期总学时" width="100" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="课程库管理" name="courses">
        <div class="bar">
          <span class="muted">先维护课程库，再在「本学期选课与合班任务」中给班级勾选开课或指定合班</span>
          <el-button size="small" type="primary" @click="courseDialog = true">+ 新增课程</el-button>
        </div>
        <el-table :data="courses" size="small" border stripe>
          <el-table-column prop="course_code" label="课程代码" width="120" />
          <el-table-column prop="course_name" label="课程名称" min-width="160" />
          <el-table-column prop="course_category" label="类别" width="95" />
          <el-table-column label="默认教室类型" width="120">
            <template #default="{ row }">{{ roomTypeLabel(row.required_room_type) }}</template>
          </el-table-column>
          <el-table-column prop="default_weekly_sessions" label="默认周节次" width="95" />
          <el-table-column prop="default_total_hours" label="默认总学时" width="95" />
          <el-table-column label="允许合班" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.allow_combined ? 'success' : 'info'">
                {{ row.allow_combined ? "允许" : "仅单班" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="handleDeleteCourse(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="taskDialog" title="新增班级选课 / 指定合班教学任务" width="520px">
      <el-form :model="taskForm" label-width="96px" size="small">
        <el-form-item label="选择课程">
          <el-select v-model="taskForm.course_id" style="width: 100%" placeholder="从课程库选择">
            <el-option v-for="c in courses" :key="c.id" :label="`${c.course_name} (${c.course_code})`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="上课班级">
          <el-select v-model="taskForm.cohort_ids" multiple style="width: 100%" placeholder="单选=单班，多选=指定合班上课">
            <el-option v-for="c in cohorts" :key="c.id" :label="`${c.cohort_name} (${c.student_count}人)`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="任课教师">
          <el-select v-model="taskForm.teacher_id" style="width: 100%" placeholder="选择任课教师">
            <el-option v-for="t in teachers" :key="t.id" :label="`${t.real_name} (${t.username})`" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="教室类型">
          <el-select v-model="taskForm.required_room_type" style="width: 100%" clearable placeholder="默认跟随课程库">
            <el-option label="普通教室" value="NORMAL" />
            <el-option label="计算机机房" value="COMPUTER_LAB" />
            <el-option label="专业实验室" value="NETWORK_LAB" />
            <el-option label="实训室" value="TRAINING_ROOM" />
            <el-option label="阶梯/合班大教室" value="LECTURE_HALL" />
          </el-select>
        </el-form-item>
        <el-form-item label="总学时与周次">
          <el-input-number v-model="taskForm.total_hours" :min="4" :max="200" :step="2" style="width: 105px" />
          <span style="margin: 0 6px">学时 · 周</span>
          <el-input-number v-model="taskForm.weekly_sessions" :min="1" :max="6" style="width: 85px" />
          <span style="margin: 0 6px">次</span>
        </el-form-item>
        <el-form-item label="起止周与连堂">
          <el-input-number v-model="taskForm.start_week" :min="1" :max="24" style="width: 88px" />
          <span style="margin: 0 6px">至</span>
          <el-input-number v-model="taskForm.end_week" :min="1" :max="24" style="width: 88px" />
          <span style="margin: 0 10px 0 6px">周</span>
          <el-checkbox v-model="taskForm.prefer_consecutive">实验/上机连堂</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="taskDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleCreateTask">保存任务</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="courseDialog" title="新增课程" width="460px">
      <el-form :model="courseForm" label-width="100px" size="small">
        <el-form-item label="课程代码"><el-input v-model="courseForm.course_code" placeholder="如 MATH101" /></el-form-item>
        <el-form-item label="课程名称"><el-input v-model="courseForm.course_name" placeholder="如 高等数学" /></el-form-item>
        <el-form-item label="课程类别">
          <el-select v-model="courseForm.course_category" style="width: 100%">
            <el-option label="理论课 (THEORY)" value="THEORY" />
            <el-option label="实验/上机 (LAB)" value="LAB" />
            <el-option label="理实一体 (MIXED)" value="MIXED" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认教室类型">
          <el-select v-model="courseForm.required_room_type" style="width: 100%">
            <el-option label="普通教室" value="NORMAL" />
            <el-option label="计算机机房" value="COMPUTER_LAB" />
            <el-option label="专业实验室" value="NETWORK_LAB" />
            <el-option label="阶梯/合班大教室" value="LECTURE_HALL" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认周节次"><el-input-number v-model="courseForm.default_weekly_sessions" :min="1" :max="6" /></el-form-item>
        <el-form-item label="默认总学时"><el-input-number v-model="courseForm.default_total_hours" :min="4" :max="200" :step="2" /></el-form-item>
        <el-form-item label="允许合班"><el-switch v-model="courseForm.allow_combined" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="courseDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleCreateCourse">保存课程</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="cloneDialog" title="从历史学期一键复用开课任务" width="420px">
      <el-form label-width="90px" size="small">
        <el-form-item label="源学期">
          <el-select v-model="cloneForm.sourceId" style="width: 100%">
            <el-option v-for="s in semesters" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标学期">
          <el-select v-model="cloneForm.targetId" style="width: 100%">
            <el-option v-for="s in semesters" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="cloneDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleCloneSemester">开始复用</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  apiClient,
  cloneSemesterTasks,
  createCourse,
  createTeachingTask,
  deleteCourse,
  deleteTeachingTask,
  fetchCourses,
  fetchTeacherWorkload,
  fetchTeachingTasks,
  mergeTeachingTasks,
  type CourseItem,
  type TeacherWorkloadItem,
  type TeachingTaskItem,
} from "../api/client";

const activeTab = ref("tasks");
const courses = ref<CourseItem[]>([]);
const tasks = ref<TeachingTaskItem[]>([]);
const workloads = ref<TeacherWorkloadItem[]>([]);
const cohorts = ref<Array<{ id: number; cohort_name: string; student_count: number }>>([]);
const teachers = ref<Array<{ id: number; real_name: string; username: string }>>([]);
const filterCohortId = ref<number | undefined>(undefined);
const selectedTaskIds = ref<number[]>([]);

const taskDialog = ref(false);
const courseDialog = ref(false);
const cloneDialog = ref(false);
const semesters = ref<Array<{ id: number; name: string }>>([]);
const cloneForm = reactive({ sourceId: undefined as number | undefined, targetId: undefined as number | undefined });

const taskForm = reactive({
  course_id: undefined as number | undefined,
  cohort_ids: [] as number[],
  teacher_id: undefined as number | undefined,
  required_room_type: "",
  weekly_sessions: 2,
  total_hours: 32,
  prefer_consecutive: false,
  start_week: 1,
  end_week: 18,
});

const courseForm = reactive({
  course_code: "",
  course_name: "",
  course_category: "THEORY",
  required_room_type: "NORMAL",
  default_weekly_sessions: 2,
  default_total_hours: 32,
  allow_combined: true,
});

function roomTypeLabel(t?: string | null) {
  const m: Record<string, string> = {
    NORMAL: "普通教室",
    COMPUTER_LAB: "计算机机房",
    NETWORK_LAB: "专业实验室",
    TRAINING_ROOM: "实训室",
    LECTURE_HALL: "阶梯大教室",
  };
  return t ? m[t] || t : "自动适配";
}

function onSelectionChange(rows: TeachingTaskItem[]) {
  selectedTaskIds.value = rows.map((r) => r.id);
}

async function loadTasks() {
  tasks.value = await fetchTeachingTasks(filterCohortId.value ? { cohort_id: filterCohortId.value } : undefined);
  workloads.value = await fetchTeacherWorkload();
}

async function loadAll() {
  const [cList, cohortRes, teacherRes] = await Promise.all([
    fetchCourses(),
    apiClient.get("/resources/cohorts"),
    apiClient.get("/resources/teachers"),
  ]);
  courses.value = cList;
  cohorts.value = cohortRes.data;
  teachers.value = teacherRes.data;
  const semRes = await apiClient.get('/resources/semesters');
  semesters.value = semRes.data || [];
  await loadTasks();
}

async function handleCreateCourse() {
  if (!courseForm.course_code || !courseForm.course_name) {
    ElMessage.warning("请填写课程代码与名称");
    return;
  }
  await createCourse({ ...courseForm });
  ElMessage.success("课程已保存");
  courseDialog.value = false;
  courseForm.course_code = "";
  courseForm.course_name = "";
  await loadAll();
}

async function handleDeleteCourse(id: number) {
  await deleteCourse(id);
  ElMessage.success("课程已删除");
  await loadAll();
}

async function handleCreateTask() {
  if (!taskForm.course_id || !taskForm.teacher_id || taskForm.cohort_ids.length === 0) {
    ElMessage.warning("请选择课程、上课班级和任课教师");
    return;
  }
  await createTeachingTask({
    course_id: taskForm.course_id,
    teacher_id: taskForm.teacher_id,
    cohort_ids: taskForm.cohort_ids,
    required_room_type: taskForm.required_room_type || undefined,
    weekly_sessions: taskForm.weekly_sessions,
    total_hours: taskForm.total_hours,
    prefer_consecutive: taskForm.prefer_consecutive,
    start_week: taskForm.start_week,
    end_week: taskForm.end_week,
  });
  ElMessage.success("教学任务已保存");
  taskDialog.value = false;
  taskForm.cohort_ids = [];
  await loadTasks();
}

async function handleMergeSelected() {
  try {
    await mergeTeachingTasks(selectedTaskIds.value);
    ElMessage.success("已合并为合班任务，排课时将自动匹配大容量流动教室");
    selectedTaskIds.value = [];
    await loadTasks();
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "合并失败，请确认所选为同一门课程");
  }
}

async function handleDeleteTask(id: number) {
  await deleteTeachingTask(id);
  ElMessage.success("已删除任务");
  await loadTasks();
}

async function handleCloneSemester() {
  if (!cloneForm.sourceId || !cloneForm.targetId) {
    ElMessage.warning('请选择源学期和目标学期');
    return;
  }
  try {
    const r = await cloneSemesterTasks(cloneForm.sourceId, cloneForm.targetId);
    ElMessage.success(`复用完成：新增 ${r.cloned_count} 条，跳过重复 ${r.skipped_count} 条`);
    cloneDialog.value = false;
    await loadTasks();
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '复用失败');
  }
}

onMounted(loadAll);
</script>

<style scoped>
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 8px; }
.bar-left { display: flex; align-items: center; gap: 8px; }
.muted { color: #64748b; font-size: 12px; }
</style>
