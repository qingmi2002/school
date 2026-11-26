"""系统版本检测与手动确认升级提醒接口（绝不静默自动重启）。"""
import re
import time
from typing import Optional, Tuple

from fastapi import APIRouter, Query
import httpx
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])

_CACHE_TTL_SECONDS = 600
_version_cache: dict = {"checked_at": 0.0, "data": None}


def parse_semver(tag: str) -> Tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", tag or "")]
    return tuple(nums) if nums else (0,)


def is_newer_version(current: str, latest: str) -> bool:
    c = parse_semver(current)
    l = parse_semver(latest)
    max_len = max(len(c), len(l))
    c_pad = c + (0,) * (max_len - len(c))
    l_pad = l + (0,) * (max_len - len(l))
    return l_pad > c_pad


class VersionCheckOut(BaseModel):
    current_version: str
    latest_version: str
    has_update: bool
    check_status: str  # OK / OFFLINE / NO_RELEASE
    release_url: str
    release_notes: str
    linux_upgrade_cmd: str
    nas_upgrade_tip: str


def fetch_latest_github_release(repo: str, timeout: float = 5.0) -> Optional[dict]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "SmartSchedule-VersionChecker"}
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code == 404:
            return {"_no_release": True}
        resp.raise_for_status()
        return resp.json()


@router.get("/version", response_model=VersionCheckOut)
def check_system_version(force: bool = Query(False)):
    now = time.time()
    if not force and _version_cache["data"] is not None and (now - _version_cache["checked_at"] < _CACHE_TTL_SECONDS):
        return _version_cache["data"]

    repo = settings.GITHUB_REPO
    current = settings.APP_VERSION
    base_url = f"https://github.com/{repo}/releases"
    linux_cmd = "cd /opt/smart-schedule && git pull && sudo bash deploy.sh --upgrade"
    nas_tip = "在 NAS Docker 界面停止容器 -> 重新拉取 ghcr.io/qingmi2002/smart-schedule-backend:latest 与 web:latest -> 启动即可（自动执行数据库迁移）。"

    try:
        rel = fetch_latest_github_release(repo)
        if rel and rel.get("_no_release"):
            out = VersionCheckOut(
                current_version=current,
                latest_version=current,
                has_update=False,
                check_status="NO_RELEASE",
                release_url=base_url,
                release_notes="GitHub 仓库尚未发布正式 Release 标签，当前已是最新运行版本。",
                linux_upgrade_cmd=linux_cmd,
                nas_upgrade_tip=nas_tip,
            )
        else:
            latest = (rel or {}).get("tag_name") or current
            notes = ((rel or {}).get("body") or "包含稳定性与功能优化。").strip()[:800]
            out = VersionCheckOut(
                current_version=current,
                latest_version=latest,
                has_update=is_newer_version(current, latest),
                check_status="OK",
                release_url=(rel or {}).get("html_url") or base_url,
                release_notes=notes,
                linux_upgrade_cmd=linux_cmd,
                nas_upgrade_tip=nas_tip,
            )
    except Exception:
        out = VersionCheckOut(
            current_version=current,
            latest_version=current,
            has_update=False,
            check_status="OFFLINE",
            release_url=base_url,
            release_notes="当前服务器处于内网离线环境或无法访问 GitHub API，暂不提示在线更新。",
            linux_upgrade_cmd=linux_cmd,
            nas_upgrade_tip=nas_tip,
        )

    _version_cache["checked_at"] = now
    _version_cache["data"] = out
    return out
