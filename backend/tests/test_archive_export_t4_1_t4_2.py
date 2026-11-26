"""T4.1 + T4.2 验收门禁测试：独立目录 5 类产物零覆盖归档、双通道故障暂存、教务三家模板、PDF 报告与 .ics 订阅。"""
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.archive import CloudArchiveManager, LocalNASAdapter
from app.archive.storage_adapter import StorageBackend
from app.db.session import Base
from app.exporter import (
    export_edu_backfill_excel,
    export_health_pdf,
    export_icalendar_ics,
    export_multi_view_excel,
)
from app.models import (
    Classroom,
    OrgNode,
    ScheduleChangeAudit,
    ScheduleDetail,
    SchedulePlan,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.org import apply_org_preset


class _FailingBackend(StorageBackend):
    def upload_directory(self, staging_dir: Path, relative_folder: str) -> str:
        raise ConnectionError("NAS 挂载点网络抖动不可达")


@pytest.fixture()
def seeded_db():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    apply_org_preset(db, "single_dept_standalone", clear_existing=True)
    dept = db.query(OrgNode).first()
    sem = Semester(code="2026-2027-1", name="2026秋", total_weeks=18, is_current=True)
    ts1 = Timeslot(org_node_id=None, day_of_week=1, period_index=1, period_name="周一 1-2节")
    db.add_all([sem, ts1])
    db.flush()

    cohort = StudentCohort(cohort_code="CS2401", cohort_name="计科2401", org_node_id=dept.id, grade_year=2024, student_count=45)
    teacher = SysUser(username="T8001", real_name="陈老师", org_node_id=dept.id, role_code="TEACHER", password_hash="x")
    room = Classroom(room_code="LAB-402", building="信息楼", owner_org_id=dept.id, capacity=60, room_type="COMPUTER_LAB")
    db.add_all([cohort, teacher, room])
    db.flush()

    task = TeachingTask(
        semester_id=sem.id,
        org_node_id=dept.id,
        course_code="CS205",
        course_name="操作系统实验",
        course_category="LAB",
        teacher_id=teacher.id,
        cohort_ids=[cohort.id],
        weekly_sessions=1,
        week_type=1,  # 单周
        total_students=45,
    )
    plan = SchedulePlan(semester_id=sem.id, org_node_id=dept.id, plan_name="计科终版", version_tag="Plan_V1", run_mode="SINGLE_DEPT", fitness_score=98.5)
    db.add_all([task, plan])
    db.flush()

    db.add(ScheduleDetail(plan_id=plan.id, task_id=task.id, timeslot_id=ts1.id, classroom_id=room.id, week_type=1))
    db.commit()
    yield db, plan.id, teacher.id
    db.close()


def test_archive_isolated_folders_five_artifacts_and_fallback(seeded_db, tmp_path):
    db, plan_id, operator_id = seeded_db
    nas_root = tmp_path / "nas_cloud"
    staging_root = tmp_path / "staging"

    mgr = CloudArchiveManager(
        primary_backend=LocalNASAdapter(str(nas_root)),
        staging_root=str(staging_root),
    )
    r1 = mgr.archive_plan(db, plan_id=plan_id, operator_id=operator_id, vendor="ZHENGFANG")
    r2 = mgr.archive_plan(db, plan_id=plan_id, operator_id=operator_id, vendor="QINGGUO")

    assert r1["status"] == "SYNCED"
    assert r2["status"] == "SYNCED"
    assert r1["archive_path"] != r2["archive_path"]  # 两次归档独立隔离目录，绝不覆盖
    assert len(list(Path(r1["archive_path"]).iterdir())) == 5

    # 验证主通道故障时，产物安全暂存本地并记录 FAILED 审计单供 Celery 重试
    mgr_fail = CloudArchiveManager(
        primary_backend=_FailingBackend(),
        staging_root=str(staging_root),
    )
    r_fail = mgr_fail.archive_plan(db, plan_id=plan_id, operator_id=operator_id)
    assert r_fail["status"] == "FAILED"
    assert len(list(Path(r_fail["staging_dir"]).iterdir())) == 5
    audit = db.query(ScheduleChangeAudit).filter(ScheduleChangeAudit.id == r_fail["audit_id"]).first()
    assert audit.status == "FAILED"


def test_edu_backfill_multi_view_pdf_and_ics_exports(seeded_db):
    db, plan_id, teacher_id = seeded_db

    # 1. 三家主流教务回填模板导出校验
    for vendor in ("ZHENGFANG", "QINGGUO", "QIANGZHI"):
        xlsx_bytes = export_edu_backfill_excel(db, plan_id=plan_id, vendor=vendor)
        wb = load_workbook(BytesIO(xlsx_bytes))
        ws = wb.active
        assert ws.max_row == 2
        assert ws.cell(row=2, column=3).value == "CS205"

    # 2. 多维度 3-Sheet 总课表校验
    mv_bytes = export_multi_view_excel(db, plan_id=plan_id)
    wb_mv = load_workbook(BytesIO(mv_bytes))
    assert wb_mv.sheetnames == ["按班级课表", "按教师课表", "按机房教室课表"]

    # 3. PDF 自检报告校验
    pdf_bytes = export_health_pdf(db, plan_id=plan_id)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"Zero Conflict" in pdf_bytes

    # 4. .ics 日历订阅（含单双周 INTERVAL=2）校验
    ics_text = export_icalendar_ics(db, plan_id=plan_id, semester_start=date(2026, 9, 7), teacher_id=teacher_id)
    assert "BEGIN:VCALENDAR" in ics_text
    assert "RRULE:FREQ=WEEKLY;INTERVAL=2;" in ics_text
    assert "SUMMARY:操作系统实验 (单周)" in ics_text
