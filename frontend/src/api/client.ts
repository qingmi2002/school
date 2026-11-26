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
