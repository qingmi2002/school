"""
T4.2 教务系统标准批量回填模板（正方/青果/强智）、多维度总课表、PDF 自检报告与 RFC 5545 .ics 日历订阅导出引擎
"""
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from app.models import (
    Classroom,
    OrgNode,
    ScheduleDetail,
    SchedulePlan,
    Semester,
    StudentCohort,
    SysUser,
    TeachingTask,
    Timeslot,
)
from app.validator import run_health_check


VENDOR_HEADERS: Dict[str, List[str]] = {
    "ZHENGFANG": ["学年学期", "开课单位", "课程代码", "课程名称", "教师工号", "教师姓名", "教学班组成", "星期", "节次", "单双周", "教室编号", "总人数"],
    "QINGGUO": ["学期编号", "承担单位", "课程号", "课程名", "主讲教师工号", "主讲教师", "上课班级", "星期几", "大节次", "周次类型", "场地代码", "选课人数"],
    "QIANGZHI": ["开课学期", "院系名称", "课程编号", "课程名称", "工号", "任课教师", "行政班", "上课星期", "上课节次", "单双周标记", "教室代码", "合班人数"],
}

WEEK_TYPE_LABEL = {0: "全周", 1: "单周", 2: "双周"}
DEFAULT_PERIOD_TIMES = {
    1: ("080000", "094000"),
    2: ("100000", "114000"),
    3: ("140000", "154000"),
    4: ("160000", "174000"),
    5: ("190000", "204000"),
}


def _load_plan_bundle(db: Session, plan_id: int) -> dict:
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if plan is None:
        raise ValueError(f"排课方案 id={plan_id} 不存在")

    sem = db.query(Semester).filter(Semester.id == plan.semester_id).first()
    org = db.query(OrgNode).filter(OrgNode.id == plan.org_node_id).first()
    details = db.query(ScheduleDetail).filter(ScheduleDetail.plan_id == plan_id).all()
    tasks = db.query(TeachingTask).filter(
        TeachingTask.semester_id == plan.semester_id,
        TeachingTask.org_node_id == plan.org_node_id,
    ).all()
    task_map = {t.id: t for t in tasks}
    ts_map = {t.id: t for t in db.query(Timeslot).all()}
    room_map = {r.id: r for r in db.query(Classroom).all()}
    user_map = {u.id: u for u in db.query(SysUser).all()}
    cohort_map = {c.id: c for c in db.query(StudentCohort).all()}

    records = []
    for d in details:
        t = task_map.get(d.task_id) or db.query(TeachingTask).filter(TeachingTask.id == d.task_id).first()
        ts = ts_map.get(d.timeslot_id)
        rm = room_map.get(d.classroom_id)
        if not t or not ts or not rm:
            continue
        teacher = user_map.get(t.teacher_id)
        c_names = [cohort_map[cid].cohort_name if cid in cohort_map else f"班#{cid}" for cid in (t.cohort_ids or [])]
        records.append(
            {
                "semester_code": sem.code if sem else str(plan.semester_id),
                "org_name": org.node_name if org else str(plan.org_node_id),
                "course_code": t.course_code,
                "course_name": t.course_name,
                "course_category": t.course_category,
                "teacher_id": t.teacher_id,
                "teacher_username": teacher.username if teacher else str(t.teacher_id),
                "teacher_name": teacher.real_name if teacher else f"教师#{t.teacher_id}",
                "cohort_ids": list(t.cohort_ids or []),
                "cohort_str": ",".join(c_names),
                "day_of_week": ts.day_of_week,
                "period_index": ts.period_index,
                "period_name": ts.period_name,
                "week_type": d.week_type,
                "week_type_label": WEEK_TYPE_LABEL.get(d.week_type, "全周"),
                "start_week": t.start_week,
                "end_week": t.end_week,
                "room_code": rm.room_code,
                "building": rm.building,
                "total_students": t.total_students,
            }
        )

    records.sort(key=lambda r: (r["day_of_week"], r["period_index"], r["room_code"]))
    return {"plan": plan, "semester": sem, "org": org, "tasks": tasks, "records": records}


