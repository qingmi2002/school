<template>
  <el-card shadow="never">
    <el-tabs v-model="tab" type="card">
      <!-- 1. 教学楼管理 -->
      <el-tab-pane label="教学楼" name="buildings">
        <div class="bar">
          <span class="tip">独立教学楼数据（关联校区/组织，供教室绑定与跨校区通勤校验）</span>
          <el-button type="primary" size="small" @click="bldgDialog = true">+ 新增教学楼</el-button>
        </div>
        <el-table :data="buildings" border stripe size="small">
          <el-table-column prop="building_code" label="楼宇编码" width="120" />
          <el-table-column prop="building_name" label="教学楼名称" width="160" />
          <el-table-column prop="floors" label="楼层数" width="80" />
          <el-table-column prop="remark" label="备注" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="onDeleteBldg(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 2. 教室管理（固定 / 流动） -->
      <el-tab-pane label="教室" name="rooms">
        <div class="bar">
          <el-radio-group v-model="roomFilter" size="small">
            <el-radio-button value="ALL">全部</el-radio-button>
            <el-radio-button value="FIXED">固定教室</el-radio-button>
            <el-radio-button value="FLOATING">流动教室</el-radio-button>
          </el-radio-group>
          <el-button type="primary" size="small" @click="roomDialog = true">+ 新增教室</el-button>
        </div>
        <el-table :data="filteredRooms" border stripe size="small">
          <el-table-column prop="room_code" label="教室编号" width="110" />
          <el-table-column prop="building" label="所属教学楼" width="130" />
          <el-table-column prop="capacity" label="座位数" width="80" />
          <el-table-column label="使用性质" width="140">
            <template #default="{ row }">
              <el-select v-model="row.usage_mode" size="small" @change="onSwitchUsage(row)">
                <el-option label="固定教室" value="FIXED" />
                <el-option label="流动教室" value="FLOATING" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="room_type" label="场地类型" width="120" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="onDeleteRoom(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 3. 教师管理 -->
      <el-tab-pane label="教师" name="teachers">
        <div class="bar">
          <span class="tip">任课教师数据库维护</span>
          <el-button type="primary" size="small" @click="teacherDialog = true">+ 新增教师</el-button>
        </div>
        <el-table :data="teachers" border stripe size="small">
          <el-table-column prop="username" label="工号" width="130" />
          <el-table-column prop="real_name" label="姓名" />
          <el-table-column prop="org_node_id" label="所属组织ID" width="110" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="onDeleteTeacher(row.id)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 4. 班级管理 -->
      <el-tab-pane label="班级" name="cohorts">
        <div class="bar">
          <span class="tip">行政班数据库维护</span>
          <el-button type="primary" size="small" @click="cohortDialog = true">+ 新增班级</el-button>
        </div>
        <el-table :data="cohorts" border stripe size="small">
          <el-table-column prop="cohort_code" label="班号" width="120" />
          <el-table-column prop="cohort_name" label="班级名称" />
          <el-table-column prop="grade_year" label="年级" width="80" />
          <el-table-column prop="student_count" label="人数" width="80" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="onDeleteCohort(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 5. 学生管理 -->
      <el-tab-pane label="学生" name="students">
        <div class="bar">
          <span class="tip">学生账号绑定行政班</span>
          <el-button type="primary" size="small" @click="studentDialog = true">+ 新增学生</el-button>
        </div>
        <el-table :data="students" border stripe size="small">
          <el-table-column prop="username" label="学号" width="130" />
          <el-table-column prop="real_name" label="姓名" />
          <el-table-column label="所属班级">
            <template #default="{ row }">{{ cohortName(row.cohort_id) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="onDeleteStudent(row.id)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="bldgDialog" title="新增教学楼" width="400px">
      <el-form :model="bldgForm" label-width="80px" size="small">
        <el-form-item label="楼宇编码"><el-input v-model="bldgForm.building_code" placeholder="如 BLDG_01" /></el-form-item>
        <el-form-item label="楼宇名称"><el-input v-model="bldgForm.building_name" placeholder="如 第一教学楼" /></el-form-item>
        <el-form-item label="楼层数"><el-input-number v-model="bldgForm.floors" :min="1" :max="30" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="bldgForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="bldgDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitBldg">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="roomDialog" title="新增教室" width="440px">
      <el-form :model="roomForm" label-width="84px" size="small">
        <el-form-item label="教室编号"><el-input v-model="roomForm.room_code" placeholder="如 A-305" /></el-form-item>
        <el-form-item label="所属教学楼">
          <el-select v-if="buildings.length" v-model="roomForm.building_id" style="width: 100%" placeholder="选择教学楼">
            <el-option v-for="b in buildings" :key="b.id" :label="b.building_name" :value="b.id" />
          </el-select>
          <el-input v-else v-model="roomForm.building" placeholder="如 第一教学楼" />
        </el-form-item>
        <el-form-item label="座位数"><el-input-number v-model="roomForm.capacity" :min="10" :max="500" /></el-form-item>
        <el-form-item label="使用性质">
          <el-radio-group v-model="roomForm.usage_mode">
            <el-radio value="FLOATING">流动教室</el-radio>
            <el-radio value="FIXED">固定教室</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="roomForm.usage_mode === 'FIXED'" label="绑定班级">
          <el-select v-model="roomForm.fixed_cohort_id" style="width: 100%">
            <el-option v-for="c in cohorts" :key="c.id" :label="c.cohort_name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="roomDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitRoom">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="teacherDialog" title="新增教师" width="380px">
      <el-form :model="teacherForm" label-width="70px" size="small">
        <el-form-item label="工号"><el-input v-model="teacherForm.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="teacherForm.real_name" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="teacherDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitTeacher">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="cohortDialog" title="新增班级" width="380px">
      <el-form :model="cohortForm" label-width="70px" size="small">
        <el-form-item label="班号"><el-input v-model="cohortForm.cohort_code" /></el-form-item>
        <el-form-item label="班名"><el-input v-model="cohortForm.cohort_name" /></el-form-item>
        <el-form-item label="人数"><el-input-number v-model="cohortForm.student_count" :min="1" :max="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="cohortDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitCohort">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="studentDialog" title="新增学生" width="380px">
      <el-form :model="studentForm" label-width="70px" size="small">
        <el-form-item label="学号"><el-input v-model="studentForm.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="studentForm.real_name" /></el-form-item>
        <el-form-item label="班级">
          <el-select v-model="studentForm.cohort_id" style="width: 100%">
            <el-option v-for="c in cohorts" :key="c.id" :label="c.cohort_name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="studentDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitStudent">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  addBuilding,
  addClassroom,
  addCohort,
  addStudent,
  addTeacher,
  deleteBuilding,
  deleteClassroom,
  deleteCohort,
  deleteStudent,
  deleteTeacher,
  getBuildings,
  getClassrooms,
  getCohorts,
  getStudents,
  getTeachers,
  switchClassroomUsage,
  type BuildingItem,
  type ClassroomItem,
  type CohortItem,
  type StudentItem,
  type TeacherItem,
} from "../api/resources";

