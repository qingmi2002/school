<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <div class="title">机房软件环境标签、黑白名单与借用策略管控</div>
          <div class="subtitle">支持单院系独占或空闲向兄弟院系开放借用，严防理论课挤占专业机房</div>
        </div>
        <el-button size="small" @click="loadRooms">刷新列表</el-button>
      </div>
    </template>

    <el-table :data="rooms" border stripe style="width: 100%">
      <el-table-column prop="room_code" label="机房编号" width="120" />
      <el-table-column prop="building" label="教学楼" width="120" />
      <el-table-column prop="capacity" label="座位数" width="90" />
      <el-table-column label="借用策略" width="190">
        <template #default="{ row }">
          <el-select
            v-model="row.sharing_policy"
            size="small"
            @change="handlePolicySave(row)"
          >
            <el-option label="本系独占 (EXCLUSIVE)" value="EXCLUSIVE" />
            <el-option label="空闲借用 (IDLE_BORROW)" value="IDLE_BORROW" />
            <el-option label="全校公共池 (PUBLIC_POOL)" value="PUBLIC_POOL" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="软件环境标签">
        <template #default="{ row }">
          <el-tag
            v-for="tag in row.env_tags"
            :key="tag"
            size="small"
            style="margin: 2px 4px 2px 0"
          >
            {{ tag }}
          </el-tag>
          <span v-if="!row.env_tags.length" class="muted">无特殊标签</span>
        </template>
      </el-table-column>
      <el-table-column label="黑白名单准入规则" min-width="220">
        <template #default="{ row }">
          <el-tag
            v-for="rule in row.rules"
            :key="rule.id"
            :type="rule.rule_type === 'DENY' ? 'danger' : 'success'"
            size="small"
            closable
            style="margin: 2px 4px 2px 0"
            @close="handleRemoveRule(row, rule.id)"
          >
            {{ rule.rule_type === "DENY" ? "禁止" : "仅限" }}:
            {{ rule.course_code || rule.course_category }}
          </el-tag>
          <el-button
            size="small"
            link
            type="primary"
            @click="quickDenyTheory(row)"
          >
            + 禁止纯理论课
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  addRoomRule,
  fetchRoomsWithRules,
  removeRoomRule,
  updateRoomPolicy,
  type RoomWithRules,
} from "../api/client";

const fallbackDemoRooms: RoomWithRules[] = [
  {
    id: 1,
    room_code: "LAB-402",
    building: "信息楼",
    owner_org_id: 1,
    capacity: 60,
    room_type: "COMPUTER_LAB",
    env_tags: ["Linux", "Python", "GPU"],
    sharing_policy: "IDLE_BORROW",
    rules: [
      {
        id: 101,
        classroom_id: 1,
        course_code: null,
        course_category: "THEORY",
        rule_type: "DENY",
        priority: 10,
      },
    ],
  },
];

const rooms = ref<RoomWithRules[]>([...fallbackDemoRooms]);

async function loadRooms(): Promise<void> {
  try {
    const data = await fetchRoomsWithRules();
    if (data.length > 0) {
      rooms.value = data;
    }
  } catch {
    rooms.value = [...fallbackDemoRooms];
  }
}

async function handlePolicySave(row: RoomWithRules): Promise<void> {
  try {
    await updateRoomPolicy(row.id, row.sharing_policy, row.env_tags);
    ElMessage.success(`${row.room_code} 借用策略已更新`);
  } catch {
    ElMessage.info(`演示模式已切换 ${row.room_code} 策略为 ${row.sharing_policy}`);
  }
}

async function quickDenyTheory(row: RoomWithRules): Promise<void> {
  try {
    const created = await addRoomRule({
      classroom_id: row.id,
      course_category: "THEORY",
      rule_type: "DENY",
    });
    row.rules.push(created);
    ElMessage.success(`已为 ${row.room_code} 添加黑名单：禁止纯理论课`);
  } catch {
    row.rules.push({
      id: Date.now(),
      classroom_id: row.id,
      course_code: null,
      course_category: "THEORY",
      rule_type: "DENY",
      priority: 10,
    });
  }
}

async function handleRemoveRule(row: RoomWithRules, ruleId: number): Promise<void> {
  try {
    await removeRoomRule(ruleId);
  } catch {
    // 演示态本地移除
  }
  row.rules = row.rules.filter((r) => r.id !== ruleId);
}

onMounted(() => {
  void loadRooms();
});
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
.muted {
  color: #9ca3af;
  font-size: 12px;
}
</style>
