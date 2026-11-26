"""T4.3 生产验收压测：多系部并发求解试算稳定性校验。"""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app


def _solve_one_dept(dept_idx: int) -> int:
    client = TestClient(app)
    slots = [{"id": i, "day_of_week": ((i - 1) // 5) + 1, "period_index": ((i - 1) % 5) + 1} for i in range(1, 26)]
    rooms = [{"id": r, "room_code": f"D{dept_idx}-R{r}", "owner_org_id": dept_idx, "capacity": 60} for r in range(1, 6)]
    tasks = [
        {
            "id": t,
            "org_node_id": dept_idx,
            "course_code": f"D{dept_idx}C{t:02d}",
            "course_name": f"课程{t}",
            "teacher_id": (t % 8) + 1,
            "cohort_ids": [(t % 5) + 1],
            "weekly_sessions": 1,
            "total_students": 40,
        }
        for t in range(1, 26)
    ]
    resp = client.post(
        "/api/v1/solver/dry-run",
        json={"timeslots": slots, "rooms": rooms, "tasks": tasks, "time_limit_seconds": 5.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert len(body["assignments"]) == 25
    return dept_idx


def test_concurrent_multi_department_solving_stability():
    """模拟 5 个系部同时并发点击智能排课，验证全部稳定返回零冲突解。"""
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(_solve_one_dept, [1, 2, 3, 4, 5]))
    assert sorted(results) == [1, 2, 3, 4, 5]
