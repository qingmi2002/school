"""
V1.3 全动态基础数据集中导入引擎（单 Excel 多 Sheet 拓扑序幂等入库）
支持一个 Excel 一次性集中导入 6 类基础数据并全部写入数据库：
  Sheet 1: 1_组织机构（编码、名称、类型、上级编码）
  Sheet 2: 2_教学楼（楼号、楼名、所属校区/组织编码、楼层数、备注）
  Sheet 3: 3_教室（教室号、教学楼号、所属组织编码、容量、类型、固定/流动、环境标签）
  Sheet 4: 4_班级（班号、班名、所属组织编码、年级、人数）
  Sheet 5: 5_教师（工号、姓名、所属组织编码）
  Sheet 6: 6_学生（学号、姓名、所属组织编码、班号）
"""
from io import BytesIO
from typing import Dict, List

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models import Building, Classroom, OrgNode, StudentCohort, SysUser
from app.org.service import ensure_node_type_dictionary


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def build_master_data_template() -> bytes:
    """生成标准 6-Sheet《基础数据集中导入模板.xlsx》。"""
    wb = Workbook()
    sheets = [
        (
            "1_组织机构",
            ["组织编码", "组织名称", "节点类型(SCHOOL/CAMPUS/COLLEGE/DEPT/MAJOR)", "上级组织编码(根节点留空)"],
            [
                ["UNIV_DEMO", "示范大学", "SCHOOL", ""],
                ["COL_INFO", "信息工程学院", "COLLEGE", "UNIV_DEMO"],
                ["DEPT_CS", "计算机系", "DEPT", "COL_INFO"],
                ["MAJ_SE", "软件工程专业", "MAJOR", "DEPT_CS"],
            ],
        ),
        (
            "2_教学楼",
            ["教学楼编码", "教学楼名称", "所属校区/组织编码", "楼层数", "备注"],
            [
                ["BLDG_01", "第一教学楼", "UNIV_DEMO", 6, "公共多媒体教学楼"],
                ["BLDG_LAB", "信息实验楼", "COL_INFO", 5, "专业机房与实验室"],
            ],
        ),
        (
            "3_教室",
            ["教室编号", "教学楼编码", "所属组织编码", "座位数", "教室类型(NORMAL/COMPUTER_LAB)", "固定或流动(FIXED/FLOATING)", "软件标签(逗号分隔)"],
            [
                ["A-101", "BLDG_01", "UNIV_DEMO", 120, "NORMAL", "FLOATING", "多媒体"],
                ["LAB-401", "BLDG_LAB", "DEPT_CS", 60, "COMPUTER_LAB", "FLOATING", "Linux,Python"],
            ],
        ),
        (
            "4_班级",
            ["班号", "班级名称", "所属组织编码", "年级", "人数"],
            [
                ["SE2601", "软工2601班", "MAJ_SE", 2026, 45],
            ],
        ),
        (
            "5_教师",
            ["工号", "姓名", "所属组织编码"],
            [
                ["T2001", "张明远", "DEPT_CS"],
            ],
        ),
        (
            "6_学生",
            ["学号", "姓名", "所属组织编码", "所属班号"],
            [
                ["S2026001", "陈同学", "MAJ_SE", "SE2601"],
            ],
        ),
    ]

    fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    for idx, (title, headers, sample_rows) in enumerate(sheets):
        ws = wb.active if idx == 0 else wb.create_sheet(title=title)
        ws.title = title
        ws.append(headers)
        for row in sample_rows:
            ws.append(row)
        for col_i in range(1, len(headers) + 1):
            c = ws.cell(row=1, column=col_i)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = fill
            c.alignment = Alignment(horizontal="center")
            ws.column_dimensions[c.column_letter].width = 22

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_master_data_workbook(db: Session, excel_bytes: bytes) -> Dict[str, object]:
    """按外键依赖拓扑顺序集中幂等入库全部 6 类基础数据。"""
    ensure_node_type_dictionary(db)
    wb = load_workbook(BytesIO(excel_bytes), data_only=True)
    summary: Dict[str, Dict[str, object]] = {}

    def _init_stat(name: str) -> Dict[str, object]:
        st = {"inserted": 0, "updated": 0, "errors": []}
        summary[name] = st
        return st

    # 1. 组织机构
    if "1_组织机构" in wb.sheetnames:
        st = _init_stat("1_组织机构")
        ws = wb["1_组织机构"]
        org_by_code = {o.node_code: o for o in db.query(OrgNode).all()}
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            code, name, ntype, pcode = _s(row[0]), _s(row[1]), (_s(row[2]) or "DEPT").upper(), _s(row[3])
            if not code or not name:
                continue
            parent = org_by_code.get(pcode) if pcode else None
            if pcode and parent is None:
                st["errors"].append(f"第{r_idx}行：上级组织编码 {pcode} 不存在")
                continue
            existing = org_by_code.get(code)
            if existing:
                existing.node_name = name
                existing.node_type_code = ntype
                st["updated"] += 1
            else:
                node = OrgNode(
                    parent_id=parent.id if parent else None,
                    node_code=code,
                    node_name=name,
                    node_type_code=ntype,
                    tree_path="/pending/",
                    depth=(parent.depth + 1) if parent else 1,
                    is_scheduling_unit=(ntype in ("DEPT", "MAJOR", "COLLEGE")),
                    has_student_cohort=(ntype in ("DEPT", "MAJOR", "ACADEMY")),
                    has_room_pool=(ntype in ("SCHOOL", "CAMPUS", "COLLEGE", "DEPT", "TRAINING_CENTER")),
                    is_campus_boundary=(ntype in ("SCHOOL", "CAMPUS")),
                )
                db.add(node)
                db.flush()
                node.tree_path = f"{parent.tree_path}{node.id}/" if parent else f"/{node.id}/"
                org_by_code[code] = node
                st["inserted"] += 1
        db.flush()

    org_by_code = {o.node_code: o for o in db.query(OrgNode).all()}

    # 2. 教学楼
    if "2_教学楼" in wb.sheetnames:
        st = _init_stat("2_教学楼")
        ws = wb["2_教学楼"]
        bldg_by_code = {b.building_code: b for b in db.query(Building).all()}
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            code, name, ocode = _s(row[0]), _s(row[1]), _s(row[2])
            if not code or not name:
                continue
            org = org_by_code.get(ocode)
            if org is None:
                st["errors"].append(f"第{r_idx}行：所属组织编码 {ocode} 不存在")
                continue
            floors = int(float(_s(row[3]) or "5"))
            remark = _s(row[4]) or None
            existing = bldg_by_code.get(code)
            if existing:
                existing.building_name = name
                existing.campus_org_id = org.id
                existing.floors = floors
                existing.remark = remark
                st["updated"] += 1
            else:
                b = Building(building_code=code, building_name=name, campus_org_id=org.id, floors=floors, remark=remark)
                db.add(b)
                db.flush()
                bldg_by_code[code] = b
                st["inserted"] += 1
        db.flush()

    bldg_by_code = {b.building_code: b for b in db.query(Building).all()}

    # 3. 教室
    if "3_教室" in wb.sheetnames:
        st = _init_stat("3_教室")
        ws = wb["3_教室"]
        room_by_code = {r.room_code: r for r in db.query(Classroom).all()}
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            rcode, bcode, ocode = _s(row[0]), _s(row[1]), _s(row[2])
            if not rcode:
                continue
            org = org_by_code.get(ocode)
            if org is None:
                st["errors"].append(f"第{r_idx}行：所属组织编码 {ocode} 不存在")
                continue
            bldg = bldg_by_code.get(bcode)
            b_name = bldg.building_name if bldg else (bcode or "默认教学楼")
            cap = int(float(_s(row[3]) or "60"))
            rtype = (_s(row[4]) or "NORMAL").upper()
            umode = (_s(row[5]) or "FLOATING").upper()
            if umode not in ("FIXED", "FLOATING"):
                umode = "FLOATING"
            tags = [x.strip() for x in _s(row[6]).replace("，", ",").split(",") if x.strip()]
            existing = room_by_code.get(rcode)
            if existing:
                existing.building = b_name
                existing.building_id = bldg.id if bldg else None
                existing.owner_org_id = org.id
                existing.capacity = cap
                existing.room_type = rtype
                existing.usage_mode = umode
                existing.env_tags = tags
                st["updated"] += 1
            else:
                rm = Classroom(
                    room_code=rcode,
                    building=b_name,
                    building_id=bldg.id if bldg else None,
                    owner_org_id=org.id,
                    capacity=cap,
                    room_type=rtype,
                    usage_mode=umode,
                    env_tags=tags,
                )
                db.add(rm)
                db.flush()
                room_by_code[rcode] = rm
                st["inserted"] += 1
        db.flush()

    # 4. 班级
    if "4_班级" in wb.sheetnames:
        st = _init_stat("4_班级")
        ws = wb["4_班级"]
        cohort_by_code = {c.cohort_code: c for c in db.query(StudentCohort).all()}
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            ccode, cname, ocode = _s(row[0]), _s(row[1]), _s(row[2])
            if not ccode or not cname:
                continue
            org = org_by_code.get(ocode)
            if org is None:
                st["errors"].append(f"第{r_idx}行：所属组织编码 {ocode} 不存在")
                continue
            grade = int(float(_s(row[3]) or "2026"))
            cnt = int(float(_s(row[4]) or "40"))
            existing = cohort_by_code.get(ccode)
            if existing:
                existing.cohort_name = cname
                existing.org_node_id = org.id
                existing.grade_year = grade
                existing.student_count = cnt
                st["updated"] += 1
            else:
                c = StudentCohort(cohort_code=ccode, cohort_name=cname, org_node_id=org.id, grade_year=grade, student_count=cnt)
                db.add(c)
                db.flush()
                cohort_by_code[ccode] = c
                st["inserted"] += 1
        db.flush()

    cohort_by_code = {c.cohort_code: c for c in db.query(StudentCohort).all()}
    default_pw = hash_password("123456")

    # 5. 教师
    if "5_教师" in wb.sheetnames:
        st = _init_stat("5_教师")
        ws = wb["5_教师"]
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            uname, rname, ocode = _s(row[0]), _s(row[1]), _s(row[2])
            if not uname or not rname:
                continue
            org = org_by_code.get(ocode)
            if org is None:
                st["errors"].append(f"第{r_idx}行：所属组织编码 {ocode} 不存在")
                continue
            existing = db.query(SysUser).filter(SysUser.username == uname).first()
            if existing:
                existing.real_name = rname
                existing.org_node_id = org.id
                existing.is_active = True
                st["updated"] += 1
            else:
                db.add(SysUser(username=uname, real_name=rname, org_node_id=org.id, role_code="TEACHER", password_hash=default_pw))
                st["inserted"] += 1
        db.flush()

    # 6. 学生
    if "6_学生" in wb.sheetnames:
        st = _init_stat("6_学生")
        ws = wb["6_学生"]
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            uname, rname, ocode, ccode = _s(row[0]), _s(row[1]), _s(row[2]), _s(row[3])
            if not uname or not rname:
                continue
            org = org_by_code.get(ocode)
            cohort = cohort_by_code.get(ccode)
            if org is None:
                st["errors"].append(f"第{r_idx}行：所属组织编码 {ocode} 不存在")
                continue
            if cohort is None:
                st["errors"].append(f"第{r_idx}行：所属班号 {ccode} 不存在")
                continue
            existing = db.query(SysUser).filter(SysUser.username == uname).first()
            if existing:
                existing.real_name = rname
                existing.org_node_id = org.id
                existing.cohort_id = cohort.id
                existing.is_active = True
                st["updated"] += 1
            else:
                db.add(
                    SysUser(
                        username=uname,
                        real_name=rname,
                        org_node_id=org.id,
                        cohort_id=cohort.id,
                        role_code="STUDENT",
                        password_hash=default_pw,
                    )
                )
                st["inserted"] += 1

    db.commit()
    total_inserted = sum(int(v["inserted"]) for v in summary.values())
    total_updated = sum(int(v["updated"]) for v in summary.values())
    total_errors = sum(len(v["errors"]) for v in summary.values())
    return {
        "status": "SUCCESS" if total_errors == 0 else "PARTIAL_SUCCESS",
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "total_errors": total_errors,
        "sheets": summary,
    }
