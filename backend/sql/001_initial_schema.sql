-- =============================================================================
-- 高校分级智能排课系统（多级通用版）PostgreSQL 15 完整 16 张核心表 DDL
-- 支持单院系独立轻量化运行与全校多级统筹自由调整
-- =============================================================================

-- 1. 组织节点类型字典表
CREATE TABLE IF NOT EXISTS node_type (
    code VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255),
    default_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_order SMALLINT NOT NULL DEFAULT 0
);

-- 2. 多架构任意深度动态组织树（含 5 大正交开关 + 校区边界）
CREATE TABLE IF NOT EXISTS org_node (
    id SERIAL PRIMARY KEY,
    parent_id INT REFERENCES org_node(id) ON DELETE RESTRICT,
    node_code VARCHAR(40) NOT NULL UNIQUE,
    node_name VARCHAR(120) NOT NULL,
    node_type_code VARCHAR(32) NOT NULL REFERENCES node_type(code) ON DELETE RESTRICT,
    tree_path VARCHAR(512) NOT NULL,
    depth SMALLINT NOT NULL DEFAULT 1,
    is_scheduling_unit BOOLEAN NOT NULL DEFAULT FALSE,
    is_public_provider BOOLEAN NOT NULL DEFAULT FALSE,
    has_student_cohort BOOLEAN NOT NULL DEFAULT FALSE,
    has_room_pool BOOLEAN NOT NULL DEFAULT FALSE,
    is_campus_boundary BOOLEAN NOT NULL DEFAULT FALSE,
    is_summary_node BOOLEAN NOT NULL DEFAULT FALSE,
    allow_custom_timeslot BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_org_node_tree_path ON org_node(tree_path);
CREATE INDEX IF NOT EXISTS ix_org_node_parent_id ON org_node(parent_id);

-- 6. 学期与教学周配置表（前置供外键引用）
CREATE TABLE IF NOT EXISTS semester (
    id SERIAL PRIMARY KEY,
    code VARCHAR(24) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    total_weeks SMALLINT NOT NULL DEFAULT 18,
    is_current BOOLEAN NOT NULL DEFAULT FALSE
);

-- 3. 横向资源授权矩阵
CREATE TABLE IF NOT EXISTS org_resource_grant (
    id SERIAL PRIMARY KEY,
    granter_org_id INT NOT NULL REFERENCES org_node(id) ON DELETE CASCADE,
    grantee_org_id INT NOT NULL REFERENCES org_node(id) ON DELETE CASCADE,
    semester_id INT REFERENCES semester(id) ON DELETE CASCADE,
    resource_type VARCHAR(24) NOT NULL CHECK (resource_type IN ('ROOM_POOL', 'TEACHER', 'PUBLIC_COURSE')),
    grant_mode VARCHAR(24) NOT NULL DEFAULT 'IDLE_ONLY' CHECK (grant_mode IN ('FULL', 'IDLE_ONLY', 'APPROVAL_REQUIRED')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    remark VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_org_resource_grant_scope UNIQUE (granter_org_id, grantee_org_id, resource_type, semester_id),
    CONSTRAINT ck_grant_not_self CHECK (granter_org_id <> grantee_org_id)
);

-- 4. 系统用户与 RBAC 角色表
CREATE TABLE IF NOT EXISTS sys_user (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    real_name VARCHAR(60) NOT NULL,
    org_node_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    role_code VARCHAR(30) NOT NULL CHECK (role_code IN ('SUPER_ADMIN', 'DEPT_SCHEDULER', 'LAB_ADMIN', 'TEACHER')),
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. 双模式 Excel 导入批次与冲突审计日志表
CREATE TABLE IF NOT EXISTS excel_import_batch (
    id SERIAL PRIMARY KEY,
    semester_id INT NOT NULL REFERENCES semester(id) ON DELETE RESTRICT,
    org_node_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    operator_id INT NOT NULL REFERENCES sys_user(id) ON DELETE RESTRICT,
    import_type VARCHAR(30) NOT NULL CHECK (import_type IN ('TASK_ONLY', 'PRE_SCHEDULED')),
    file_name VARCHAR(255) NOT NULL,
    total_rows INT NOT NULL DEFAULT 0,
    conflict_rows INT NOT NULL DEFAULT 0,
    status VARCHAR(24) NOT NULL CHECK (status IN ('SUCCESS', 'PARTIAL_CONFLICT', 'ROLLED_BACK')),
    conflict_report JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 7. 标准时间片字典表（支持节点级作息覆写）
CREATE TABLE IF NOT EXISTS timeslot (
    id SERIAL PRIMARY KEY,
    org_node_id INT REFERENCES org_node(id) ON DELETE CASCADE,
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    period_index SMALLINT NOT NULL CHECK (period_index >= 1),
    period_name VARCHAR(40) NOT NULL,
    start_time VARCHAR(8),
    end_time VARCHAR(8),
    is_evening BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_timeslot_node_slot UNIQUE (org_node_id, day_of_week, period_index)
);

-- 8. 行政班/学生群组表
CREATE TABLE IF NOT EXISTS student_cohort (
    id SERIAL PRIMARY KEY,
    cohort_code VARCHAR(40) NOT NULL UNIQUE,
    cohort_name VARCHAR(100) NOT NULL,
    org_node_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    grade_year SMALLINT NOT NULL,
    student_count INT NOT NULL DEFAULT 30
);

-- 9. 教室与专业机房/实验室表
CREATE TABLE IF NOT EXISTS classroom (
    id SERIAL PRIMARY KEY,
    room_code VARCHAR(40) NOT NULL UNIQUE,
    building VARCHAR(60) NOT NULL,
    owner_org_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    capacity INT NOT NULL CHECK (capacity > 0),
    room_type VARCHAR(24) NOT NULL CHECK (room_type IN ('NORMAL', 'COMPUTER_LAB', 'NETWORK_LAB', 'TRAINING_ROOM', 'SPORTS')),
    env_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    sharing_policy VARCHAR(24) NOT NULL DEFAULT 'IDLE_BORROW' CHECK (sharing_policy IN ('EXCLUSIVE', 'IDLE_BORROW', 'PUBLIC_POOL')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 10. 教学任务主表
CREATE TABLE IF NOT EXISTS teaching_task (
    id SERIAL PRIMARY KEY,
    semester_id INT NOT NULL REFERENCES semester(id) ON DELETE RESTRICT,
    org_node_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    course_code VARCHAR(40) NOT NULL,
    course_name VARCHAR(120) NOT NULL,
    course_category VARCHAR(20) NOT NULL CHECK (course_category IN ('THEORY', 'LAB', 'MIXED')),
    course_level VARCHAR(20) NOT NULL DEFAULT 'DEPT' CHECK (course_level IN ('PUBLIC', 'COLLEGE', 'DEPT')),
    teacher_id INT NOT NULL REFERENCES sys_user(id) ON DELETE RESTRICT,
    cohort_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    weekly_sessions SMALLINT NOT NULL CHECK (weekly_sessions > 0),
    week_type SMALLINT NOT NULL DEFAULT 0 CHECK (week_type IN (0, 1, 2)),
    start_week SMALLINT NOT NULL DEFAULT 1,
    end_week SMALLINT NOT NULL DEFAULT 18,
    total_students INT NOT NULL CHECK (total_students > 0),
    required_env_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE
);

-- 11. 分级基线锁定表
CREATE TABLE IF NOT EXISTS public_course_lock (
    id SERIAL PRIMARY KEY,
    semester_id INT NOT NULL REFERENCES semester(id) ON DELETE CASCADE,
    lock_scope_org_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    timeslot_id INT NOT NULL REFERENCES timeslot(id) ON DELETE RESTRICT,
    week_type SMALLINT NOT NULL DEFAULT 0 CHECK (week_type IN (0, 1, 2)),
    cohort_id INT REFERENCES student_cohort(id) ON DELETE CASCADE,
    classroom_id INT REFERENCES classroom(id) ON DELETE CASCADE,
    teacher_id INT REFERENCES sys_user(id) ON DELETE CASCADE,
    course_name VARCHAR(120) NOT NULL,
    is_readonly BOOLEAN NOT NULL DEFAULT TRUE
);

-- 12. 教师禁排与偏好时间表
CREATE TABLE IF NOT EXISTS teacher_unavailable (
    id SERIAL PRIMARY KEY,
    semester_id INT NOT NULL REFERENCES semester(id) ON DELETE CASCADE,
    teacher_id INT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    timeslot_id INT NOT NULL REFERENCES timeslot(id) ON DELETE CASCADE,
    constraint_level VARCHAR(10) NOT NULL DEFAULT 'HARD' CHECK (constraint_level IN ('HARD', 'SOFT')),
    reason VARCHAR(120),
    CONSTRAINT uq_teacher_unavail_slot UNIQUE (semester_id, teacher_id, timeslot_id)
);

-- 13. 机房黑白名单与准入规则表
CREATE TABLE IF NOT EXISTS room_course_rule (
    id SERIAL PRIMARY KEY,
    classroom_id INT NOT NULL REFERENCES classroom(id) ON DELETE CASCADE,
    course_code VARCHAR(40),
    course_category VARCHAR(20),
    rule_type VARCHAR(10) NOT NULL CHECK (rule_type IN ('ALLOW', 'DENY')),
    priority SMALLINT NOT NULL DEFAULT 10
);

-- 14. 排课方案版本与云盘归档表
CREATE TABLE IF NOT EXISTS schedule_plan (
    id SERIAL PRIMARY KEY,
    semester_id INT NOT NULL REFERENCES semester(id) ON DELETE RESTRICT,
    org_node_id INT NOT NULL REFERENCES org_node(id) ON DELETE RESTRICT,
    plan_name VARCHAR(120) NOT NULL,
    version_tag VARCHAR(40) NOT NULL,
    run_mode VARCHAR(20) NOT NULL DEFAULT 'SINGLE_DEPT' CHECK (run_mode IN ('SINGLE_DEPT', 'SCHOOL_WIDE')),
    fitness_score NUMERIC(10, 2),
    cloud_archive_path VARCHAR(500),
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 15. 课表明细表
CREATE TABLE IF NOT EXISTS schedule_detail (
    id SERIAL PRIMARY KEY,
    plan_id INT NOT NULL REFERENCES schedule_plan(id) ON DELETE CASCADE,
    task_id INT NOT NULL REFERENCES teaching_task(id) ON DELETE RESTRICT,
    timeslot_id INT NOT NULL REFERENCES timeslot(id) ON DELETE RESTRICT,
    classroom_id INT NOT NULL REFERENCES classroom(id) ON DELETE RESTRICT,
    week_type SMALLINT NOT NULL DEFAULT 0 CHECK (week_type IN (0, 1, 2)),
    is_manual_adjusted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_detail_room_slot_week UNIQUE (plan_id, timeslot_id, classroom_id, week_type)
);
CREATE INDEX IF NOT EXISTS ix_schedule_detail_plan_slot ON schedule_detail(plan_id, timeslot_id);

-- 16. 调停课审批流与云盘归档审计表
CREATE TABLE IF NOT EXISTS schedule_change_audit (
    id SERIAL PRIMARY KEY,
    plan_id INT NOT NULL REFERENCES schedule_plan(id) ON DELETE CASCADE,
    operator_id INT NOT NULL REFERENCES sys_user(id) ON DELETE RESTRICT,
    audit_type VARCHAR(24) NOT NULL CHECK (audit_type IN ('CHANGE_REQUEST', 'ARCHIVE_SYNC')),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'SYNCED', 'FAILED')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    retry_count SMALLINT NOT NULL DEFAULT 0,
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
