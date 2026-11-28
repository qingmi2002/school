<template>
  <div class="split-layout">
    <el-card shadow="never" class="sub-nav">
      <div class="sub-title">按归属与教学楼导航</div>
      <div class="nav-item" :class="{ active: scopeFilter === 'ALL' }" @click="scopeFilter = 'ALL'">全部教室</div>
      <div class="nav-item" :class="{ active: scopeFilter === 'PUBLIC_POOL' }" @click="scopeFilter = 'PUBLIC_POOL'">公共教室池</div>
      <div class="nav-item" :class="{ active: scopeFilter === 'FIXED' }" @click="scopeFilter = 'FIXED'">固定班级专用教室</div>
      <div class="sub-title" style="margin-top: 12px">按教学楼</div>
      <div
        v-for="b in buildings"
        :key="b.id"
        class="nav-item"
        :class="{ active: scopeFilter === `BLD:${b.building_name}` }"
        @click="scopeFilter = `BLD:${b.building_name}`"
      >
        {{ b.building_name }}
      </div>
    </el-card>

    <el-card shadow="never" class="sub-main">
      <el-tabs v-model="tab">
        <el-tab-pane label="教室台账与导入导出" name="list">
          <div class="bar">
            <span class="muted">共 {{ filteredRooms.length }} 间教室</span>
            <div style="display: flex; gap: 8px">
              <el-button size="small" @click="downloadDomainExcel('classrooms')">导出教室 Excel</el-button>
              <el-button size="small" @click="bldDialog = true">+ 新增教学楼</el-button>
              <el-button size="small" type="primary" @click="roomDialog = true">+ 新增教室</el-button>
            </div>
          </div>
          <el-table :data="filteredRooms" size="small" border stripe>
            <el-table-column prop="room_code" label="教室编号" width="110" />
            <el-table-column prop="building" label="教学楼" width="130" />
            <el-table-column prop="room_type" label="教室类型" width="130" />
            <el-table-column prop="capacity" label="座位数" width="80" />
            <el-table-column label="固定 / 流动" width="130">
              <template #default="{ row }">
                <el-tag size="small" :type="row.usage_mode === 'FIXED' ? 'warning' : 'success'">
                  {{ row.usage_mode === "FIXED" ? "固定班独占" : "流动教室" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="sharing_policy" label="共享策略" width="120" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button link type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="空教室实时查询" name="free">
          <FreeRoomView />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="roomDialog" title="新增教室" width="440px">
      <el-form :model="roomForm" label-width="88px" size="small">
        <el-form-item label="教室编号"><el-input v-model="roomForm.room_code" placeholder="如 A-305" /></el-form-item>
        <el-form-item label="所属教学楼"><el-input v-model="roomForm.building" placeholder="如 第一教学楼" /></el-form-item>
        <el-form-item label="教室类型">
          <el-select v-model="roomForm.room_type" style="width: 100%">
            <el-option label="普通教室" value="NORMAL" />
            <el-option label="阶梯/合班大教室" value="LECTURE_HALL" />
            <el-option label="计算机机房" value="COMPUTER_LAB" />
            <el-option label="专业实验室" value="NETWORK_LAB" />
            <el-option label="实训室" value="TRAINING_ROOM" />
          </el-select>
        </el-form-item>
        <el-form-item label="座位数"><el-input-number v-model="roomForm.capacity" :min="10" :max="500" /></el-form-item>
        <el-form-item label="使用模式">
          <el-radio-group v-model="roomForm.usage_mode">
            <el-radio value="FLOATING">流动教室（支持合班）</el-radio>
            <el-radio value="FIXED">固定班级独占</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="roomForm.usage_mode === 'FIXED'" label="绑定固定班">
          <el-select v-model="roomForm.fixed_cohort_id" style="width: 100%">
            <el-option v-for="c in cohorts" :key="c.id" :label="c.cohort_name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="共享策略">
          <el-select v-model="roomForm.sharing_policy" style="width: 100%">
            <el-option label="公共教室池 (PUBLIC_POOL)" value="PUBLIC_POOL" />
            <el-option label="空闲可借用 (IDLE_BORROW)" value="IDLE_BORROW" />
            <el-option label="本院系专属 (EXCLUSIVE)" value="EXCLUSIVE" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="roomDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleCreateRoom">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bldDialog" title="新增教学楼" width="380px">
      <el-form :model="bldForm" label-width="80px" size="small">
        <el-form-item label="楼栋编码"><el-input v-model="bldForm.building_code" placeholder="如 BLD-1" /></el-form-item>
        <el-form-item label="楼栋名称"><el-input v-model="bldForm.building_name" placeholder="如 第一教学楼" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="bldDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleCreateBuilding">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchOrgTree } from "../api/client";
import { addBuilding, addClassroom, deleteClassroom, downloadDomainExcel, getBuildings, getClassrooms, getCohorts, type BuildingItem, type ClassroomItem, type CohortItem } from "../api/resources";
import FreeRoomView from "./FreeRoomView.vue";

const tab = ref("list");
const scopeFilter = ref("ALL");
const rooms = ref<ClassroomItem[]>([]);
const buildings = ref<BuildingItem[]>([]);
const cohorts = ref<CohortItem[]>([]);
const defaultOrgId = ref<number>(1);
const roomDialog = ref(false);
const bldDialog = ref(false);

const roomForm = reactive({
  room_code: "",
  building: "第一教学楼",
  room_type: "NORMAL",
  capacity: 60,
  usage_mode: "FLOATING" as "FIXED" | "FLOATING",
  fixed_cohort_id: null as number | null,
  sharing_policy: "PUBLIC_POOL",
});
const bldForm = reactive({ building_code: "", building_name: "" });

const filteredRooms = computed(() =>
  rooms.value.filter((r) => {
    if (scopeFilter.value === "PUBLIC_POOL") return r.sharing_policy === "PUBLIC_POOL";
    if (scopeFilter.value === "FIXED") return r.usage_mode === "FIXED";
    if (scopeFilter.value.startsWith("BLD:")) return r.building === scopeFilter.value.slice(4);
    return true;
  })
);

async function loadAll() {
  const [rList, bList, cList, tree] = await Promise.all([getClassrooms(), getBuildings(), getCohorts(), fetchOrgTree()]);
  rooms.value = rList;
  buildings.value = bList;
  cohorts.value = cList;
  if (tree[0]) defaultOrgId.value = tree[0].id;
}

async function handleCreateRoom() {
  if (!roomForm.room_code) return;
  await addClassroom({ ...roomForm, owner_org_id: defaultOrgId.value, env_tags: [] });
  ElMessage.success("教室已添加");
  roomDialog.value = false;
  roomForm.room_code = "";
  await loadAll();
}

async function handleCreateBuilding() {
  if (!bldForm.building_code || !bldForm.building_name) return;
  await addBuilding({ ...bldForm, campus_org_id: defaultOrgId.value, floors: 5 });
  ElMessage.success("教学楼已添加");
  bldDialog.value = false;
  bldForm.building_code = "";
  bldForm.building_name = "";
  await loadAll();
}

async function handleDelete(id: number) {
  await deleteClassroom(id);
  ElMessage.success("已删除");
  await loadAll();
}

onMounted(loadAll);
</script>

<style scoped>
.split-layout { display: flex; gap: 12px; align-items: flex-start; }
.sub-nav { width: 220px; flex-shrink: 0; }
.sub-main { flex: 1; min-width: 0; }
.sub-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.nav-item { padding: 7px 10px; border-radius: 5px; cursor: pointer; font-size: 13px; }
.nav-item:hover { background: #f1f5f9; }
.nav-item.active { background: #eff6ff; color: #1d4ed8; font-weight: 600; }
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.muted { color: #64748b; font-size: 12px; }
</style>
