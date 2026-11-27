"""T1.4 + V1.5 排课求解 REST API（支持一键同步排课落库、异步 Celery 提交与轻量试算）。"""
from typing import Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.auth.security import get_optional_current_user
from app.db.session import get_db
from app.org.rbac import assert_org_subtree_access
from app.models import OrgNode, Semester, SysUser
from app.solver.cp_sat_engine import CourseScheduleSolver
from app.solver.db_loader import load_solver_input_from_db, persist_solver_result
from app.solver.schemas import SolverInput, SolverResult
from app.tasks.schedule_tasks import run_schedule_solve_task

router = APIRouter(prefix="/solver", tags=["solver"])


class AsyncSolveRequest(BaseModel):
    semester_id: int
    org_node_id: int
    plan_name: str
    run_mode: str = "SINGLE_DEPT"
    time_limit_seconds: float = 10.0


class OneClickSolveRequest(BaseModel):
    semester_id: Optional[int] = None
    org_node_id: Optional[int] = None
    plan_name: Optional[str] = None
    run_mode: str = "SINGLE_DEPT"
    time_limit_seconds: float = 10.0


@router.post("/dry-run", response_model=SolverResult)
def solve_dry_run(payload: SolverInput):
    """同步轻量试算接口：不落库，直接返回 CP-SAT 求解结果与无解诊断。"""
    return CourseScheduleSolver(payload).solve()


@router.post("/one-click")
def one_click_solve_and_persist(
    req: OneClickSolveRequest,
    db: Session = Depends(get_db),
    current_user: Optional[SysUser] = Depends(get_optional_current_user),
):
    """V1.5 一键智能排课：自动体检基础数据 → CP-SAT 求解 → 落库生成方案 → 返回 plan_id 直接进入工作台微调。"""
    sem = (
        db.query(Semester).filter(Semester.id == req.semester_id).first()
        if req.semester_id
        else db.query(Semester).filter(Semester.is_current.is_(True)).first() or db.query(Semester).first()
    )
    if sem is None:
        raise HTTPException(status_code=400, detail="请先在「周期与规则」中创建学期")

    node = (
        db.query(OrgNode).filter(OrgNode.id == req.org_node_id).first()
        if req.org_node_id
        else db.query(OrgNode).filter(OrgNode.is_active.is_(True)).order_by(OrgNode.id).first()
    )
    if node is None:
        raise HTTPException(status_code=400, detail="请先初始化组织节点")

    assert_org_subtree_access(db, current_user, node.id)
    inp = load_solver_input_from_db(
        db=db,
        semester_id=sem.id,
        org_node_id=node.id,
        run_mode=req.run_mode,
        time_limit_seconds=req.time_limit_seconds,
    )
    if not inp.tasks:
        raise HTTPException(status_code=400, detail="当前学期暂无待排教学任务，请先在「课程与合班」录入班级选课任务")
    if not inp.rooms:
        raise HTTPException(status_code=400, detail="当前范围暂无可用教室/机房，请先在「基础数据」录入教室")
    if not inp.timeslots:
        raise HTTPException(status_code=400, detail="当前范围暂无时间片配置")

    result = CourseScheduleSolver(inp).solve()
    plan_name = req.plan_name or f"{node.node_name}_{sem.name}_一键排课方案"
    plan = persist_solver_result(
        db=db,
        semester_id=sem.id,
        org_node_id=node.id,
        plan_name=plan_name,
        run_mode=req.run_mode,
        result=result,
    )
    return {
        "plan_id": plan.id,
        "plan_name": plan.plan_name,
        "version_tag": plan.version_tag,
        "status": result.status,
        "solve_seconds": result.solve_seconds,
        "fitness_score": result.fitness_score,
        "scheduled_count": len(result.assignments),
        "unscheduled_count": len(result.unscheduled_diagnostics),
        "unscheduled_diagnostics": [d.model_dump() for d in result.unscheduled_diagnostics],
    }


@router.post("/solve")
def submit_async_solve(req: AsyncSolveRequest):
    """提交异步 Celery 排课求解任务，立即返回 task_id 防止阻塞。"""
    task = run_schedule_solve_task.delay(
        semester_id=req.semester_id,
        org_node_id=req.org_node_id,
        plan_name=req.plan_name,
        run_mode=req.run_mode,
        time_limit_seconds=req.time_limit_seconds,
    )
    return {"task_id": task.id, "status": "PENDING"}


@router.get("/tasks/{task_id}")
def get_solve_task_status(task_id: str):
    res = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "state": res.state,
        "result": res.result if res.ready() else res.info,
    }
