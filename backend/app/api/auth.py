"""登录鉴权、分级角色信息、教师个人课表、学生班级课表及一键初始化演示数据 API。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, get_current_user, verify_password
from app.auth.seed import seed_full_demo_data
from app.db.session import get_db
from app.locks.service import get_effective_locks_for_node
from app.models import (
    Classroom,
    OrgNode,
    ScheduleDetail,
    SchedulePlan,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org.rbac import ROLE_LABELS, get_role_permissions

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


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
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
    is_public_lock: bool = False


class PersonalScheduleOut(BaseModel):
    owner_type: str  # TEACHER / STUDENT
    owner_name: str
    sub_title: str
    plan_id: Optional[int]
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
    )


@router.post("/seed-demo")
def seed_demo_api(db: Session = Depends(get_db)):
    return seed_full_demo_data(db)


@router.post("/login", response_model=LoginResponse)
def login_api(req: LoginRequest, db: Session = Depends(get_db)):
    # 若库内尚无任何用户且请求默认演示账号，自动初始化演示数据实现开箱即用
    if db.query(SysUser).count() == 0:
        seed_full_demo_data(db)

    user = db.query(SysUser).filter(SysUser.username == req.username, SysUser.is_active.is_(True)).first()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="工号/学号或密码错误（演示账号密码均为 123456）")

    token = create_access_token(user.id, user.username, user.role_code, user.org_node_id)
    return LoginResponse(access_token=token, user=_build_profile(db, user))


@router.get("/me", response_model=UserProfileOut)
def get_me_api(current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_profile(db, current_user)


@router.get("/users", response_model=List[UserProfileOut])
def list_scoped_users_api(current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """分级权限查看管辖范围内的账号列表（校级看全校，院/系/专业级仅看子树）。"""
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
    """教师查看个人排课信息 / 学生查看所属行政班排课信息。"""
    plan = db.query(SchedulePlan).order_by(SchedulePlan.is_published.desc(), SchedulePlan.id.desc()).first()
    ts_map = {t.id: t for t in db.query(Timeslot).all()}
    room_map = {r.id: r for r in db.query(Classroom).all()}
    user_map = {u.id: u for u in db.query(SysUser).all()}
    cohort_map = {c.id: c for c in db.query(StudentCohort).all()}

    cards: List[PersonalCourseCard] = []

    if plan:
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
                )
            )

        # 学生同时叠加所属班级的校级公共课锁定
        if current_user.role_code == "STUDENT" and current_user.cohort_id:
            locks = get_effective_locks_for_node(db, plan.semester_id, current_user.org_node_id)
            for lk in locks.locks:
                if lk.cohort_id == current_user.cohort_id and lk.timeslot_id in ts_map:
                    ts = ts_map[lk.timeslot_id]
                    rm = room_map.get(lk.classroom_id) if lk.classroom_id else None
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
            cards=cards,
        )

    return PersonalScheduleOut(
        owner_type="TEACHER",
        owner_name=current_user.real_name,
        sub_title=f"工号：{current_user.username}",
        plan_id=plan.id if plan else None,
        cards=cards,
    )
