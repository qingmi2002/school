"""T1.3 双模式 Excel 导入与碰撞检测 API（支持模板下载与带批注诊断表导出）。"""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.importer.excel_gateway import (
    ExcelImportGateway,
    build_excel_template,
    export_annotated_conflict_excel,
)
from app.importer.schemas import ImportContext, ImportParseResult

router = APIRouter(prefix="/import", tags=["excel-import"])


@router.get("/template/{mode}")
def download_import_template(mode: Literal["TASK_ONLY", "PRE_SCHEDULED"]):
    data = build_excel_template(mode)
    filename = "教学任务书模板.xlsx" if mode == "TASK_ONLY" else "预排课表模板.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/validate", response_model=ImportParseResult)
async def validate_excel_upload(
    file: UploadFile = File(...),
    import_type: Literal["TASK_ONLY", "PRE_SCHEDULED"] = Query("TASK_ONLY"),
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = Query("SCHOOL_WIDE"),
):
    raw_bytes = await file.read()
    gateway = ExcelImportGateway(ImportContext(scope=scope))
    return gateway.parse_and_validate(raw_bytes, import_type=import_type)


@router.post("/validate-and-annotate")
async def validate_and_export_annotated_excel(
    file: UploadFile = File(...),
    import_type: Literal["TASK_ONLY", "PRE_SCHEDULED"] = Query("PRE_SCHEDULED"),
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = Query("SCHOOL_WIDE"),
):
    raw_bytes = await file.read()
    gateway = ExcelImportGateway(ImportContext(scope=scope))
    result = gateway.parse_and_validate(raw_bytes, import_type=import_type)
    annotated = export_annotated_conflict_excel(raw_bytes, result)
    filename = "冲突诊断结果.xlsx"
    return Response(
        content=annotated,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
