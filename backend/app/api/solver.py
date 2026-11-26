"""T1.4 排课求解 REST API（支持异步 Celery 提交与同步轻量试算）。"""
from celery.result import AsyncResult
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.celery_app import celery_app
from app.solver.cp_sat_engine import CourseScheduleSolver
from app.solver.schemas import SolverInput, SolverResult
from app.tasks.schedule_tasks import run_schedule_solve_task

router = APIRouter(prefix="/solver", tags=["solver"])


class AsyncSolveRequest(BaseModel):
    semester_id: int
    org_node_id: int
    plan_name: str
    run_mode: str = "SINGLE_DEPT"
    time_limit_seconds: float = 10.0


@router.post("/dry-run", response_model=SolverResult)
def solve_dry_run(payload: SolverInput):
    """同步轻量试算接口：不落库，直接返回 CP-SAT 求解结果与无解诊断。"""
    return CourseScheduleSolver(payload).solve()


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
