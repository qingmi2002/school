"""
T1.3 教务 Excel 双模式导入网关与冲突诊断批注导出引擎
- 模式 A (TASK_ONLY)：解析《教学任务书.xlsx》，前置 Schema 与脏数据 100% 拦截。
- 模式 B (PRE_SCHEDULED)：解析《预排课表.xlsx》，叠加单院系/全校碰撞检测（公共课锁定、跨系兼课、机房黑白名单、容量、软环境、单双周复用）。
- 导出带原生 openpyxl 中文批注与红色高亮的《冲突诊断 Excel》。
"""
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

from app.importer.schemas import (
    ImportContext,
    ImportParseResult,
    ParsedPreScheduleRow,
    ParsedTaskRow,
    RowIssue,
)


WEEK_TYPE_MAP = {
    "0": 0, "全周": 0, "全": 0, "": 0,
    "1": 1, "单周": 1, "单": 1,
    "2": 2, "双周": 2, "双": 2,
}

CATEGORY_MAP = {
    "THEORY": "THEORY", "纯理论": "THEORY", "理论": "THEORY", "理论课": "THEORY",
    "LAB": "LAB", "纯上机": "LAB", "实验": "LAB", "上机": "LAB", "实训": "LAB",
    "MIXED": "MIXED", "理实一体": "MIXED", "混合": "MIXED",
}

DAY_MAP = {
    "1": 1, "周一": 1, "星期一": 1,
    "2": 2, "周二": 2, "星期二": 2,
    "3": 3, "周三": 3, "星期三": 3,
    "4": 4, "周四": 4, "星期四": 4,
    "5": 5, "周五": 5, "星期五": 5,
    "6": 6, "周六": 6, "星期六": 6,
    "7": 7, "周日": 7, "星期日": 7, "星期天": 7,
}


def _weeks_overlap(w1: int, w2: int) -> bool:
    return w1 == 0 or w2 == 0 or w1 == w2


def _clean_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _split_tags(val) -> List[str]:
    raw = _clean_str(val)
    if not raw:
        return []
    for sep in ("，", ";", "；", "/"):
        raw = raw.replace(sep, ",")
    return [x.strip() for x in raw.split(",") if x.strip()]


