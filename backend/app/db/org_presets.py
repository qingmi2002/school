"""
高校多级组织架构字典与预设库（已补充 MAJOR 专业级节点，完整覆盖 校 -> 院 -> 系 -> 专业 四级权限）。
"""

NODE_TYPE_DICTIONARY = [
    {"code": "SCHOOL", "name": "学校", "sort_order": 1, "default_flags": {"is_summary_node": True, "has_room_pool": True, "is_public_provider": True}},
    {"code": "CAMPUS", "name": "校区", "sort_order": 2, "default_flags": {"is_campus_boundary": True, "is_summary_node": True, "has_room_pool": True}},
    {"code": "FACULTY", "name": "学部", "sort_order": 3, "default_flags": {"is_summary_node": True, "has_room_pool": True}},
    {"code": "ACADEMY", "name": "书院", "sort_order": 4, "default_flags": {"has_student_cohort": True}},
    {"code": "COLLEGE", "name": "二级学院", "sort_order": 5, "default_flags": {"is_summary_node": True, "has_room_pool": True}},
    {"code": "DEPT", "name": "教学系", "sort_order": 6, "default_flags": {"is_scheduling_unit": True, "has_student_cohort": True, "has_room_pool": True}},
    {"code": "MAJOR", "name": "专业", "sort_order": 7, "default_flags": {"is_scheduling_unit": True, "has_student_cohort": True}},
    {"code": "PUBLIC_DEPT", "name": "公共教学部", "sort_order": 8, "default_flags": {"is_public_provider": True, "is_scheduling_unit": True}},
    {"code": "TRAINING_CENTER", "name": "实训中心", "sort_order": 9, "default_flags": {"has_room_pool": True}},
]

ORG_ARCHETYPE_PRESETS = {
    "single_dept_standalone": {
        "name": "单院系独立轻量化模式",
        "description": "单个学院或教学系独立启动排课，无需全校前置配置，后续可随时平滑挂载至校级根节点。",
        "nodes": [
            {"code": "CS_DEPT", "name": "计算机科学与技术系", "type": "DEPT", "parent": None, "flags": {"is_scheduling_unit": True, "has_student_cohort": True, "has_room_pool": True, "is_campus_boundary": True, "allow_custom_timeslot": True}},
        ],
    },
    "school_college_dept": {
        "name": "校—院—系—专业四级制",
        "description": "完整高校分级体制：校级统筹公共课，院级汇总，系级/专业级排课员分级自治。",
        "nodes": [
            {"code": "UNIV", "name": "示范大学", "type": "SCHOOL", "parent": None, "flags": {"is_public_provider": True, "has_room_pool": True, "is_summary_node": True, "is_campus_boundary": True}},
            {"code": "INFO_COL", "name": "信息工程学院", "type": "COLLEGE", "parent": "UNIV", "flags": {"has_room_pool": True, "is_summary_node": True}},
            {"code": "CS_DEPT", "name": "计算机系", "type": "DEPT", "parent": "INFO_COL", "flags": {"is_scheduling_unit": True, "has_student_cohort": True, "has_room_pool": True}},
            {"code": "SE_MAJOR", "name": "软件工程专业", "type": "MAJOR", "parent": "CS_DEPT", "flags": {"is_scheduling_unit": True, "has_student_cohort": True}},
            {"code": "AI_MAJOR", "name": "人工智能专业", "type": "MAJOR", "parent": "CS_DEPT", "flags": {"is_scheduling_unit": True, "has_student_cohort": True}},
        ],
    },
    "school_college_flat": {
        "name": "校—院两级扁平制",
        "description": "直接以二级学院作为独立排课单元，减少中间层级。",
        "nodes": [
            {"code": "UNIV", "name": "示范大学", "type": "SCHOOL", "parent": None, "flags": {"is_public_provider": True, "has_room_pool": True, "is_summary_node": True, "is_campus_boundary": True}},
            {"code": "AI_COL", "name": "人工智能学院", "type": "COLLEGE", "parent": "UNIV", "flags": {"is_scheduling_unit": True, "has_student_cohort": True, "has_room_pool": True}},
        ],
    },
    "school_dept_vocational": {
        "name": "校—系两级制（高职/独立学院）",
        "description": "教学系直连全校公共教室池。",
        "nodes": [
            {"code": "UNIV", "name": "示范职业技术学院", "type": "SCHOOL", "parent": None, "flags": {"is_public_provider": True, "has_room_pool": True, "is_summary_node": True, "is_campus_boundary": True}},
            {"code": "MECH_DEPT", "name": "机电工程系", "type": "DEPT", "parent": "UNIV", "flags": {"is_scheduling_unit": True, "has_student_cohort": True, "has_room_pool": True}},
        ],
    },
    "multi_campus_four_tier": {
        "name": "多校区四级制",
        "description": "校区节点自动作为物理通勤边界（is_campus_boundary=True），跨校区连排自动熔断预警。",
        "nodes": [
            {"code": "UNIV", "name": "示范大学", "type": "SCHOOL", "parent": None, "flags": {"is_public_provider": True, "is_summary_node": True}},
            {"code": "MAIN_CAMPUS", "name": "主校区", "type": "CAMPUS", "parent": "UNIV", "flags": {"is_campus_boundary": True, "has_room_pool": True, "is_summary_node": True}},
            {"code": "NEW_CAMPUS", "name": "新校区", "type": "CAMPUS", "parent": "UNIV", "flags": {"is_campus_boundary": True, "has_room_pool": True, "is_summary_node": True, "allow_custom_timeslot": True}},
            {"code": "CS_COL", "name": "计算机学院", "type": "COLLEGE", "parent": "MAIN_CAMPUS", "flags": {"is_scheduling_unit": True, "has_student_cohort": True, "has_room_pool": True}},
        ],
    },
    "academy_college_dual": {
        "name": "学部制 / 书院制",
        "description": "行政班级归书院（has_student_cohort），课程与师资归专业学院，通过横向授权协同。",
        "nodes": [
            {"code": "UNIV", "name": "示范大学", "type": "SCHOOL", "parent": None, "flags": {"is_public_provider": True, "is_summary_node": True, "is_campus_boundary": True}},
            {"code": "ZHIYUAN_ACAD", "name": "致远书院", "type": "ACADEMY", "parent": "UNIV", "flags": {"has_student_cohort": True}},
            {"code": "MATH_COL", "name": "数学学院", "type": "COLLEGE", "parent": "UNIV", "flags": {"is_scheduling_unit": True, "has_room_pool": True}},
        ],
    },
    "public_dept_and_training_center": {
        "name": "独立公共教学部 + 实训中心",
        "description": "无固定行政班，分别负责输出全校公共课与统筹全校共享实训机房。",
        "nodes": [
            {"code": "UNIV", "name": "示范大学", "type": "SCHOOL", "parent": None, "flags": {"is_summary_node": True, "is_campus_boundary": True}},
            {"code": "BASIC_PUB", "name": "基础教学部", "type": "PUBLIC_DEPT", "parent": "UNIV", "flags": {"is_public_provider": True, "is_scheduling_unit": True}},
            {"code": "LAB_CENTER", "name": "现代实训中心", "type": "TRAINING_CENTER", "parent": "UNIV", "flags": {"has_room_pool": True}},
        ],
    },
}


def resolve_campus_boundary_id(node_by_id: dict, start_node_id: int) -> int | None:
    current = node_by_id.get(start_node_id)
    visited = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        if current.is_campus_boundary:
            return current.id
        current = node_by_id.get(current.parent_id)
    return None
