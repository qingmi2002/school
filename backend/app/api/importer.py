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
MAX_EXCEL_UPLOAD_BYTES = 10 * 1024 * 1024


def _validate_xlsx_bytes(filename: str | None, raw: bytes) -> None:
    if filename and not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持上传 .xlsx 格式的 Excel 文件")
    if len(raw) > MAX_EXCEL_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="上传文件超过 10MB 安全上限")
    if len(raw) < 4 or raw[:4] != b"PK\x03\x04":
        raise HTTPException(status_code=400, detail="文件内容不是合法的 .xlsx 压缩文档")


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
    _validate_xlsx_bytes(file.filename, raw_bytes)
    gateway = ExcelImportGateway(ImportContext(scope=scope))
    return gateway.parse_and_validate(raw_bytes, import_type=import_type)


@router.post("/validate-and-annotate")
async def validate_and_export_annotated_excel(
    file: UploadFile = File(...),
    import_type: Literal["TASK_ONLY", "PRE_SCHEDULED"] = Query("PRE_SCHEDULED"),
    scope: Literal["SINGLE_DEPT", "SCHOOL_WIDE"] = Query("SCHOOL_WIDE"),
):
    raw_bytes = await file.read()
    _validate_xlsx_bytes(file.filename, raw_bytes)
    gateway = ExcelImportGateway(ImportContext(scope=scope))
    result = gateway.parse_and_validate(raw_bytes, import_type=import_type)
    annotated = export_annotated_conflict_excel(raw_bytes, result)
    filename = "冲突诊断结果.xlsx"
    return Response(
        content=annotated,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