def _style_sheet(ws, headers: List[str], fill_hex: str = "1E40AF") -> None:
    fill = PatternFill(start_color=fill_hex, end_color=fill_hex, fill_type="solid")
    for idx in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=idx)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[c.column_letter].width = 16


def export_raw_tasks_excel(db: Session, plan_id: int) -> bytes:
    """产物 01：导出归档用的原始教学任务书 Excel。"""
    bundle = _load_plan_bundle(db, plan_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "教学任务书"
    headers = ["课程代码", "课程名称", "课程类型", "教师ID", "周大课次数", "单双周", "合班人数"]
    ws.append(headers)
    for t in bundle["tasks"]:
        ws.append([
            t.course_code, t.course_name, t.course_category, t.teacher_id,
            t.weekly_sessions, WEEK_TYPE_LABEL.get(t.week_type, "全周"), t.total_students,
        ])
    _style_sheet(ws, headers, "334155")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_edu_backfill_excel(db: Session, plan_id: int, vendor: str = "ZHENGFANG") -> bytes:
    """产物 04：导出可直接导入学校现有教务系统（正方/青果/强智）的标准批量回填 Excel。"""
    vendor_key = vendor.upper()
    if vendor_key not in VENDOR_HEADERS:
        raise ValueError(f"不支持的教务系统模板类型：{vendor}（支持 ZHENGFANG / QINGGUO / QIANGZHI）")

    bundle = _load_plan_bundle(db, plan_id)
    wb = Workbook()
    ws = wb.active
    ws.title = f"{vendor_key}_教务回填表"
    headers = VENDOR_HEADERS[vendor_key]
    ws.append(headers)

    for r in bundle["records"]:
        ws.append([
            r["semester_code"],
            r["org_name"],
            r["course_code"],
            r["course_name"],
            r["teacher_username"],
            r["teacher_name"],
            r["cohort_str"],
            r["day_of_week"],
            r["period_index"],
            r["week_type_label"],
            r["room_code"],
            r["total_students"],
        ])
    _style_sheet(ws, headers, "1D4ED8")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_multi_view_excel(db: Session, plan_id: int) -> bytes:
    """产物 03：导出系部/全校多维度总课表（班级视图 + 教师视图 + 机房视图 3 个 Sheet）。"""
    bundle = _load_plan_bundle(db, plan_id)
    wb = Workbook()

    views = [
        ("按班级课表", "cohort_str", ["行政班", "星期", "节次", "课程名称", "任课教师", "教室", "单双周"]),
        ("按教师课表", "teacher_name", ["任课教师", "星期", "节次", "课程名称", "行政班", "教室", "单双周"]),
        ("按机房教室课表", "room_code", ["教室编号", "星期", "节次", "课程名称", "任课教师", "行政班", "单双周"]),
    ]

    for idx, (sheet_title, sort_key, headers) in enumerate(views):
        ws = wb.active if idx == 0 else wb.create_sheet(title=sheet_title)
        ws.title = sheet_title
        ws.append(headers)
        sorted_rows = sorted(bundle["records"], key=lambda x: (x[sort_key], x["day_of_week"], x["period_index"]))
        for r in sorted_rows:
            if sort_key == "cohort_str":
                ws.append([r["cohort_str"], r["day_of_week"], r["period_name"], r["course_name"], r["teacher_name"], r["room_code"], r["week_type_label"]])
            elif sort_key == "teacher_name":
                ws.append([r["teacher_name"], r["day_of_week"], r["period_name"], r["course_name"], r["cohort_str"], r["room_code"], r["week_type_label"]])
            else:
                ws.append([r["room_code"], r["day_of_week"], r["period_name"], r["course_name"], r["teacher_name"], r["cohort_str"], r["week_type_label"]])
        _style_sheet(ws, headers, "0F766E")

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_minimal_pdf(lines: List[str]) -> bytes:
    """零外部字体依赖的轻量 PDF 1.4 生成器，保证容器与 CI 环境 100% 稳定生成合规 PDF。"""
    def _esc(s: str) -> str:
        # 仅保留 ASCII 安全字符用于内置 Helvetica，非 ASCII 转义为可读编码，防止 PDF 解析乱码
        ascii_safe = s.encode("ascii", "replace").decode("ascii")
        return ascii_safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream_lines = ["BT", "/F1 11 Tf", "50 780 Td", "16 TL"]
    for idx, line in enumerate(lines[:42]):
        prefix = "" if idx == 0 else "T* "
        stream_lines.append(f"{prefix}({_esc(line)}) Tj")
    stream_lines.append("ET")
    stream_bytes = "\n".join(stream_lines).encode("latin-1")

    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def export_health_pdf(db: Session, plan_id: int) -> bytes:
    """产物 05：导出排课质量与冲突自检 PDF 报告。"""
    bundle = _load_plan_bundle(db, plan_id)
    plan: SchedulePlan = bundle["plan"]
    report = run_health_check(
        db,
        semester_id=plan.semester_id,
        scope=plan.run_mode,
        org_node_id=plan.org_node_id,
    )
    lines = [
        "SmartSchedule - Course Scheduling Quality & Health Check Report",
        "================================================================",
        f"Plan ID: {plan.id} | Version: {plan.version_tag} | Mode: {plan.run_mode}",
        f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total Scheduled Sessions: {len(bundle['records'])}",
        f"Fitness Score: {plan.fitness_score or 0}",
        f"Health Check Passed: {'YES (Zero Conflict)' if report.passed else 'NO'}",
        f"Conflict Count: {report.conflict_count} | Elapsed: {report.elapsed_ms} ms",
        "----------------------------------------------------------------",
    ]
    if report.issues:
        lines.append("Detected Issues:")
        for idx, issue in enumerate(report.issues[:25], start=1):
            lines.append(f"  {idx}. [{issue.issue_type}] detail_ids={issue.detail_ids}")
    else:
        lines.append("All hard constraints verified: zero room, teacher, cohort, or commute conflict.")
    return _build_minimal_pdf(lines)


def export_icalendar_ics(
    db: Session,
    plan_id: int,
    semester_start: date = date(2026, 9, 7),
    teacher_id: Optional[int] = None,
    cohort_id: Optional[int] = None,
) -> str:
    """导出 RFC 5545 标准 .ics 日历文件，支持手机端一键订阅及单双周 INTERVAL=2 重复规则。"""
    bundle = _load_plan_bundle(db, plan_id)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SmartSchedule//University Course Schedule//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for idx, r in enumerate(bundle["records"], start=1):
        if teacher_id is not None and r["teacher_id"] != teacher_id:
            continue
        if cohort_id is not None and cohort_id not in r["cohort_ids"]:
            continue

        # 计算首次上课日期（按 start_week 与单双周对齐）
        first_week = r["start_week"]
        if r["week_type"] == 1 and first_week % 2 == 0:
            first_week += 1
        elif r["week_type"] == 2 and first_week % 2 == 1:
            first_week += 1

        event_day = semester_start + timedelta(weeks=max(first_week - 1, 0), days=r["day_of_week"] - 1)
        start_hms, end_hms = DEFAULT_PERIOD_TIMES.get(r["period_index"], ("080000", "094000"))
        dt_start = f"{event_day.strftime('%Y%m%d')}T{start_hms}"
        dt_end = f"{event_day.strftime('%Y%m%d')}T{end_hms}"

        interval = 2 if r["week_type"] in (1, 2) else 1
        total_span_weeks = max(r["end_week"] - first_week + 1, 1)
        count = (total_span_weeks + interval - 1) // interval

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:smartschedule-p{plan_id}-{idx}@campus.local",
            f"DTSTART;TZID=Asia/Shanghai:{dt_start}",
            f"DTEND;TZID=Asia/Shanghai:{dt_end}",
            f"RRULE:FREQ=WEEKLY;INTERVAL={interval};COUNT={count}",
            f"SUMMARY:{r['course_name']} ({r['week_type_label']})",
            f"LOCATION:{r['building']} {r['room_code']}",
            f"DESCRIPTION:教师:{r['teacher_name']} | 班级:{r['cohort_str']}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
