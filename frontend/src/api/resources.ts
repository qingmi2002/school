import { apiClient } from "./client";

export interface SiteConfig {
  site_name: string;
  site_subtitle: string;
  show_demo_accounts: boolean;
}

export interface SemesterItem {
  id: number;
  code: string;
  name: string;
  total_weeks: number;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
}

export interface BuildingItem {
  id: number;
  building_code: string;
  building_name: string;
  campus_org_id: number;
  floors: number;
  remark?: string | null;
}

export interface TeacherItem {
  id: number;
  username: string;
  real_name: string;
  org_node_id: number;
  role_code?: string;
  teacher_priority?: number;
}

export interface CohortItem {
  id: number;
  cohort_code: string;
  cohort_name: string;
  org_node_id: number;
  grade_year: number;
  student_count: number;
}

export interface StudentItem {
  id: number;
  username: string;
  real_name: string;
  org_node_id: number;
  cohort_id: number | null;
}

export interface ClassroomItem {
  id: number;
  room_code: string;
  building: string;
  building_id?: number | null;
  owner_org_id: number;
  capacity: number;
  room_type: string;
  usage_mode: "FIXED" | "FLOATING";
  fixed_cohort_id: number | null;
  sharing_policy: string;
  env_tags: string[];
}

export interface PolicyRuleItem {
  id: number;
  semester_id: number;
  target_type: "GLOBAL" | "TEACHER" | "COHORT" | "CLASSROOM";
  target_id: number | null;
  rule_type: "MUST_SCHEDULE" | "FORBID_SCHEDULE" | "PREFER_SCHEDULE";
  day_of_week: number;
  period_index: number;
  is_active: boolean;
  remark?: string | null;
}

export interface MasterImportReport {
  status: string;
  total_inserted: number;
  total_updated: number;
  total_errors: number;
  sheets: Record<string, { inserted: number; updated: number; errors: string[] }>;
}

export const getSiteConfig = async () => (await apiClient.get<SiteConfig>("/resources/site-config")).data;
export const saveSiteConfig = async (p: SiteConfig) => (await apiClient.put<SiteConfig>("/resources/site-config", p)).data;

export const getSemesters = async () => (await apiClient.get<SemesterItem[]>("/resources/semesters")).data;
export const addSemester = async (p: Omit<SemesterItem, "id">) => (await apiClient.post<SemesterItem>("/resources/semesters", p)).data;
export const setCurrentSemester = async (id: number) => (await apiClient.patch(`/resources/semesters/${id}/set-current`)).data;

export const getBuildings = async () => (await apiClient.get<BuildingItem[]>("/resources/buildings")).data;
export const addBuilding = async (p: Omit<BuildingItem, "id">) => (await apiClient.post<BuildingItem>("/resources/buildings", p)).data;
export const deleteBuilding = async (id: number) => apiClient.delete(`/resources/buildings/${id}`);

export const createOrgNodeApi = async (p: { parent_id: number | null; node_code: string; node_name: string; node_type_code: string }) =>
  (await apiClient.post("/org/nodes", p)).data;
export const renameOrgNodeApi = async (id: number, node_name: string) =>
  (await apiClient.patch(`/org/nodes/${id}`, { node_name })).data;
export const deleteOrgNodeApi = async (id: number) => apiClient.delete(`/org/nodes/${id}`);

export const getTeachers = async () => (await apiClient.get<TeacherItem[]>("/resources/teachers")).data;
export const addTeacher = async (p: { username: string; real_name: string; org_node_id: number; role_code?: string; teacher_priority?: number }) => (await apiClient.post<TeacherItem>("/resources/teachers", p)).data;
export const deleteTeacher = async (id: number) => apiClient.delete(`/resources/teachers/${id}`);

export const getCohorts = async () => (await apiClient.get<CohortItem[]>("/resources/cohorts")).data;
export const addCohort = async (p: Omit<CohortItem, "id">) => (await apiClient.post<CohortItem>("/resources/cohorts", p)).data;
export const deleteCohort = async (id: number) => apiClient.delete(`/resources/cohorts/${id}`);

export const getStudents = async () => (await apiClient.get<StudentItem[]>("/resources/students")).data;
export const addStudent = async (p: { username: string; real_name: string; org_node_id: number; cohort_id: number }) => (await apiClient.post<StudentItem>("/resources/students", p)).data;
export const deleteStudent = async (id: number) => apiClient.delete(`/resources/students/${id}`);

export const getClassrooms = async () => (await apiClient.get<ClassroomItem[]>("/resources/classrooms")).data;
export const addClassroom = async (p: Omit<ClassroomItem, "id">) => (await apiClient.post<ClassroomItem>("/resources/classrooms", p)).data;
export const switchClassroomUsage = async (id: number, usage_mode: "FIXED" | "FLOATING", fixed_cohort_id?: number | null) =>
  apiClient.patch(`/resources/classrooms/${id}/usage-mode`, null, { params: { usage_mode, fixed_cohort_id } });
export const deleteClassroom = async (id: number) => apiClient.delete(`/resources/classrooms/${id}`);

export const getPolicyRules = async (semesterId?: number) =>
  (await apiClient.get<PolicyRuleItem[]>("/resources/policy-rules", { params: { semester_id: semesterId } })).data;
export const addPolicyRule = async (p: Omit<PolicyRuleItem, "id" | "is_active">) =>
  (await apiClient.post<PolicyRuleItem>("/resources/policy-rules", p)).data;
export const deletePolicyRule = async (id: number) => apiClient.delete(`/resources/policy-rules/${id}`);

export const uploadMasterImport = async (file: File): Promise<MasterImportReport> => {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await apiClient.post<MasterImportReport>("/resources/master-import/upload", fd);
  return data;
};
