"""
多级排课管理员（校级/院级/系级/专业级）、机房管理员、教师与学生 RBAC 权限校验中心
"""
from typing import Dict, List, Tuple
from app.models import OrgNode, SysUser

ROLE_LABELS: Dict[str, str] = {
    "SUPER_ADMIN": "校级排课管理员",
    "COLLEGE_SCHEDULER": "院级排课管理员",
    "DEPT_SCHEDULER": "系级排课管理员",
    "MAJOR_SCHEDULER": "专业级排课管理员",
    "LAB_ADMIN": "机房/实验室管理员",
    "TEACHER": "任课教师",
    "STUDENT": "在校学生",
}

SCHEDULER_ROLES = {"SUPER_ADMIN", "COLLEGE_SCHEDULER", "DEPT_SCHEDULER", "MAJOR_SCHEDULER"}


def get_role_permissions(role_code: str) -> List[str]:
    if role_code == "SUPER_ADMIN":
        return ["DASHBOARD", "ORG_TREE", "EXCEL_SOLVER", "WORKBENCH", "ROOMS", "ARCHIVE_EXPORT", "HEALTH_CHECK", "USER_MANAGE"]
    if role_code in ("COLLEGE_SCHEDULER", "DEPT_SCHEDULER", "MAJOR_SCHEDULER"):
        return ["DASHBOARD", "ORG_TREE_VIEW", "EXCEL_SOLVER", "WORKBENCH", "ROOMS", "ARCHIVE_EXPORT", "HEALTH_CHECK"]
    if role_code == "LAB_ADMIN":
        return ["DASHBOARD", "ROOMS", "WORKBENCH_READ"]
    if role_code == "TEACHER":
        return ["MY_TEACHER_SCHEDULE", "TEACHER_UNAVAILABLE", "CHANGE_REQUEST"]
    if role_code == "STUDENT":
        return ["MY_STUDENT_SCHEDULE"]
    return []


def check_org_scope_permission(
    user: SysUser,
    user_org: OrgNode,
    target_org: OrgNode,
    action: str = "SCHEDULE",
) -> Tuple[bool, str]:
    if user.role_code == "SUPER_ADMIN":
        return True, "校级排课管理员具备全校所有组织节点的最高管理权限"

    in_subtree = target_org.tree_path.startswith(user_org.tree_path)

    if user.role_code in ("COLLEGE_SCHEDULER", "DEPT_SCHEDULER", "MAJOR_SCHEDULER"):
        if action in ("SCHEDULE", "ORG_CONFIG", "TIMESLOT", "EXPORT") and in_subtree:
            return True, f"{ROLE_LABELS[user.role_code]}在所属节点【{user_org.node_name}】及子树内具备操作权限"
        return False, f"越权操作：{ROLE_LABELS[user.role_code]}仅可管理【{user_org.node_name}】及下属节点，无权操作【{target_org.node_name}】"

    if user.role_code == "LAB_ADMIN":
        if action == "LAB_RULE" and in_subtree:
            return True, "机房管理员在所属组织及子树内具备场地管控权限"
        return False, "越权操作：机房管理员仅可维护本组织管辖场地"

    if user.role_code == "TEACHER":
        if action == "TEACHER_SELF":
            return True, "任课教师具备个人课表查询与禁排填报权限"
        return False, "越权操作：任课教师不可进入管理员排课后台"

    if user.role_code == "STUDENT":
        if action == "STUDENT_SELF":
            return True, "学生具备所属班级课表查询权限"
        return False, "越权操作：学生仅可查看本班课表"

    return False, f"未知角色 {user.role_code}"
