"""登录鉴权、分级角色信息、教师个人课表、学生班级课表（已集成 V1.4 整周实训提示与精确周次标签）。"""
from collections import defaultdict
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.week_plan import get_cohort_blocked_mask
from app.auth.security import create_access_token, get_current_user, get_optional_current_user, hash_password, verify_password
from app.auth.seed import seed_full_demo_data
from app.core.week_mask import build_week_mask, mask_to_label, subtract_blocked_weeks
from app.db.session import get_db
from app.locks.service import get_effective_locks_for_node
from app.models import (
    Classroom,
    CohortWeekPlan,
    OrgNode,
    OrgNodeManager,
    ScheduleDetail,
    SchedulePlan,
    Semester,
    StudentCohort,
    SystemConfig,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org.rbac import ROLE_LABELS, SCHEDULER_ROLES, assert_org_subtree_access, get_role_permissions

router = APIRouter(prefix="/auth", tags=["auth-and-personal"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserProfileOut(BaseModel):
    id: int
    username: str
    real_name: str
    role_code: str
    role_label: str
    org_node_id: int
    org_node_name: str
    tree_path: str
    cohort_id: Optional[int] = None
    cohort_name: Optional[str] = None
    permissions: List[str]
    managed_nodes: List[dict] = Field(default_factory=list)


_LOGIN_FAILURES: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SECONDS = 900
_LOGIN_MAX_FAILURES = 5


def reset_login_rate_limit() -> None:
    _LOGIN_FAILURES.clear()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    user: UserProfileOut


class PersonalCourseCard(BaseModel):
    course_code: str
    course_name: str
    day_of_week: int
    period_index: int
    period_name: str
    room_code: str
    building: str
    teacher_name: str
    cohort_names: List[str]
    week_type: int
    effective_weeks_label: str = "1-18周"
    is_public_lock: bool = False


class PersonalScheduleOut(BaseModel):
    owner_type: str
    owner_name: str
    sub_title: str
    plan_id: Optional[int]
    block_week_notices: List[str] = Field(default_factory=list)
    cards: List[PersonalCourseCard]


def _build_profile(db: Session, user: SysUser) -> UserProfileOut:
    org = db.query(OrgNode).filter(OrgNode.id == user.org_node_id).first()
    cohort = db.query(StudentCohort).filter(StudentCohort.id == user.cohort_id).first() if user.cohort_id else None
    return UserProfileOut(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        role_code=user.role_code,
        role_label=ROLE_LABELS.get(user.role_code, user.role_code),
        org_node_id=user.org_node_id,
        org_node_name=org.node_name if org else "",
        tree_path=org.tree_path if org else "/",
        cohort_id=user.cohort_id,
        cohort_name=cohort.cohort_name if cohort else None,
        permissions=get_role_permissions(user.role_code),
        managed_nodes=[
            {
                'org_node_id': m.org_node_id,
                'org_node_name': (db.query(OrgNode).filter(OrgNode.id == m.org_node_id).first().node_name if db.query(OrgNode).filter(OrgNode.id == m.org_node_id).first() else ''),
                'title_name': m.title_name,
                'permission_level': m.permission_level,
            }
            for m in db.query(OrgNodeManager).filter(OrgNodeManager.user_id == user.id, OrgNodeManager.is_active.is_(True)).all()
        ],
    )


@router.post("/seed-demo")
def seed_demo_api(
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    """V1.7 安全加固：仅空库冷启动、或超级管理员且演示模式开启时允许初始化演示数据。"""
    existing_users = db.query(SysUser).count()
    demo_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == "site_config").first()
    demo_enabled = True
    if demo_cfg and isinstance(demo_cfg.config_value, dict):
        demo_enabled = bool(demo_cfg.config_value.get("enable_demo_mode", True))
    if existing_users > 0:
        if not demo_enabled:
            raise HTTPException(status_code=403, detail="生产环境已关闭演示模式，禁止初始化演示数据")
        if current_user is not None and current_user.role_code != "SUPER_ADMIN":
            raise HTTPException(status_code=403, detail="仅校级超级管理员可重置演示数据")
    return seed_full_demo_data(db)


@router.post("/login", response_model=LoginResponse)
def login_api(req: LoginRequest, db: Session = Depends(get_db)):
    if db.query(SysUser).count() == 0:
        seed_full_demo_data(db)

    uname = req.username.strip()
    key = uname.lower()
    now = time.time()
    recent = [ts for ts in _LOGIN_FAILURES.get(key, []) if now - ts < _LOGIN_WINDOW_SECONDS]
    _LOGIN_FAILURES[key] = recent
    if len(recent) >= _LOGIN_MAX_FAILURES:
        raise HTTPException(status_code=429, detail="登录失败次数过多，账号已临时锁定 15 分钟")

    user = db.query(SysUser).filter(SysUser.username == uname, SysUser.is_active.is_(True)).first()
    if user is None or not verify_password(req.password, user.password_hash):
        _LOGIN_FAILURES[key].append(now)
        raise HTTPException(status_code=401, detail="工号/学号或密码错误（演示账号密码均为 123456）")

    _LOGIN_FAILURES.pop(key, None)
    token = create_access_token(user.id, user.username, user.role_code, user.org_node_id)
    return LoginResponse(
        access_token=token,
        must_change_password=(req.password == "123456"),
        user=_build_profile(db, user),
    )


@router.get("/me", response_model=UserProfileOut)
def get_me_api(current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_profile(db, current_user)


@router.get("/users", response_model=List[UserProfileOut])
def list_scoped_users_api(current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    my_org = db.query(OrgNode).filter(OrgNode.id == current_user.org_node_id).first()
    orgs = db.query(OrgNode).all()
    if current_user.role_code == "SUPER_ADMIN":
        allowed_org_ids = {o.id for o in orgs}
    else:
        allowed_org_ids = {o.id for o in orgs if my_org and o.tree_path.startswith(my_org.tree_path)}

    users = db.query(SysUser).filter(SysUser.org_node_id.in_(allowed_org_ids)).order_by(SysUser.id).all()
    return [_build_profile(db, u) for u in users]


@router.get("/my-schedule", response_model=PersonalScheduleOut)
def get_my_schedule_api(current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = (
        db.query(SchedulePlan)
        .filter(SchedulePlan.is_published.is_(True))
        .order_by(SchedulePlan.id.desc())
        .first()
    )
    ts_map = {t.id: t for t in db.query(Timeslot).all()}
    room_map = {r.id: r for r in db.query(Classroom).all()}
    user_map = {u.id: u for u in db.query(SysUser).all()}
    cohort_map = {c.id: c for c in db.query(StudentCohort).all()}

    cards: List[PersonalCourseCard] = []
    block_notices: List[str] = []

    if plan:
        # 收集整周实训/考试/停课横幅提示
        if current_user.role_code == "STUDENT" and current_user.cohort_id:
            bw_rows = (
                db.query(CohortWeekPlan)
                .filter(
                    CohortWeekPlan.semester_id == plan.semester_id,
                    CohortWeekPlan.cohort_id == current_user.cohort_id,
                    CohortWeekPlan.week_mode != "REGULAR",
                )
                .order_by(CohortWeekPlan.week_no)
                .all()
            )
            mode_cn = {"PRACTICUM": "整周实训", "INTERNSHIP": "校外实习", "EXAM": "考试周", "HOLIDAY": "停课"}
            for r in bw_rows:
                cname = r.block_course_name or mode_cn.get(r.week_mode, r.week_mode)
                block_notices.append(f"第{r.week_no}周：{cname}（{mode_cn.get(r.week_mode, r.week_mode)}，常规课暂停）")

        details = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == plan.id).all()
        tasks = {t.id: t for t in db.query(TeachingTask).filter(TeachingTask.semester_id == plan.semester_id).all()}

        for d in details:
            t = tasks.get(d.task_id)
            ts = ts_map.get(d.timeslot_id)
            rm = room_map.get(d.classroom_id)
            if not t or not ts or not rm:
                continue

            if current_user.role_code == "TEACHER" and t.teacher_id != current_user.id:
                continue
            if current_user.role_code == "STUDENT":
                if current_user.cohort_id is None or current_user.cohort_id not in (t.cohort_ids or []):
                    continue

            raw_m = d.week_mask or t.week_mask or build_week_mask(t.start_week, t.end_week, d.week_type)
            blocked_m = get_cohort_blocked_mask(db, plan.semester_id, list(t.cohort_ids or []))
            eff_label = mask_to_label(subtract_blocked_weeks(raw_m, blocked_m))

            cards.append(
                PersonalCourseCard(
                    course_code=t.course_code,
                    course_name=t.course_name,
                    day_of_week=ts.day_of_week,
                    period_index=ts.period_index,
                    period_name=ts.period_name,
                    room_code=rm.room_code,
                    building=rm.building,
                    teacher_name=user_map[t.teacher_id].real_name if t.teacher_id in user_map else "",
                    cohort_names=[cohort_map[cid].cohort_name for cid in (t.cohort_ids or []) if cid in cohort_map],
                    week_type=d.week_type,
                    effective_weeks_label=eff_label,
                )
            )

        if current_user.role_code == "STUDENT" and current_user.cohort_id:
            locks = get_effective_locks_for_node(db, plan.semester_id, current_user.org_node_id)
            blocked_m = get_cohort_blocked_mask(db, plan.semester_id, [current_user.cohort_id])
            for lk in locks.locks:
                if lk.cohort_id == current_user.cohort_id and lk.timeslot_id in ts_map:
                    ts = ts_map[lk.timeslot_id]
                    rm = room_map.get(lk.classroom_id) if lk.classroom_id else None
                    eff_label = mask_to_label(subtract_blocked_weeks(build_week_mask(1, 18, lk.week_type), blocked_m))
                    cards.append(
                        PersonalCourseCard(
                            course_code="PUBLIC",
                            course_name=lk.course_name,
                            day_of_week=ts.day_of_week,
                            period_index=ts.period_index,
                            period_name=ts.period_name,
                            room_code=rm.room_code if rm else "公共教学楼",
                            building=rm.building if rm else "校级统筹",
                            teacher_name="校级公共课教师",
                            cohort_names=[cohort_map[current_user.cohort_id].cohort_name]
                            if current_user.cohort_id in cohort_map
                            else [],
                            week_type=lk.week_type,
                            effective_weeks_label=eff_label,
                            is_public_lock=True,
                        )
                    )

    if current_user.role_code == "STUDENT":
        cname = cohort_map[current_user.cohort_id].cohort_name if current_user.cohort_id in cohort_map else "未分配班级"
        return PersonalScheduleOut(
            owner_type="STUDENT",
            owner_name=current_user.real_name,
            sub_title=f"行政班：{cname}",
            plan_id=plan.id if plan else None,
            block_week_notices=block_notices,
            cards=cards,
        )

    return PersonalScheduleOut(
        owner_type="TEACHER",
        owner_name=current_user.real_name,
        sub_title=f"工号：{current_user.username}",
        plan_id=plan.id if plan else None,
        block_week_notices=block_notices,
        cards=cards,
    )


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=64)


class ResetPasswordIn(BaseModel):
    user_id: int
    new_password: str = Field(default="123456", min_length=6, max_length=64)


@router.post("/change-password")
def change_password_api(
    payload: ChangePasswordIn,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """V1.7 师生及管理员自助修改本人密码。"""
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"updated": True, "username": current_user.username}


@router.post("/reset-password")
def reset_password_api(
    payload: ResetPasswordIn,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """V1.7 排课管理员重置指定用户密码。"""
    if current_user.role_code not in SCHEDULER_ROLES:
        raise HTTPException(status_code=403, detail="仅排课管理员可重置用户密码")
    target = db.query(SysUser).filter(SysUser.id == payload.user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="目标用户不存在")
    if target.role_code == "SUPER_ADMIN" and current_user.role_code != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="越权拦截：非校级超级管理员禁止重置超级管理员密码")
    assert_org_subtree_access(db, current_user, target.org_node_id)
    target.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"reset": True, "user_id": target.id, "username": target.username}


@router.get("/my-overview")
def get_my_personal_overview_api(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """V2.0 学生/普通教师专属个人工作台概览（聚合身份、班级届别/固定教室、课程总学时、实训提醒与管辖职务）。"""
    profile = _build_profile(db, current_user)
    sem = db.query(Semester).filter(Semester.is_current.is_(True)).first() or db.query(Semester).first()
    sem_id = sem.id if sem else None
    sem_name = sem.name if sem else "未设定学期"

    if current_user.role_code == "STUDENT":
        cohort = db.query(StudentCohort).filter(StudentCohort.id == current_user.cohort_id).first() if current_user.cohort_id else None
        fixed_room = (
            db.query(Classroom).filter(Classroom.fixed_cohort_id == cohort.id, Classroom.usage_mode == "FIXED").first()
            if cohort
            else None
        )
        courses_list = []
        block_notices = []
        if cohort and sem_id:
            t_map = {u.id: u.real_name for u in db.query(SysUser).all()}
            for t in db.query(TeachingTask).filter(TeachingTask.semester_id == sem_id).all():
                if cohort.id in (t.cohort_ids or []):
                    courses_list.append(
                        {
                            "course_code": t.course_code,
                            "course_name": t.course_name,
                            "teacher_name": t_map.get(t.teacher_id, ""),
                            "weekly_sessions": t.weekly_sessions,
                            "total_hours": getattr(t, "total_hours", None) or (t.weekly_sessions * 32),
                            "is_combined": len(t.cohort_ids or []) >= 2,
                        }
                    )
            for wp in db.query(CohortWeekPlan).filter(CohortWeekPlan.semester_id == sem_id, CohortWeekPlan.cohort_id == cohort.id, CohortWeekPlan.week_mode != "REGULAR").order_by(CohortWeekPlan.week_no).all():
                block_notices.append(f"第{wp.week_no}周：{wp.block_course_name or wp.week_mode}")
        sy = int(getattr(cohort, "study_years", 4) or 4) if cohort else 4
        gy = (getattr(cohort, "graduation_year", None) or (cohort.grade_year + sy)) if cohort else None
        return {
            "view_type": "STUDENT",
            "semester_name": sem_name,
            "profile": profile.model_dump(),
            "cohort_lifecycle": (
                {
                    "cohort_name": cohort.cohort_name,
                    "enroll_year": cohort.grade_year,
                    "study_years": sy,
                    "graduation_year": gy,
                    "status": getattr(cohort, "cohort_status", "ACTIVE"),
                    "fixed_room_code": fixed_room.room_code if fixed_room else "无固定教室(流动走班)",
                }
                if cohort
                else None
            ),
            "block_notices": block_notices,
            "my_courses": courses_list,
        }

    # 教师 / 教研室主任 / 管理员个人工作台概览
    my_tasks = db.query(TeachingTask).filter(TeachingTask.teacher_id == current_user.id).all()
    if sem_id:
        my_tasks = [t for t in my_tasks if t.semester_id == sem_id]
    cohort_map = {c.id: c.cohort_name for c in db.query(StudentCohort).all()}
    total_weekly = sum(int(t.weekly_sessions or 0) for t in my_tasks)
    total_hours = sum(int(getattr(t, "total_hours", None) or (t.weekly_sessions * 32)) for t in my_tasks)
    win_row = db.query(SystemConfig).filter(SystemConfig.config_key == "teacher_unavail_open").first()
    unavail_open = True if not win_row else (bool(win_row.config_value.get("is_open", True)) if isinstance(win_row.config_value, dict) else True)
    return {
        "view_type": "TEACHER",
        "semester_name": sem_name,
        "profile": profile.model_dump(),
        "teacher_priority": int(getattr(current_user, "teacher_priority", 1) or 1),
        "unavail_window_open": unavail_open,
        "total_weekly_sessions": total_weekly,
        "total_semester_hours": total_hours,
        "my_courses": [
            {
                "course_code": t.course_code,
                "course_name": t.course_name,
                "cohorts": [cohort_map[cid] for cid in (t.cohort_ids or []) if cid in cohort_map],
                "is_combined": len(t.cohort_ids or []) >= 2,
                "weekly_sessions": t.weekly_sessions,
                "total_hours": getattr(t, "total_hours", None) or (t.weekly_sessions * 32),
            }
            for t in my_tasks
        ],
    }
