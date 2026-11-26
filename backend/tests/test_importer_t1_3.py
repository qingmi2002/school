"""T1.3 验收门禁测试：双模式 Excel 解析、100% 脏数据拦截、单双周碰撞检测与中文批注导出。"""
from io import BytesIO
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.importer import (
    ExcelImportGateway,
    ImportContext,
    build_excel_template,
    export_annotated_conflict_excel,
)
from app.importer.schemas import ExistingOccupancy, RoomMeta
from app.main import app


def _wb_to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_mode_a_dirty_data_100_percent_interception():
    wb = Workbook()
    ws = wb.active
    ws.append(["课程代码", "课程名称", "课程类型", "教师工号", "行政班代码", "周大课次数", "单双周", "合班人数"])
    # 第2行：正常数据
    ws.append(["CS101", "数据结构", "THEORY", "T001", "C01,C02", 2, "全周", 60])
    # 第3行：脏数据（缺失课程名、未知教师、负数人数、非法单双周）
    ws.append(["CS102", "", "THEORY", "T999", "C01", 1, "三周", -10])
    # 第4-5行：合并单元格脏数据
    ws.append(["CS103", "算法", "LAB", "T001", "C01", 1, "单周", 30])
    ws.append(["CS103", "算法", "LAB", "T001", "C02", 1, "双周", 30])
    ws.merge_cells("A4:A5")

    ctx = ImportContext(
        scope="SINGLE_DEPT",
        valid_teachers={"T001"},
        valid_cohorts={"C01", "C02"},
    )
    res = ExcelImportGateway(ctx).parse_and_validate(_wb_to_bytes(wb), import_type="TASK_ONLY")
    assert res.total_rows == 4
    assert res.valid_rows == 1
    assert res.conflict_rows == 3
    assert res.status == "PARTIAL_CONFLICT"

    issue_map = {i.row_number: "；".join(i.messages) for i in res.issues}
    assert "缺少必填字段：课程名称" in issue_map[3]
    assert "未在师资库中登记" in issue_map[3]
    assert "合班人数必须大于 0" in issue_map[3]
    assert "合并单元格" in issue_map[4]
    assert "合并单元格" in issue_map[5]


def test_mode_b_collision_detection_odd_even_reuse_and_annotated_export():
    wb = Workbook()
    ws = wb.active
    ws.append(["课程代码", "课程名称", "课程类型", "教师工号", "行政班代码", "周大课次数", "单双周", "合班人数", "软件环境标签", "星期", "大节", "教室编号"])
    # 第2行：单周实验课（合法）
    ws.append(["CS201", "Linux实验A", "LAB", "T001", "C01", 1, "单周", 40, "Linux", "周一", 1, "LAB-402"])
    # 第3行：双周实验课复用同一机房同一时段（合法！）
    ws.append(["CS202", "Linux实验B", "LAB", "T001", "C01", 1, "双周", 40, "Linux", "周一", 1, "LAB-402"])
    # 第4行：与校级公共课锁定撞车 + 机房黑名单拦截理论课
    ws.append(["CS301", "离散数学", "THEORY", "T002", "C02", 1, "全周", 40, "", "周二", 2, "LAB-402"])

    raw_bytes = _wb_to_bytes(wb)
    ctx = ImportContext(
        scope="SCHOOL_WIDE",
        valid_teachers={"T001", "T002"},
        valid_cohorts={"C01", "C02"},
        rooms={
            "LAB-402": RoomMeta(
                room_code="LAB-402",
                capacity=50,
                room_type="COMPUTER_LAB",
                env_tags=["Linux", "Python"],
                deny_categories=["THEORY"],
            )
        },
        existing_occupancies=[
            ExistingOccupancy(
                day_of_week=2,
                period_index=2,
                week_type=0,
                cohort_code="C02",
                source_label="校级公共课-大学英语",
            )
        ],
    )
    res = ExcelImportGateway(ctx).parse_and_validate(raw_bytes, import_type="PRE_SCHEDULED")
    assert res.valid_rows == 2
    assert res.conflict_rows == 1
    assert res.issues[0].row_number == 4
    msg = "；".join(res.issues[0].messages)
    assert "黑名单禁止" in msg
    assert "校级公共课-大学英语" in msg

    # 验证导出带原生 openpyxl 中文批注的《冲突诊断 Excel》
    annotated_bytes = export_annotated_conflict_excel(raw_bytes, res)
    wb_out = load_workbook(BytesIO(annotated_bytes))
    ws_out = wb_out.active
    assert ws_out.cell(row=1, column=13).value == "冲突诊断结果"
    assert "校级公共课-大学英语" in str(ws_out.cell(row=4, column=13).value)
    assert ws_out.cell(row=4, column=1).comment is not None
    assert "黑名单禁止" in ws_out.cell(row=4, column=1).comment.text


def test_import_api_template_and_upload():
    client = TestClient(app)
    r_tpl = client.get("/api/v1/import/template/TASK_ONLY")
    assert r_tpl.status_code == 200
    assert len(r_tpl.content) > 100

    tpl_bytes = build_excel_template("TASK_ONLY")
    r_val = client.post(
        "/api/v1/import/validate?import_type=TASK_ONLY&scope=SINGLE_DEPT",
        files={"file": ("tasks.xlsx", tpl_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r_val.status_code == 200
    body = r_val.json()
    assert body["status"] == "SUCCESS"
    assert body["valid_rows"] == 1