class ExcelImportGateway:
    """双模式 Excel 解析与碰撞检测网关"""

    def __init__(self, context: ImportContext):
        self.ctx = context

    def _map_headers(self, header_cells: List[str]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        alias_lookup: Dict[str, str] = {}
        for canonical, aliases in self.ctx.column_aliases.items():
            for a in aliases:
                alias_lookup[a.strip().lower()] = canonical

        for idx, text in enumerate(header_cells):
            key = _clean_str(text).lower()
            if key in alias_lookup:
                mapping[alias_lookup[key]] = idx
        return mapping

    def _detect_merged_rows(self, ws) -> set:
        merged_rows = set()
        for rng in ws.merged_cells.ranges:
            for r in range(rng.min_row, rng.max_row + 1):
                if r >= 2:
                    merged_rows.add(r)
        return merged_rows

    def parse_and_validate(
        self,
        excel_bytes: bytes,
        import_type: str = "TASK_ONLY",
    ) -> ImportParseResult:
        wb = load_workbook(BytesIO(excel_bytes), data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return ImportParseResult(
                import_type=import_type,
                scope=self.ctx.scope,
                status="ROLLED_BACK",
                total_rows=0,
                valid_rows=0,
                conflict_rows=0,
                issues=[RowIssue(row_number=1, severity="ERROR", messages=["Excel 文件为空，未检测到表头"])],
            )

        header_map = self._map_headers([_clean_str(c) for c in rows[0]])
        required_cols = ["course_code", "course_name", "teacher_username", "cohort_codes", "total_students"]
        if import_type == "PRE_SCHEDULED":
            required_cols.extend(["day_of_week", "period_index", "room_code"])

        missing_cols = [c for c in required_cols if c not in header_map]
        if missing_cols:
            return ImportParseResult(
                import_type=import_type,
                scope=self.ctx.scope,
                status="ROLLED_BACK",
                total_rows=max(len(rows) - 1, 0),
                valid_rows=0,
                conflict_rows=max(len(rows) - 1, 0),
                issues=[
                    RowIssue(
                        row_number=1,
                        severity="ERROR",
                        messages=[f"缺少必需列：{', '.join(missing_cols)}，请核对模板表头"],
                    )
                ],
            )

        merged_rows = self._detect_merged_rows(ws)

        issues: List[RowIssue] = []
        parsed_tasks: List[ParsedTaskRow] = []
        parsed_pre: List[ParsedPreScheduleRow] = []

        # 批次内占用追踪（用于模式 B 内部撞车检测）
        batch_room_occ: List[Tuple[int, int, int, str, int]] = []  # (day, period, week_type, room, row)
        batch_teacher_occ: List[Tuple[int, int, int, str, int]] = []
        batch_cohort_occ: List[Tuple[int, int, int, str, int]] = []

        total_data_rows = 0

        for row_idx, row_vals in enumerate(rows[1:], start=2):
            if all(_clean_str(v) == "" for v in row_vals):
                continue
            total_data_rows += 1
            row_errors: List[str] = []
            severity = "ERROR"

            if row_idx in merged_rows:
                row_errors.append("检测到合并单元格，请取消合并并补全每行数据后重新导入")

            def get_val(col_key: str) -> str:
                pos = header_map.get(col_key)
                if pos is None or pos >= len(row_vals):
                    return ""
                return _clean_str(row_vals[pos])

            course_code = get_val("course_code")
            course_name = get_val("course_name")
            raw_cat = get_val("course_category") or "THEORY"
            teacher_username = get_val("teacher_username")
            cohort_codes = _split_tags(get_val("cohort_codes"))
            raw_sessions = get_val("weekly_sessions") or "1"
            raw_week_type = get_val("week_type") or "0"
            raw_students = get_val("total_students")
            env_tags = _split_tags(get_val("required_env_tags"))

            if not course_code:
                row_errors.append("缺少必填字段：课程代码")
            if not course_name:
                row_errors.append("缺少必填字段：课程名称")
            if not teacher_username:
                row_errors.append("缺少必填字段：教师工号")
            elif self.ctx.valid_teachers and teacher_username not in self.ctx.valid_teachers:
                row_errors.append(f"教师工号 '{teacher_username}' 未在师资库中登记")

            if not cohort_codes:
                row_errors.append("缺少必填字段：行政班代码")
            elif self.ctx.valid_cohorts:
                unknown_cohorts = [c for c in cohort_codes if c not in self.ctx.valid_cohorts]
                if unknown_cohorts:
                    row_errors.append(f"未知行政班代码：{', '.join(unknown_cohorts)}")

            course_category = CATEGORY_MAP.get(raw_cat.upper()) or CATEGORY_MAP.get(raw_cat)
            if not course_category:
                row_errors.append(f"非法课程类型 '{raw_cat}'（仅支持 THEORY/LAB/MIXED 或 理论/实验/理实一体）")

            try:
                weekly_sessions = int(float(raw_sessions))
                if weekly_sessions <= 0:
                    row_errors.append("周大课次数必须大于 0")
            except ValueError:
                weekly_sessions = 0
                row_errors.append(f"周大课次数格式非法：'{raw_sessions}'")

            week_type = WEEK_TYPE_MAP.get(raw_week_type)
            if week_type is None:
                row_errors.append(f"非法单双周属性 '{raw_week_type}'（仅支持 全周/单周/双周 或 0/1/2）")

            try:
                total_students = int(float(raw_students))
                if total_students <= 0:
                    row_errors.append("合班人数必须大于 0")
            except ValueError:
                total_students = 0
                row_errors.append(f"合班人数格式非法：'{raw_students}'")

            if import_type == "TASK_ONLY":
                if row_errors:
                    issues.append(RowIssue(row_number=row_idx, severity="ERROR", messages=row_errors))
                else:
                    parsed_tasks.append(
                        ParsedTaskRow(
                            row_number=row_idx,
                            course_code=course_code,
                            course_name=course_name,
                            course_category=course_category,
                            teacher_username=teacher_username,
                            cohort_codes=cohort_codes,
                            weekly_sessions=weekly_sessions,
                            week_type=week_type,
                            total_students=total_students,
                            required_env_tags=env_tags,
                        )
                    )
                continue

            # 模式 B：预排课表校验与全校/单院系碰撞检测
            raw_day = get_val("day_of_week")
            raw_period = get_val("period_index")
            room_code = get_val("room_code")

            day_of_week = DAY_MAP.get(raw_day)
            if day_of_week is None:
                row_errors.append(f"非法星期值 '{raw_day}'（应为 1-7 或 周一至周日）")

            try:
                period_index = int(float(raw_period))
                if period_index < 1 or period_index > 10:
                    row_errors.append(f"大节编号越界：{period_index}")
            except ValueError:
                period_index = 0
                row_errors.append(f"大节编号格式非法：'{raw_period}'")

            if not room_code:
                row_errors.append("缺少必填字段：教室编号")
            elif self.ctx.rooms:
                room_meta = self.ctx.rooms.get(room_code)
                if room_meta is None:
                    row_errors.append(f"教室编号 '{room_code}' 不存在")
                else:
                    if total_students > 0 and room_meta.capacity < total_students:
                        row_errors.append(
                            f"教室 {room_code} 容量({room_meta.capacity})小于合班人数({total_students})"
                        )
                    if env_tags and not set(env_tags).issubset(set(room_meta.env_tags)):
                        missing_tags = sorted(set(env_tags) - set(room_meta.env_tags))
                        row_errors.append(f"教室 {room_code} 缺少必需软件环境标签：{missing_tags}")
                    if room_meta.allow_course_codes or room_meta.allow_categories:
                        ok_allow = (course_code in room_meta.allow_course_codes) or (
                            course_category in room_meta.allow_categories
                        )
                        if not ok_allow:
                            row_errors.append(f"机房 {room_code} 设有白名单限制，不允许当前课程进入")
                    if (course_code in room_meta.deny_course_codes) or (
                        course_category in room_meta.deny_categories
                    ):
                        row_errors.append(f"机房 {room_code} 黑名单禁止排入当前课程/类型({course_category})")

            # 若基础字段完整，执行时空冲突碰撞检测
            if day_of_week is not None and period_index > 0 and week_type is not None:
                if (teacher_username, day_of_week, period_index) in self.ctx.teacher_hard_unavailable:
                    severity = "CONFLICT"
                    row_errors.append(f"教师 {teacher_username} 在周{day_of_week}第{period_index}大节已设硬性禁排")

                # 1. 与数据库已有占用（公共课锁定、全校其他系部课表）碰撞检测
                for occ in self.ctx.existing_occupancies:
                    if occ.day_of_week != day_of_week or occ.period_index != period_index:
                        continue
                    if not _weeks_overlap(week_type, occ.week_type):
                        continue
                    if occ.room_code and room_code and occ.room_code == room_code:
                        severity = "CONFLICT"
                        row_errors.append(f"教室 {room_code} 在周{day_of_week}第{period_index}大节与【{occ.source_label}】冲突")
                    if occ.teacher_username and teacher_username and occ.teacher_username == teacher_username:
                        severity = "CONFLICT"
                        row_errors.append(f"教师 {teacher_username} 在周{day_of_week}第{period_index}大节与【{occ.source_label}】发生跨系/公共课撞车")
                    if occ.cohort_code and occ.cohort_code in cohort_codes:
                        severity = "CONFLICT"
                        row_errors.append(f"行政班 {occ.cohort_code} 在周{day_of_week}第{period_index}大节已被【{occ.source_label}】锁定占用")

                # 2. 批次内自撞检测
                for d, p, wt, rc, prev_row in batch_room_occ:
                    if d == day_of_week and p == period_index and rc == room_code and _weeks_overlap(week_type, wt):
                        severity = "CONFLICT"
                        row_errors.append(f"教室 {room_code} 与本表第 {prev_row} 行发生时间冲突")
                for d, p, wt, tu, prev_row in batch_teacher_occ:
                    if d == day_of_week and p == period_index and tu == teacher_username and _weeks_overlap(week_type, wt):
                        severity = "CONFLICT"
                        row_errors.append(f"教师 {teacher_username} 与本表第 {prev_row} 行发生时间冲突")
                for c in cohort_codes:
                    for d, p, wt, cc, prev_row in batch_cohort_occ:
                        if d == day_of_week and p == period_index and cc == c and _weeks_overlap(week_type, wt):
                            severity = "CONFLICT"
                            row_errors.append(f"行政班 {c} 与本表第 {prev_row} 行发生时间冲突")

            if row_errors:
                issues.append(RowIssue(row_number=row_idx, severity=severity, messages=row_errors))
            else:
                batch_room_occ.append((day_of_week, period_index, week_type, room_code, row_idx))
                batch_teacher_occ.append((day_of_week, period_index, week_type, teacher_username, row_idx))
                for c in cohort_codes:
                    batch_cohort_occ.append((day_of_week, period_index, week_type, c, row_idx))

                parsed_pre.append(
                    ParsedPreScheduleRow(
                        row_number=row_idx,
                        course_code=course_code,
                        course_name=course_name,
                        course_category=course_category,
                        teacher_username=teacher_username,
                        cohort_codes=cohort_codes,
                        weekly_sessions=weekly_sessions,
                        week_type=week_type,
                        total_students=total_students,
                        required_env_tags=env_tags,
                        day_of_week=day_of_week,
                        period_index=period_index,
                        room_code=room_code,
                    )
                )

        valid_count = len(parsed_tasks) if import_type == "TASK_ONLY" else len(parsed_pre)
        conflict_count = len(issues)
        if conflict_count == 0:
            status = "SUCCESS"
        elif valid_count > 0:
            status = "PARTIAL_CONFLICT"
        else:
            status = "ROLLED_BACK"

        return ImportParseResult(
            import_type=import_type,
            scope=self.ctx.scope,
            status=status,
            total_rows=total_data_rows,
            valid_rows=valid_count,
            conflict_rows=conflict_count,
            issues=issues,
            parsed_tasks=parsed_tasks,
            parsed_pre_schedules=parsed_pre,
        )


def export_annotated_conflict_excel(original_excel_bytes: bytes, result: ImportParseResult) -> bytes:
    """在原始 Excel 上标红冲突行、追加中文诊断列并写入原生 openpyxl 单元格批注。"""
    wb = load_workbook(BytesIO(original_excel_bytes))
    ws = wb.active

    diag_col = ws.max_column + 1
    header_cell = ws.cell(row=1, column=diag_col, value="冲突诊断结果")
    header_cell.font = Font(bold=True, color="FFFFFF")
    header_cell.fill = PatternFill(start_color="B91C1C", end_color="B91C1C", fill_type="solid")
    header_cell.alignment = Alignment(horizontal="center", vertical="center")

    err_fill = PatternFill(start_color="FFE4E1", end_color="FFE4E1", fill_type="solid")
    issue_by_row = {item.row_number: item for item in result.issues}

    for row_num, issue in issue_by_row.items():
        summary = "；".join(issue.messages)
        for col_idx in range(1, diag_col + 1):
            ws.cell(row=row_num, column=col_idx).fill = err_fill
        ws.cell(row=row_num, column=diag_col, value=summary)
        first_cell = ws.cell(row=row_num, column=1)
        first_cell.comment = Comment(text=f"【{issue.severity}】{summary}", author="SmartSchedule冲突检测网关")

    ws.column_dimensions[ws.cell(row=1, column=diag_col).column_letter].width = 48

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def build_excel_template(import_type: str = "TASK_ONLY") -> bytes:
    """一键生成标准模式 A（教学任务书）或模式 B（预排课表）Excel 模板。"""
    wb = Workbook()
    ws = wb.active
    if import_type == "PRE_SCHEDULED":
        ws.title = "预排课表模板"
        headers = [
            "课程代码", "课程名称", "课程类型", "教师工号", "行政班代码",
            "周大课次数", "单双周", "合班人数", "软件环境标签", "星期", "大节", "教室编号",
        ]
        sample = [
            "CS201", "数据结构实验", "LAB", "T1001", "CS2401,CS2402",
            1, "单周", 56, "Linux,Python", "周一", 2, "LAB-402",
        ]
    else:
        ws.title = "教学任务书模板"
        headers = [
            "课程代码", "课程名称", "课程类型", "教师工号", "行政班代码",
            "周大课次数", "单双周", "合班人数", "软件环境标签",
        ]
        sample = [
            "CS101", "操作系统原理", "THEORY", "T1001", "CS2401,CS2402",
            2, "全周", 60, "",
        ]

    ws.append(headers)
    ws.append(sample)

    header_fill = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    for col_idx in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[c.column_letter].width = 16

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
