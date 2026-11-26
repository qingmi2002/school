"""一键初始化完整四级高校演示数据（校->院->系->专业 + 6类角色账号 + 教室机房 + 公共课锁定 + 已排课表）。"""
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.locks import upsert_baseline_locks
from app.locks.schemas import BaselineLockBatchCreate, PublicLockItemIn
from app.models import (
    Classroom,
    OrgNode,
    RoomCourseRule,
    ScheduleDetail,
    SchedulePlan,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org import apply_org_preset


def seed_full_demo_data(db: Session) -> dict:
    existing_admin = db.query(SysUser).filter(SysUser.username == "admin").first()
    if existing_admin:
        plan = db.query(SchedulePlan).order_by(SchedulePlan.id.desc()).first()
        return {"seeded": False, "message": "演示数据已存在，无需重复初始化", "plan_id": plan.id if plan else None}

    apply_org_preset(db, "school_college_dept", clear_existing=True)
    univ = db.query(OrgNode).filter(OrgNode.node_code == "UNIV").first()
    col = db.query(OrgNode).filter(OrgNode.node_code == "INFO_COL").first()
    dept = db.query(OrgNode).filter(OrgNode.node_code == "CS_DEPT").first()
    se_major = db.query(OrgNode).filter(OrgNode.node_code == "SE_MAJOR").first()
    ai_major = db.query(OrgNode).filter(OrgNode.node_code == "AI_MAJOR").first()

    sem = Semester(code="2026-2027-1", name="2026-2027学年第一学期", total_weeks=18, is_current=True)
    db.add(sem)
    db.flush()

    slots = {}
    day_names = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五"}
    period_names = {1: "1-2节", 2: "3-4节", 3: "5-6节", 4: "7-8节", 5: "9-10节"}
    for d in range(1, 6):
        for p in range(1, 6):
            ts = Timeslot(
                org_node_id=None,
                day_of_week=d,
                period_index=p,
                period_name=f"{day_names[d]} {period_names[p]}",
                is_evening=(p == 5),
            )
            db.add(ts)
            db.flush()
            slots[(d, p)] = ts

    c_se1 = StudentCohort(cohort_code="SE2401", cohort_name="软工2401班", org_node_id=se_major.id, grade_year=2024, student_count=46)
    c_ai1 = StudentCohort(cohort_code="AI2401", cohort_name="智能2401班", org_node_id=ai_major.id, grade_year=2024, student_count=42)
    db.add_all([c_se1, c_ai1])
    db.flush()

    pw = hash_password("123456")
    u_admin = SysUser(username="admin", real_name="教务处长(校级)", org_node_id=univ.id, role_code="SUPER_ADMIN", password_hash=pw)
    u_col = SysUser(username="college_admin", real_name="王院长(院级排课员)", org_node_id=col.id, role_code="COLLEGE_SCHEDULER", password_hash=pw)
    u_dept = SysUser(username="dept_admin", real_name="赵主任(系级排课员)", org_node_id=dept.id, role_code="DEPT_SCHEDULER", password_hash=pw)
    u_major = SysUser(username="major_admin", real_name="周秘书(专业级排课员)", org_node_id=se_major.id, role_code="MAJOR_SCHEDULER", password_hash=pw)
    u_lab = SysUser(username="lab_admin", real_name="孙老师(机房管理员)", org_node_id=dept.id, role_code="LAB_ADMIN", password_hash=pw)
    u_t1 = SysUser(username="T1001", real_name="张明远教授", org_node_id=se_major.id, role_code="TEACHER", password_hash=pw)
    u_t2 = SysUser(username="T1002", real_name="李思琪副教授", org_node_id=ai_major.id, role_code="TEACHER", password_hash=pw)
    u_stu = SysUser(username="S202401", real_name="陈同学(软工2401)", org_node_id=se_major.id, cohort_id=c_se1.id, role_code="STUDENT", password_hash=pw)
    db.add_all([u_admin, u_col, u_dept, u_major, u_lab, u_t1, u_t2, u_stu])
    db.flush()

    r_pub = Classroom(room_code="A-201", building="第一教学楼", owner_org_id=univ.id, capacity=120, room_type="NORMAL", env_tags=["多媒体"], sharing_policy="PUBLIC_POOL")
    r_lab1 = Classroom(room_code="LAB-402", building="信息实验楼", owner_org_id=dept.id, capacity=60, room_type="COMPUTER_LAB", env_tags=["Linux", "Python", "GPU"], sharing_policy="IDLE_BORROW")
    r_lab2 = Classroom(room_code="LAB-305", building="信息实验楼", owner_org_id=col.id, capacity=55, room_type="NETWORK_LAB", env_tags=["Cisco", "Linux"], sharing_policy="IDLE_BORROW")
    db.add_all([r_pub, r_lab1, r_lab2])
    db.flush()

    db.add(RoomCourseRule(classroom_id=r_lab1.id, course_category="THEORY", rule_type="DENY", priority=10))

    upsert_baseline_locks(
        db,
        BaselineLockBatchCreate(
            semester_id=sem.id,
            lock_scope_org_id=univ.id,
            items=[
                PublicLockItemIn(timeslot_id=slots[(1, 1)].id, cohort_id=c_se1.id, classroom_id=r_pub.id, course_name="大学英语(校级公共课)"),
                PublicLockItemIn(timeslot_id=slots[(3, 1)].id, cohort_id=c_se1.id, classroom_id=r_pub.id, course_name="高等数学(校级公共课)"),
            ],
        ),
    )

    t1 = TeachingTask(semester_id=sem.id, org_node_id=se_major.id, course_code="SE201", course_name="软件工程导论", course_category="THEORY", teacher_id=u_t1.id, cohort_ids=[c_se1.id], weekly_sessions=2, week_type=0, total_students=46)
    t2 = TeachingTask(semester_id=sem.id, org_node_id=se_major.id, course_code="SE205", course_name="Linux系统实训", course_category="LAB", teacher_id=u_t1.id, cohort_ids=[c_se1.id], weekly_sessions=1, week_type=1, total_students=46, required_env_tags=["Linux"])
    t3 = TeachingTask(semester_id=sem.id, org_node_id=se_major.id, course_code="SE206", course_name="Python数据挖掘实验", course_category="LAB", teacher_id=u_t2.id, cohort_ids=[c_se1.id], weekly_sessions=1, week_type=2, total_students=46, required_env_tags=["Python"])
    t4 = TeachingTask(semester_id=sem.id, org_node_id=ai_major.id, course_code="AI301", course_name="深度学习架构", course_category="LAB", teacher_id=u_t2.id, cohort_ids=[c_ai1.id], weekly_sessions=1, week_type=0, total_students=42, required_env_tags=["GPU"])
    db.add_all([t1, t2, t3, t4])
    db.flush()

    plan = SchedulePlan(
        semester_id=sem.id,
        org_node_id=dept.id,
        plan_name="2026秋_计算机系排课方案V1",
        version_tag="Plan_V1",
        run_mode="SCHOOL_WIDE",
        fitness_score=96.5,
        is_published=True,
    )
    db.add(plan)
    db.flush()

    db.add_all([
        ScheduleDetail(plan_id=plan.id, task_id=t1.id, timeslot_id=slots[(1, 2)].id, classroom_id=r_pub.id, week_type=0),
        ScheduleDetail(plan_id=plan.id, task_id=t1.id, timeslot_id=slots[(4, 2)].id, classroom_id=r_pub.id, week_type=0),
        ScheduleDetail(plan_id=plan.id, task_id=t2.id, timeslot_id=slots[(2, 2)].id, classroom_id=r_lab1.id, week_type=1),
        ScheduleDetail(plan_id=plan.id, task_id=t3.id, timeslot_id=slots[(2, 2)].id, classroom_id=r_lab1.id, week_type=2),
        ScheduleDetail(plan_id=plan.id, task_id=t4.id, timeslot_id=slots[(3, 3)].id, classroom_id=r_lab1.id, week_type=0),
    ])
    db.commit()
    return {"seeded": True, "message": "已初始化四级组织树、8个多角色演示账号及排课方案", "plan_id": plan.id}
