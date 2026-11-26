"""T4.1 & T4.2 云盘独立目录归档、教务回填 Excel、PDF 自检报告与 .ics 日历订阅 REST API。"""
from datetime import date
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.archive import CloudArchiveManager
from app.db.session import get_db
from app.exporter import (
    export_edu_backfill_excel,
    export_health_pdf,
    export_icalendar_ics,
    export_multi_view_excel,
)

router = APIRouter(prefix="/export", tags=["archive-and-export"])


@router.post("/plans/{plan_id}/archive")
def archive_plan_api(
    plan_id: int,
    operator_id: int = Query(1),
    vendor: Literal["ZHENGFANG", "QINGGUO", "QIANGZHI"] = Query("ZHENGFANG"),
    db: Session = Depends(get_db),
):
    try:
        return CloudArchiveManager().archive_plan(db, plan_id=plan_id, operator_id=operator_id, vendor=vendor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans/{plan_id}/edu-backfill")
def download_edu_backfill_api(
    plan_id: int,
    vendor: Literal["ZHENGFANG", "QINGGUO", "QIANGZHI"] = Query("ZHENGFANG"),
    db: Session = Depends(get_db),
):
    try:
        data = export_edu_backfill_excel(db, plan_id=plan_id, vendor=vendor)
        filename = f"教务回填模板_{vendor}_plan{plan_id}.xlsx"
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans/{plan_id}/multi-view")
def download_multi_view_excel_api(plan_id: int, db: Session = Depends(get_db)):
    try:
        data = export_multi_view_excel(db, plan_id=plan_id)
        filename = f"多维度总课表_plan{plan_id}.xlsx"
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans/{plan_id}/report.pdf")
def download_health_pdf_api(plan_id: int, db: Session = Depends(get_db)):
    try:
        data = export_health_pdf(db, plan_id=plan_id)
        filename = f"排课质量与冲突自检报告_plan{plan_id}.pdf"
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans/{plan_id}/calendar.ics")
def download_ics_api(
    plan_id: int,
    semester_start: date = Query(date(2026, 9, 7)),
    teacher_id: Optional[int] = Query(None),
    cohort_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        ics = export_icalendar_ics(
            db, plan_id=plan_id, semester_start=semester_start, teacher_id=teacher_id, cohort_id=cohort_id
        )
        return Response(
            content=ics.encode("utf-8"),
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=schedule_plan_{plan_id}.ics"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
