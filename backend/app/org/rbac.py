"""T2.1 RBAC 四类角色与基于 tree_path 的多级数据隔离校验。"""
from typing import Tuple
from app.models import OrgNode, SysUser


def check_org_scope_permission(
    user: SysUser,
    user_org: OrgNode,
    target_org: OrgNode,
    action: str = "SCHEDULE",
) -> Tuple[bool, str]:
    """
    多级数据隔离校验：
    - SUPER_ADMIN：全校/全树所有节点均具备读写权限。
    - DEPT_SCHEDULER：仅限操作所属节点及其子树（基于 tree_path 前缀匹配）。
    - LAB_ADMIN：仅限管理所属节点及子树的机房规则（action='LAB_RULE'）。
    - TEACHER：仅限个人禁排与课表查看（action='TEACHER_SELF'）。
    """
    if user.role_code == "SUPER_ADMIN":
        return True, "校级管理员具备全树管理权限"

    in_subtree = target_org.tree_path.startswith(user_org.tree_path)

    if user.role_code == "DEPT_SCHEDULER":
        if action in ("SCHEDULE", "ORG_CONFIG", "TIMESLOT") and in_subtree:
            return True, "院系排课员在本组织及子树范围内具备权限"
        return False, "越权操作：院系排课员无权跨组织修改兄弟院系或上级节点"

    if user.role_code == "LAB_ADMIN":
        if action == "LAB_RULE" and in_subtree:
            return True, "机房管理员在本组织及子树范围内具备场地规则权限"
        return False, "越权操作：机房管理员仅可维护本组织管辖场地规则"

    if user.role_code == "TEACHER":
        if action == "TEACHER_SELF":
            return True, "任课教师具备个人禁排填报与课表查询权限"
        return False, "越权操作：任课教师无权执行排课或组织管理操作"

    return False, f"未知角色 {user.role_code}"
