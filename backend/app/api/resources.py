"""
V1.2 高内聚动态资源管理与自定义排课规则中心 API：
- 系统自定义配置（系统名称、正式版隐藏体验账号）
- 排课大周期管理（学期起止日期、周数、切换当前学期）
- 教师 / 学生 / 班级 / 教室（固定 FIXED 与 流动 FLOATING）全动态数据库 CRUD
- 统一自定义规则引擎（针对全局/单教师/单班级/单教室设置必排/禁排/优先时段，如每天 1-2 节必排）
"""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.db.session import get_db
from app.models import (
    Classroom,
    SchedulePolicyRule,
    Semester,
    StudentCohort,
    SysUser,
    SystemConfig,
)

router = APIRouter(prefix="/resources", tags=["resources-and-rules"])


# ---------- 1. 系统配置（自定义系统名 & 体验账号开关） ----------
class SiteConfigDTO(BaseModel):
    site_name: str = "智能排课系统"
    site_subtitle: str = "面向高校与院系的专业分级排课管理平台"
    show_demo_accounts: bool = True


@router.get("/site-config", response_model=SiteConfigDTO)
def get_site_config(db: Session = Depends(get_db)):
    row = db.query(SystemConfig).filter(SystemConfig.config_key == "site_profile").first()
    if row and isinstance(row.config_value, dict):
        return SiteConfigDTO(**row.config_value)
    return SiteConfigDTO()


@router.put("/site-config", response_model=SiteConfigDTO)
def update_site_config(payload: SiteConfigDTO, db: Session = Depends(get_db)):
    row = db.query(SystemConfig).filter(SystemConfig.config_key == "site_profile").first()
    if row is None:
        row = SystemConfig(config_key="site_profile", config_value=payload.model_dump())
        db.add(row)
    else:
        row.config_value = payload.model_dump()
    db.commit()
    return payload


# ---------- 2. 排课大时间周期（学期管理） ----------
class SemesterCreate(BaseModel):
    code: str
    name: str
    total_weeks: int = 18
    start_date: Optional[str] = "2026-09-07"
    end_date: Optional[str] = "2027-01-15"
    is_current: bool = False


class SemesterOut(SemesterCreate):
    id: int


@router.get("/semesters", response_model=List[SemesterOut])
def list_semesters(db: Session = Depends(get_db)):
    rows = db.query(Semester).order_by(Semester.is_current.desc(), Semester.id.desc()).all()
    return [
        SemesterOut(
            id=r.id,
            code=r.code,
            name=r.name,
            total_weeks=r.total_weeks,
            start_date=r.start_date,
            end_date=r.end_date,
            is_current=r.is_current,
        )
        for r in rows
    ]


