"""
V1.4 周次位掩码（Week Bitmask）核心引擎
- 第 w 周对应二进制位 (1 << (w - 1))，支持 1..30 周任意组合（全周/单周/双周/半学期/跳过整周实训的断续周）。
- 冲突判定为 O(1) 按位与：(mask_a & mask_b) != 0。
"""
from typing import Iterable, List


def build_week_mask(start_week: int = 1, end_week: int = 18, week_type: int = 0) -> int:
    """根据起止周与单双周(0=全周, 1=单周, 2=双周)生成位掩码。"""
    mask = 0
    for w in range(max(1, start_week), min(30, end_week) + 1):
        if week_type == 1 and w % 2 == 0:
            continue
        if week_type == 2 and w % 2 == 1:
            continue
        mask |= 1 << (w - 1)
    return mask


def weeks_to_mask(weeks: Iterable[int]) -> int:
    mask = 0
    for w in weeks:
        if 1 <= w <= 30:
            mask |= 1 << (w - 1)
    return mask


def mask_to_weeks(mask: int, max_weeks: int = 30) -> List[int]:
    return [w for w in range(1, max_weeks + 1) if (mask & (1 << (w - 1))) != 0]


def masks_overlap(mask_a: int, mask_b: int) -> bool:
    """O(1) 判断两个周次掩码是否存在任意重叠周。"""
    return (mask_a & mask_b) != 0


def subtract_blocked_weeks(raw_mask: int, blocked_mask: int) -> int:
    """从课程原始周次中剔除班级整周实训/实习/考试/停课周。"""
    return raw_mask & (~blocked_mask)


def mask_to_label(mask: int) -> str:
    """将位掩码格式化为紧凑可读中文周次标签，如 '1-9,12-16周' 或 '1-17周(单)'。"""
    weeks = mask_to_weeks(mask)
    if not weeks:
        return "无有效周"

    # 检查是否为连续单周或连续双周
    if len(weeks) >= 2:
        all_odd = all(w % 2 == 1 for w in weeks)
        all_even = all(w % 2 == 0 for w in weeks)
        if all_odd and weeks == list(range(weeks[0], weeks[-1] + 1, 2)):
            return f"{weeks[0]}-{weeks[-1]}周(单)"
        if all_even and weeks == list(range(weeks[0], weeks[-1] + 1, 2)):
            return f"{weeks[0]}-{weeks[-1]}周(双)"

    # 合并连续区间
    ranges: List[str] = []
    start = prev = weeks[0]
    for w in weeks[1:]:
        if w == prev + 1:
            prev = w
        else:
            ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = w
    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(ranges) + "周"


def fit_week_mask_to_hours(
    start_week: int,
    end_week: int,
    week_type: int,
    blocked_mask: int,
    total_hours: int | None,
    weekly_sessions: int,
    hours_per_session: int = 2,
) -> tuple[int, int, int]:
    """
    V1.6 学期总课时与班级周历自动耦合：
    - 从 [start_week, end_week] 剔除实训/考试/假期等 blocked_mask 周次；
    - 若指定了 total_hours（如 32 学时），按每次课 hours_per_session（默认 2 学时）自动截取凑满总课时所需的有效周次；
    - 返回 (effective_mask, effective_weeks_count, planned_actual_hours)。
    """
    raw_mask = build_week_mask(start_week, end_week, week_type)
    avail_weeks = mask_to_weeks(subtract_blocked_weeks(raw_mask, blocked_mask))
    per_week_hours = max(1, int(weekly_sessions or 1)) * max(1, hours_per_session)

    if total_hours and total_hours > 0:
        needed_weeks = (total_hours + per_week_hours - 1) // per_week_hours
        chosen = avail_weeks[:needed_weeks]
    else:
        chosen = avail_weeks

    eff_mask = weeks_to_mask(chosen)
    return eff_mask, len(chosen), len(chosen) * per_week_hours
