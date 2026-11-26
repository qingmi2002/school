"""T1.4 & T4.1 Celery 异步任务队列：排课求解 + 云盘归档失败自动重试。"""
from pathlib import Path

from app.archive.storage_adapter import LocalNASAdapter
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models import ScheduleChangeAudit, SchedulePlan
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


@celery_app.task(bind=True, max_retries=5, default_retry_delay=60, name="smart_schedule.retry_archive_sync")
def retry_archive_sync_task(self, audit_id: int) -> dict:
    """云盘/NAS 挂载瞬时抖动时的异步重试任务（从本地安全暂存目录补传）。"""
    db = SessionLocal()
    try:
        audit = db.query(ScheduleChangeAudit).filter(ScheduleChangeAudit.id == audit_id).first()
        if audit is None or audit.status == "SYNCED":
            return {"audit_id": audit_id, "status": "SKIPPED"}

        payload = audit.payload or {}
        staging_dir = Path(payload.get("staging_dir", ""))
        relative_folder = payload.get("relative_folder", "")
        if not staging_dir.exists():
            return {"audit_id": audit_id, "status": "MISSING_STAGING"}

        adapter = LocalNASAdapter()
        final_path = adapter.upload_directory(staging_dir, relative_folder)
        audit.status = "SYNCED"
        audit.retry_count += 1
        audit.remark = f"第 {audit.retry_count} 次异步重试归档成功"

        plan = db.query(SchedulePlan).filter(SchedulePlan.id == audit.plan_id).first()
        if plan:
            plan.cloud_archive_path = final_path
        db.commit()
        return {"audit_id": audit_id, "status": "SYNCED", "archive_path": final_path}
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc)
    finally:
        db.close()