@router.post("/semesters", response_model=SemesterOut)
def create_semester(payload: SemesterCreate, db: Session = Depends(get_db)):
    if payload.is_current:
        db.query(Semester).update({Semester.is_current: False})
    row = Semester(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return SemesterOut(
        id=row.id,
        code=row.code,
        name=row.name,
        total_weeks=row.total_weeks,
        start_date=row.start_date,
        end_date=row.end_date,
        is_current=row.is_current,
    )


@router.patch("/semesters/{sem_id}/set-current")
def set_current_semester(sem_id: int, db: Session = Depends(get_db)):
    row = db.query(Semester).filter(Semester.id == sem_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="学期不存在")
    db.query(Semester).update({Semester.is_current: False})
    row.is_current = True
    db.commit()
    return {"current_semester_id": sem_id}


# ---------- 3. 教师管理 ----------
class TeacherCreate(BaseModel):
    username: str
    real_name: str
    org_node_id: int
    password: str = "123456"


class TeacherOut(BaseModel):
    id: int
    username: str
    real_name: str
    org_node_id: int


@router.get("/teachers", response_model=List[TeacherOut])
def list_teachers(org_node_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(SysUser).filter(SysUser.role_code == "TEACHER", SysUser.is_active.is_(True))
    if org_node_id is not None:
        q = q.filter(SysUser.org_node_id == org_node_id)
    return [TeacherOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id) for u in q.order_by(SysUser.id).all()]


@router.post("/teachers", response_model=TeacherOut)
def create_teacher(payload: TeacherCreate, db: Session = Depends(get_db)):
    u = SysUser(
        username=payload.username,
        real_name=payload.real_name,
        org_node_id=payload.org_node_id,
        role_code="TEACHER",
        password_hash=hash_password(payload.password),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return TeacherOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id)


@router.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    u = db.query(SysUser).filter(SysUser.id == teacher_id, SysUser.role_code == "TEACHER").first()
    if u is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    u.is_active = False
    db.commit()
    return {"deleted_id": teacher_id}


# ---------- 4. 班级管理 ----------
class CohortCreate(BaseModel):
    cohort_code: str
    cohort_name: str
    org_node_id: int
    grade_year: int = 2026
    student_count: int = 40


class CohortOut(CohortCreate):
    id: int


@router.get("/cohorts", response_model=List[CohortOut])
def list_cohorts(org_node_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(StudentCohort)
    if org_node_id is not None:
        q = q.filter(StudentCohort.org_node_id == org_node_id)
    return [
        CohortOut(
            id=c.id,
            cohort_code=c.cohort_code,
            cohort_name=c.cohort_name,
            org_node_id=c.org_node_id,
            grade_year=c.grade_year,
            student_count=c.student_count,
        )
        for c in q.order_by(StudentCohort.id).all()
    ]


@router.post("/cohorts", response_model=CohortOut)
def create_cohort(payload: CohortCreate, db: Session = Depends(get_db)):
    c = StudentCohort(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return CohortOut(
        id=c.id,
        cohort_code=c.cohort_code,
        cohort_name=c.cohort_name,
        org_node_id=c.org_node_id,
        grade_year=c.grade_year,
        student_count=c.student_count,
    )


@router.delete("/cohorts/{cohort_id}")
def delete_cohort(cohort_id: int, db: Session = Depends(get_db)):
    c = db.query(StudentCohort).filter(StudentCohort.id == cohort_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    db.delete(c)
    db.commit()
    return {"deleted_id": cohort_id}


# ---------- 5. 学生管理 ----------
class StudentCreate(BaseModel):
    username: str
    real_name: str
    org_node_id: int
    cohort_id: int
    password: str = "123456"


class StudentOut(BaseModel):
    id: int
    username: str
    real_name: str
    org_node_id: int
    cohort_id: Optional[int]


@router.get("/students", response_model=List[StudentOut])
def list_students(cohort_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(SysUser).filter(SysUser.role_code == "STUDENT", SysUser.is_active.is_(True))
    if cohort_id is not None:
        q = q.filter(SysUser.cohort_id == cohort_id)
    return [
        StudentOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id, cohort_id=u.cohort_id)
        for u in q.order_by(SysUser.id).all()
    ]


@router.post("/students", response_model=StudentOut)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    u = SysUser(
        username=payload.username,
        real_name=payload.real_name,
        org_node_id=payload.org_node_id,
        cohort_id=payload.cohort_id,
        role_code="STUDENT",
        password_hash=hash_password(payload.password),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return StudentOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id, cohort_id=u.cohort_id)


@router.delete("/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    u = db.query(SysUser).filter(SysUser.id == student_id, SysUser.role_code == "STUDENT").first()
    if u is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    u.is_active = False
    db.commit()
    return {"deleted_id": student_id}


# ---------- 6. 教室管理（固定 FIXED / 流动 FLOATING） ----------
class ClassroomCreate(BaseModel):
    room_code: str
    building: str
    owner_org_id: int
    capacity: int = 60
    room_type: Literal["NORMAL", "COMPUTER_LAB", "NETWORK_LAB", "TRAINING_ROOM", "SPORTS"] = "NORMAL"
    usage_mode: Literal["FIXED", "FLOATING"] = "FLOATING"
    fixed_cohort_id: Optional[int] = None
    sharing_policy: Literal["EXCLUSIVE", "IDLE_BORROW", "PUBLIC_POOL"] = "IDLE_BORROW"
    env_tags: List[str] = Field(default_factory=list)


class ClassroomOut(ClassroomCreate):
    id: int


@router.get("/classrooms", response_model=List[ClassroomOut])
def list_classrooms(usage_mode: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(Classroom).filter(Classroom.is_active.is_(True))
    if usage_mode in ("FIXED", "FLOATING"):
        q = q.filter(Classroom.usage_mode == usage_mode)
    return [
        ClassroomOut(
            id=r.id,
            room_code=r.room_code,
            building=r.building,
            owner_org_id=r.owner_org_id,
            capacity=r.capacity,
            room_type=r.room_type,
            usage_mode=r.usage_mode,
            fixed_cohort_id=r.fixed_cohort_id,
            sharing_policy=r.sharing_policy,
            env_tags=list(r.env_tags or []),
        )
        for r in q.order_by(Classroom.room_code).all()
    ]


@router.post("/classrooms", response_model=ClassroomOut)
def create_classroom(payload: ClassroomCreate, db: Session = Depends(get_db)):
    r = Classroom(**payload.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return ClassroomOut(
        id=r.id,
        room_code=r.room_code,
        building=r.building,
        owner_org_id=r.owner_org_id,
        capacity=r.capacity,
        room_type=r.room_type,
        usage_mode=r.usage_mode,
        fixed_cohort_id=r.fixed_cohort_id,
        sharing_policy=r.sharing_policy,
        env_tags=list(r.env_tags or []),
    )


@router.patch("/classrooms/{room_id}/usage-mode")
def update_classroom_usage_mode(
    room_id: int,
    usage_mode: Literal["FIXED", "FLOATING"] = Query(...),
    fixed_cohort_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    r = db.query(Classroom).filter(Classroom.id == room_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="教室不存在")
    r.usage_mode = usage_mode
    r.fixed_cohort_id = fixed_cohort_id if usage_mode == "FIXED" else None
    db.commit()
    return {"id": r.id, "usage_mode": r.usage_mode, "fixed_cohort_id": r.fixed_cohort_id}


@router.delete("/classrooms/{room_id}")
def delete_classroom(room_id: int, db: Session = Depends(get_db)):
    r = db.query(Classroom).filter(Classroom.id == room_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="教室不存在")
    r.is_active = False
    db.commit()
    return {"deleted_id": room_id}


# ---------- 7. 高内聚统一排课策略规则（必排/禁排/优先，支持全局与单实体） ----------
class PolicyRuleCreate(BaseModel):
    semester_id: int
    target_type: Literal["GLOBAL", "TEACHER", "COHORT", "CLASSROOM"] = "GLOBAL"
    target_id: Optional[int] = None
    rule_type: Literal["MUST_SCHEDULE", "FORBID_SCHEDULE", "PREFER_SCHEDULE"] = "MUST_SCHEDULE"
    day_of_week: int = 0  # 0=每天, 1..7=周一至周日
    period_index: int = 1  # 1=(1-2节)
    remark: Optional[str] = None


class PolicyRuleOut(PolicyRuleCreate):
    id: int
    is_active: bool


@router.get("/policy-rules", response_model=List[PolicyRuleOut])
def list_policy_rules(
    semester_id: Optional[int] = Query(None),
    target_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(SchedulePolicyRule).filter(SchedulePolicyRule.is_active.is_(True))
    if semester_id is not None:
        q = q.filter(SchedulePolicyRule.semester_id == semester_id)
    if target_type:
        q = q.filter(SchedulePolicyRule.target_type == target_type)
    return [
        PolicyRuleOut(
            id=r.id,
            semester_id=r.semester_id,
            target_type=r.target_type,
            target_id=r.target_id,
            rule_type=r.rule_type,
            day_of_week=r.day_of_week,
            period_index=r.period_index,
            is_active=r.is_active,
            remark=r.remark,
        )
        for r in q.order_by(SchedulePolicyRule.id.desc()).all()
    ]


@router.post("/policy-rules", response_model=PolicyRuleOut)
def create_policy_rule(payload: PolicyRuleCreate, db: Session = Depends(get_db)):
    row = SchedulePolicyRule(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return PolicyRuleOut(
        id=row.id,
        semester_id=row.semester_id,
        target_type=row.target_type,
        target_id=row.target_id,
        rule_type=row.rule_type,
        day_of_week=row.day_of_week,
        period_index=row.period_index,
        is_active=row.is_active,
        remark=row.remark,
    )


@router.delete("/policy-rules/{rule_id}")
def delete_policy_rule(rule_id: int, db: Session = Depends(get_db)):
    row = db.query(SchedulePolicyRule).filter(SchedulePolicyRule.id == rule_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    db.delete(row)
    db.commit()
    return {"deleted_id": rule_id}
