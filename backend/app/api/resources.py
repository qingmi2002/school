"""
V1.3 高内聚动态资源管理与集中导入中心 API：
- 系统自定义配置、排课大周期（学期）
- 教学楼（独立表）、教室（固定/流动）、班级、教师、学生全动态数据库 CRUD
- 6-Sheet 基础数据集中导入模板下载与批量幂等入库
- 统一自定义排课规则引擎
"""
from typing import List, Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.db.session import get_db
from app.importer.master_data_importer import build_master_data_template, import_master_data_workbook
from app.models import (
    Building,
    Classroom,
    SchedulePolicyRule,
    Semester,
    StudentCohort,
    SysUser,
    SystemConfig,
)

router = APIRouter(prefix="/resources", tags=["resources-and-rules"])


# ---------- 1. 系统配置 ----------
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


# ---------- 2. 排课大周期（学期） ----------
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
    return [SemesterOut(id=r.id, code=r.code, name=r.name, total_weeks=r.total_weeks, start_date=r.start_date, end_date=r.end_date, is_current=r.is_current) for r in rows]


@router.post("/semesters", response_model=SemesterOut)
def create_semester(payload: SemesterCreate, db: Session = Depends(get_db)):
    if payload.is_current:
        db.query(Semester).update({Semester.is_current: False})
    row = Semester(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return SemesterOut(id=row.id, code=row.code, name=row.name, total_weeks=row.total_weeks, start_date=row.start_date, end_date=row.end_date, is_current=row.is_current)


@router.patch("/semesters/{sem_id}/set-current")
def set_current_semester(sem_id: int, db: Session = Depends(get_db)):
    row = db.query(Semester).filter(Semester.id == sem_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="学期不存在")
    db.query(Semester).update({Semester.is_current: False})
    row.is_current = True
    db.commit()
    return {"current_semester_id": sem_id}


# ---------- 3. 教学楼管理（独立数据库表） ----------
class BuildingCreate(BaseModel):
    building_code: str
    building_name: str
    campus_org_id: int
    floors: int = 5
    remark: Optional[str] = None


class BuildingOut(BuildingCreate):
    id: int


@router.get("/buildings", response_model=List[BuildingOut])
def list_buildings(db: Session = Depends(get_db)):
    rows = db.query(Building).filter(Building.is_active.is_(True)).order_by(Building.building_code).all()
    return [BuildingOut(id=b.id, building_code=b.building_code, building_name=b.building_name, campus_org_id=b.campus_org_id, floors=b.floors, remark=b.remark) for b in rows]


@router.post("/buildings", response_model=BuildingOut)
def create_building(payload: BuildingCreate, db: Session = Depends(get_db)):
    b = Building(**payload.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return BuildingOut(id=b.id, building_code=b.building_code, building_name=b.building_name, campus_org_id=b.campus_org_id, floors=b.floors, remark=b.remark)


@router.delete("/buildings/{building_id}")
def delete_building(building_id: int, db: Session = Depends(get_db)):
    b = db.query(Building).filter(Building.id == building_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="教学楼不存在")
    b.is_active = False
    db.commit()
    return {"deleted_id": building_id}


# ---------- 4. 教师管理 ----------
class TeacherCreate(BaseModel):
    username: str
    real_name: str
    org_node_id: int
    role_code: str = "TEACHER"
    teacher_priority: int = 1
    password: str = "123456"


class TeacherOut(BaseModel):
    id: int
    username: str
    real_name: str
    org_node_id: int
    role_code: str = "TEACHER"
    teacher_priority: int = 1


@router.get("/teachers", response_model=List[TeacherOut])
def list_teachers(org_node_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(SysUser).filter(SysUser.role_code.in_(["TEACHER", "TEACHING_LEAD"]), SysUser.is_active.is_(True))
    if org_node_id is not None:
        q = q.filter(SysUser.org_node_id == org_node_id)
    return [TeacherOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id, role_code=u.role_code, teacher_priority=int(getattr(u, "teacher_priority", 1) or 1)) for u in q.order_by(SysUser.id).all()]


@router.post("/teachers", response_model=TeacherOut)
def create_teacher(payload: TeacherCreate, db: Session = Depends(get_db)):
    role = payload.role_code if payload.role_code in ("TEACHER", "TEACHING_LEAD") else "TEACHER"
    u = SysUser(username=payload.username, real_name=payload.real_name, org_node_id=payload.org_node_id, role_code=role, teacher_priority=payload.teacher_priority, password_hash=hash_password(payload.password))
    db.add(u)
    db.commit()
    db.refresh(u)
    return TeacherOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id, role_code=u.role_code, teacher_priority=int(getattr(u, "teacher_priority", 1) or 1))


@router.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    u = db.query(SysUser).filter(SysUser.id == teacher_id, SysUser.role_code.in_(["TEACHER", "TEACHING_LEAD"])).first()
    if u is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    u.is_active = False
    db.commit()
    return {"deleted_id": teacher_id}


# ---------- 5. 班级管理 ----------
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
    return [CohortOut(id=c.id, cohort_code=c.cohort_code, cohort_name=c.cohort_name, org_node_id=c.org_node_id, grade_year=c.grade_year, student_count=c.student_count) for c in q.order_by(StudentCohort.id).all()]


@router.post("/cohorts", response_model=CohortOut)
def create_cohort(payload: CohortCreate, db: Session = Depends(get_db)):
    c = StudentCohort(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return CohortOut(id=c.id, cohort_code=c.cohort_code, cohort_name=c.cohort_name, org_node_id=c.org_node_id, grade_year=c.grade_year, student_count=c.student_count)


@router.delete("/cohorts/{cohort_id}")
def delete_cohort(cohort_id: int, db: Session = Depends(get_db)):
    c = db.query(StudentCohort).filter(StudentCohort.id == cohort_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    db.delete(c)
    db.commit()
    return {"deleted_id": cohort_id}


# ---------- 6. 学生管理 ----------
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
    return [StudentOut(id=u.id, username=u.username, real_name=u.real_name, org_node_id=u.org_node_id, cohort_id=u.cohort_id) for u in q.order_by(SysUser.id).all()]


@router.post("/students", response_model=StudentOut)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    u = SysUser(username=payload.username, real_name=payload.real_name, org_node_id=payload.org_node_id, cohort_id=payload.cohort_id, role_code="STUDENT", password_hash=hash_password(payload.password))
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


# ---------- 7. 教室管理（关联教学楼 + 固定/流动） ----------
class ClassroomCreate(BaseModel):
    room_code: str
    building: str
    building_id: Optional[int] = None
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
            id=r.id, room_code=r.room_code, building=r.building, building_id=r.building_id,
            owner_org_id=r.owner_org_id, capacity=r.capacity, room_type=r.room_type,
            usage_mode=r.usage_mode, fixed_cohort_id=r.fixed_cohort_id,
            sharing_policy=r.sharing_policy, env_tags=list(r.env_tags or []),
        )
        for r in q.order_by(Classroom.room_code).all()
    ]


@router.post("/classrooms", response_model=ClassroomOut)
def create_classroom(payload: ClassroomCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data.get("building_id"):
        b = db.query(Building).filter(Building.id == data["building_id"]).first()
        if b:
            data["building"] = b.building_name
    r = Classroom(**data)
    db.add(r)
    db.commit()
    db.refresh(r)
    return ClassroomOut(
        id=r.id, room_code=r.room_code, building=r.building, building_id=r.building_id,
        owner_org_id=r.owner_org_id, capacity=r.capacity, room_type=r.room_type,
        usage_mode=r.usage_mode, fixed_cohort_id=r.fixed_cohort_id,
        sharing_policy=r.sharing_policy, env_tags=list(r.env_tags or []),
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


# ---------- 8. 统一自定义排课规则 ----------
class PolicyRuleCreate(BaseModel):
    semester_id: int
    target_type: Literal["GLOBAL", "TEACHER", "COHORT", "CLASSROOM"] = "GLOBAL"
    target_id: Optional[int] = None
    rule_type: Literal["MUST_SCHEDULE", "FORBID_SCHEDULE", "PREFER_SCHEDULE"] = "MUST_SCHEDULE"
    day_of_week: int = 0
    period_index: int = 1
    remark: Optional[str] = None


class PolicyRuleOut(PolicyRuleCreate):
    id: int
    is_active: bool


@router.get("/policy-rules", response_model=List[PolicyRuleOut])
def list_policy_rules(semester_id: Optional[int] = Query(None), target_type: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(SchedulePolicyRule).filter(SchedulePolicyRule.is_active.is_(True))
    if semester_id is not None:
        q = q.filter(SchedulePolicyRule.semester_id == semester_id)
    if target_type:
        q = q.filter(SchedulePolicyRule.target_type == target_type)
    return [
        PolicyRuleOut(id=r.id, semester_id=r.semester_id, target_type=r.target_type, target_id=r.target_id, rule_type=r.rule_type, day_of_week=r.day_of_week, period_index=r.period_index, is_active=r.is_active, remark=r.remark)
        for r in q.order_by(SchedulePolicyRule.id.desc()).all()
    ]


@router.post("/policy-rules", response_model=PolicyRuleOut)
def create_policy_rule(payload: PolicyRuleCreate, db: Session = Depends(get_db)):
    row = SchedulePolicyRule(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return PolicyRuleOut(id=row.id, semester_id=row.semester_id, target_type=row.target_type, target_id=row.target_id, rule_type=row.rule_type, day_of_week=row.day_of_week, period_index=row.period_index, is_active=row.is_active, remark=row.remark)


@router.delete("/policy-rules/{rule_id}")
def delete_policy_rule(rule_id: int, db: Session = Depends(get_db)):
    row = db.query(SchedulePolicyRule).filter(SchedulePolicyRule.id == rule_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    db.delete(row)
    db.commit()
    return {"deleted_id": rule_id}


# ---------- 9. 一站式 6-Sheet 基础数据集中导入 ----------
@router.get("/master-import/template")
def download_master_import_template():
    data = build_master_data_template()
    filename = "基础数据集中导入模板(6合一).xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/master-import/upload")
async def upload_master_import_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    MAX_MASTER_UPLOAD_BYTES = 10 * 1024 * 1024
    if file.filename and not file.filename.lower().endswith('.xlsx'):
        raise HTTPException(status_code=400, detail='仅支持上传 .xlsx 文件')
    if len(raw) > MAX_MASTER_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail='上传文件超过 10MB 上限')
    if len(raw) < 4 or raw[:4] != b'PK\x03\x04':
        raise HTTPException(status_code=400, detail='文件格式损坏，非有效 .xlsx')
    return import_master_data_workbook(db, raw)
