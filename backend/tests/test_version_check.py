"""版本检测与手动确认升级提醒单测（远端模拟新版本固定使用 v99.0.0，避免随 APP_VERSION 递增冲突）。"""
from fastapi.testclient import TestClient

from app.api import system as sys_api
from app.main import app


def test_semver_comparison():
    assert sys_api.is_newer_version("v1.0.3", "v1.1.0") is True
    assert sys_api.is_newer_version("v1.0.3", "v1.0.3") is False
    assert sys_api.is_newer_version("v1.2.0", "v1.1.9") is False


def test_version_endpoint_detects_update_and_handles_offline(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr(
        sys_api,
        "fetch_latest_github_release",
        lambda repo, timeout=5.0: {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/qingmi2002/school/releases/tag/v99.0.0",
            "body": "新增跨校区通勤优化与一键归档增强",
        },
    )
    r1 = client.get("/api/v1/system/version?force=true")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["has_update"] is True
    assert body1["latest_version"] == "v99.0.0"
    assert "deploy.sh --upgrade" in body1["linux_upgrade_cmd"]

    def _offline(*args, **kwargs):
        raise ConnectionError("offline campus network")

    monkeypatch.setattr(sys_api, "fetch_latest_github_release", _offline)
    r2 = client.get("/api/v1/system/version?force=true")
    assert r2.status_code == 200
    assert r2.json()["check_status"] == "OFFLINE"
    assert r2.json()["has_update"] is False