const props = defineProps<{ activeOrgId: number }>();

const tab = ref("buildings");
const roomFilter = ref("ALL");
const buildings = ref<BuildingItem[]>([]);
const rooms = ref<ClassroomItem[]>([]);
const teachers = ref<TeacherItem[]>([]);
const cohorts = ref<CohortItem[]>([]);
const students = ref<StudentItem[]>([]);

const bldgDialog = ref(false);
const roomDialog = ref(false);
const teacherDialog = ref(false);
const cohortDialog = ref(false);
const studentDialog = ref(false);

const bldgForm = reactive({ building_code: "", building_name: "", floors: 5, remark: "" });
const roomForm = reactive({ room_code: "", building: "第一教学楼", building_id: null as number | null, capacity: 60, usage_mode: "FLOATING" as "FIXED" | "FLOATING", fixed_cohort_id: null as number | null });
const teacherForm = reactive({ username: "", real_name: "" });
const cohortForm = reactive({ cohort_code: "", cohort_name: "", grade_year: 2026, student_count: 45 });
const studentForm = reactive({ username: "", real_name: "", cohort_id: 1 });

const filteredRooms = computed(() =>
  roomFilter.value === "ALL" ? rooms.value : rooms.value.filter((r) => r.usage_mode === roomFilter.value)
);

function cohortName(id: number | null): string {
  return cohorts.value.find((c) => c.id === id)?.cohort_name || "-";
}

async function reloadAll(): Promise<void> {
  const [b, rm, t, c, s] = await Promise.all([getBuildings(), getClassrooms(), getTeachers(), getCohorts(), getStudents()]);
  buildings.value = b;
  rooms.value = rm;
  teachers.value = t;
  cohorts.value = c;
  students.value = s;
  if (b[0] && !roomForm.building_id) roomForm.building_id = b[0].id;
  if (c[0]) studentForm.cohort_id = c[0].id;
}

async function submitBldg(): Promise<void> {
  await addBuilding({ ...bldgForm, campus_org_id: props.activeOrgId || 1 });
  bldgDialog.value = false;
  bldgForm.building_code = "";
  bldgForm.building_name = "";
  ElMessage.success("教学楼已入库");
  await reloadAll();
}

async function onSwitchUsage(row: ClassroomItem): Promise<void> {
  await switchClassroomUsage(row.id, row.usage_mode, row.fixed_cohort_id);
  ElMessage.success(`${row.room_code} 已切换`);
}

async function submitRoom(): Promise<void> {
  await addClassroom({ ...roomForm, owner_org_id: props.activeOrgId || 1, room_type: "NORMAL", sharing_policy: "IDLE_BORROW", env_tags: [] });
  roomDialog.value = false;
  roomForm.room_code = "";
  ElMessage.success("教室已入库");
  await reloadAll();
}

async function submitTeacher(): Promise<void> {
  await addTeacher({ ...teacherForm, org_node_id: props.activeOrgId || 1 });
  teacherDialog.value = false;
  teacherForm.username = "";
  teacherForm.real_name = "";
  ElMessage.success("教师已入库");
  await reloadAll();
}

async function submitCohort(): Promise<void> {
  await addCohort({ ...cohortForm, org_node_id: props.activeOrgId || 1 });
  cohortDialog.value = false;
  cohortForm.cohort_code = "";
  cohortForm.cohort_name = "";
  ElMessage.success("班级已入库");
  await reloadAll();
}

async function submitStudent(): Promise<void> {
  await addStudent({ ...studentForm, org_node_id: props.activeOrgId || 1 });
  studentDialog.value = false;
  studentForm.username = "";
  studentForm.real_name = "";
  ElMessage.success("学生已入库");
  await reloadAll();
}

async function onDeleteBldg(id: number): Promise<void> { await deleteBuilding(id); await reloadAll(); }
async function onDeleteRoom(id: number): Promise<void> { await deleteClassroom(id); await reloadAll(); }
async function onDeleteTeacher(id: number): Promise<void> { await deleteTeacher(id); await reloadAll(); }
async function onDeleteCohort(id: number): Promise<void> { await deleteCohort(id); await reloadAll(); }
async function onDeleteStudent(id: number): Promise<void> { await deleteStudent(id); await reloadAll(); }

onMounted(() => { void reloadAll(); });
</script>

<style scoped>
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.tip { font-size: 12px; color: #606266; }
</style>
