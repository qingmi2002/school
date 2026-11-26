import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 15000,
});

export type ConstraintLevel = "HARD" | "SOFT";
export type SharingPolicy = "EXCLUSIVE" | "IDLE_BORROW" | "PUBLIC_POOL";

export interface TeacherUnavailableSlotPayload {
  timeslot_id: number;
  constraint_level: ConstraintLevel;
  reason?: string;
}

export interface RoomRuleItem {
  id: number;
  classroom_id: number;
  course_code: string | null;
  course_category: string | null;
  rule_type: "ALLOW" | "DENY";
  priority: number;
}

export interface RoomWithRules {
  id: number;
  room_code: string;
  building: string;
  owner_org_id: number;
  capacity: number;
  room_type: string;
  env_tags: string[];
  sharing_policy: SharingPolicy;
  rules: RoomRuleItem[];
}

export interface MatrixEntityOption {
  id: number;
  label: string;
  sub_label?: string;
}

export interface MatrixCard {
  detail_id: number;
  task_id: number;
  timeslot_id: number;
  day_of_week: number;
  period_index: number;
  classroom_id: number;
  room_code: string;
  course_code: string;
  course_name: string;
  course_category: string;
  teacher_id: number;
  teacher_name: string;
  cohort_ids: number[];
  cohort_names: string[];
  week_type: number;
  is_locked: boolean;
  is_manual_adjusted: boolean;
  lock_source?: string;
}

export interface UnscheduledItem {
  task_id: number;
  course_code: string;
  course_name: string;
  teacher_name: string;
  weekly_sessions: number;
  scheduled_sessions: number;
  reason: string;
}

export interface WorkbenchView {
  plan_id: number;
  plan_name: string;
  semester_id: number;
  org_node_id: number;
  run_mode: string;
  cohorts: MatrixEntityOption[];
  teachers: MatrixEntityOption[];
  rooms: MatrixEntityOption[];
  cards: MatrixCard[];
  unscheduled: UnscheduledItem[];
}

export interface SlotLightResult {
  target_timeslot_id: number;
  target_classroom_id: number;
  light: "GREEN" | "YELLOW" | "RED";
  allowed: boolean;
  elapsed_ms: number;
  hard_conflicts: string[];
  soft_warnings: string[];
}

export interface HealthCheckIssue {
  issue_type: string;
  severity: "ERROR" | "WARNING";
  message: string;
  detail_ids: number[];
}

export interface HealthCheckReport {
  semester_id: number;
  scope: "SINGLE_DEPT" | "SCHOOL_WIDE";
  passed: boolean;
  total_checked_sessions: number;
  conflict_count: number;
  elapsed_ms: number;
  issues: HealthCheckIssue[];
}

export async function saveTeacherUnavailableGrid(
  semesterId: number,
  teacherId: number,
  slots: TeacherUnavailableSlotPayload[]
) {
  const { data } = await apiClient.put("/constraints/teacher-unavailable", {
    semester_id: semesterId,
    teacher_id: teacherId,
    slots,
  });
  return data;
}

export async function fetchRoomsWithRules(): Promise<RoomWithRules[]> {
  const { data } = await apiClient.get<RoomWithRules[]>("/constraints/rooms");
  return data;
}

export async function updateRoomPolicy(
  roomId: number,
  sharingPolicy: SharingPolicy,
  envTags: string[]
) {
  const { data } = await apiClient.patch(`/constraints/rooms/${roomId}/policy`, {
    sharing_policy: sharingPolicy,
    env_tags: envTags,
  });
  return data;
}

export async function addRoomRule(payload: {
  classroom_id: number;
  course_code?: string;
  course_category?: "THEORY" | "LAB" | "MIXED";
  rule_type: "ALLOW" | "DENY";
}) {
  const { data } = await apiClient.post<RoomRuleItem>("/constraints/room-rules", payload);
  return data;
}

export async function removeRoomRule(ruleId: number) {
  await apiClient.delete(`/constraints/room-rules/${ruleId}`);
}

export async function fetchWorkbenchView(planId: number): Promise<WorkbenchView> {
  const { data } = await apiClient.get<WorkbenchView>(`/workbench/plans/${planId}`);
  return data;
}

export async function fetchMatrixLights(payload: {
  plan_id: number;
  detail_id: number;
  target_classroom_id: number;
  scope: "SINGLE_DEPT" | "SCHOOL_WIDE";
}) {
  const { data } = await apiClient.post<{
    elapsed_ms: number;
    slots: Record<number, SlotLightResult>;
  }>("/validator/matrix-lights", payload);
  return data;
}

export async function applyDragMove(payload: {
  plan_id: number;
  detail_id: number;
  target_timeslot_id: number;
  target_classroom_id: number;
  scope: "SINGLE_DEPT" | "SCHOOL_WIDE";
}) {
  const { data } = await apiClient.post<SlotLightResult>("/validator/drag-apply", payload);
  return data;
}

export async function runHealthCheck(
  semesterId: number,
  scope: "SINGLE_DEPT" | "SCHOOL_WIDE"
): Promise<HealthCheckReport> {
  const { data } = await apiClient.get<HealthCheckReport>("/validator/health-check", {
    params: { semester_id: semesterId, scope },
  });
  return data;
}
