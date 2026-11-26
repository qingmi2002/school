"""T1.4 Celery 异步排课任务队列，支持多系部并发求解防阻塞。"""
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.solver.cp_sat_engine import CourseScheduleSolver
from app.solver.db_loader import load_solver_input_from_db, persist_solver_result


@celery_app.task(bind=True, name="smart_schedule.solve_plan")
def run_schedule_solve_task(
    self,
    semester_id: int,
    org_node_id: int,
    plan_name: str,
    run_mode: str = "SINGLE_DEPT",
    time_limit_seconds: float = 10.0,
) -> dict:
    self.update_state(state="PROGRESS", meta={"step": "loading_constraints"})
    db = SessionLocal()
    try:
        solver_input = load_solver_input_from_db(
            db=db,
            semester_id=semester_id,
            org_node_id=org_node_id,
            run_mode=run_mode,
            time_limit_seconds=time_limit_seconds,
        )
        self.update_state(state="PROGRESS", meta={"step": "solving_cp_sat"})
        result = CourseScheduleSolver(solver_input).solve()

        plan = persist_solver_result(
            db=db,
            semester_id=semester_id,
            org_node_id=org_node_id,
            plan_name=plan_name,
            run_mode=run_mode,
            result=result,
        )
        return {
            "plan_id": plan.id,
            "version_tag": plan.version_tag,
            "result": result.model_dump(),
        }
    finally:
        db.close()
