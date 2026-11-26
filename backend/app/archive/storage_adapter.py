"""
T4.1 Storage Adapter 云盘独立文件夹自动归档模块（R4 风险双通道兜底）
- 目录隔离：/SmartSchedule_Archive/{semester}/{dept}/{version}_{timestamp}/
- 5 类产物自动留存：原始任务书、约束快照 JSON、多维度总课表、教务回填模板、PDF 自检报告
- 高可靠机制：先写入本地安全暂存目录 -> 推送至 NAS / WebDAV -> 失败自动写入审计表供 Celery 异步重试
"""
from abc import ABC, abstractmethod
from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Dict, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.exporter import (
    export_edu_backfill_excel,
    export_health_pdf,
    export_multi_view_excel,
    export_raw_tasks_excel,
)
from app.models import (
    OrgNode,
    RoomCourseRule,
    ScheduleChangeAudit,
    SchedulePlan,
    Semester,
    TeacherUnavailable,
)


class StorageBackend(ABC):
    @abstractmethod
    def upload_directory(self, staging_dir: Path, relative_folder: str) -> str:
        """将暂存目录下的 5 类归档产物同步到目标存储并返回最终路径。"""


class LocalNASAdapter(StorageBackend):
    """本地挂载目录 / 群晖 / 飞牛 OS NAS 共享路径适配器"""

    def __init__(self, root_dir: Optional[str] = None):
        self.root = Path(root_dir or settings.ARCHIVE_LOCAL_ROOT)

    def upload_directory(self, staging_dir: Path, relative_folder: str) -> str:
        target = self.root / relative_folder
        target.mkdir(parents=True, exist_ok=True)
        for f in staging_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, target / f.name)
        return str(target)


class WebDAVAdapter(StorageBackend):
    """标准 WebDAV（Nextcloud / Alist / NAS WebDAV）双通道适配器"""

    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None

    def upload_directory(self, staging_dir: Path, relative_folder: str) -> str:
        parts = [p for p in relative_folder.strip("/").split("/") if p]
        with httpx.Client(auth=self.auth, timeout=15.0) as client:
            acc = ""
            for p in parts:
                acc = f"{acc}/{p}"
                resp = client.request("MKCOL", f"{self.base_url}{acc}")
                if resp.status_code not in (200, 201, 204, 301, 405):
                    raise RuntimeError(f"WebDAV MKCOL 失败 ({resp.status_code}): {acc}")
            for f in staging_dir.iterdir():
                if f.is_file():
                    put_url = f"{self.base_url}{acc}/{f.name}"
                    r = client.put(put_url, content=f.read_bytes())
                    if r.status_code not in (200, 201, 204):
                        raise RuntimeError(f"WebDAV PUT 失败 ({r.status_code}): {put_url}")
        return f"{self.base_url}{acc}"


class CloudArchiveManager:
    """排课方案云盘独立文件夹自动归档管理器（本地安全暂存 + 双通道兜底）"""

    def __init__(
        self,
        primary_backend: Optional[StorageBackend] = None,
        fallback_backend: Optional[StorageBackend] = None,
        staging_root: Optional[str] = None,
    ):
        self.primary = primary_backend or LocalNASAdapter()
        self.fallback = fallback_backend
        self.staging_root = Path(staging_root or settings.ARCHIVE_STAGING_DIR)

    def _build_constraints_snapshot(self, db: Session, semester_id: int) -> dict:
        unavails = db.query(TeacherUnavailable).filter(TeacherUnavailable.semester_id == semester_id).all()
        rules = db.query(RoomCourseRule).all()
        return {
            "semester_id": semester_id,
            "captured_at": datetime.now().isoformat(),
            "teacher_unavailable": [
                {
                    "teacher_id": u.teacher_id,
                    "timeslot_id": u.timeslot_id,
                    "level": u.constraint_level,
                    "reason": u.reason,
                }
                for u in unavails
            ],
            "room_course_rules": [
                {
                    "classroom_id": r.classroom_id,
                    "course_code": r.course_code,
                    "course_category": r.course_category,
                    "rule_type": r.rule_type,
                }
                for r in rules
            ],
        }

    def archive_plan(
        self,
        db: Session,
        plan_id: int,
        operator_id: int,
        vendor: str = "ZHENGFANG",
    ) -> Dict[str, object]:
        plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
        if plan is None:
            raise ValueError(f"排课方案 id={plan_id} 不存在")

        sem = db.query(Semester).filter(Semester.id == plan.semester_id).first()
        org = db.query(OrgNode).filter(OrgNode.id == plan.org_node_id).first()

        sem_code = (sem.code if sem else f"sem_{plan.semester_id}").replace("/", "_")
        dept_name = (org.node_name if org else f"org_{plan.org_node_id}").replace("/", "_").strip()
        ts_suffix = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        relative_folder = f"{sem_code}/{dept_name}/{plan.version_tag}_{ts_suffix}"

        # 1. 先写入本地安全暂存目录（确保 5 类产物零丢失）
        staging_dir = self.staging_root / relative_folder
        staging_dir.mkdir(parents=True, exist_ok=True)

        files_written = {
            "01_原始输入_教学任务书.xlsx": export_raw_tasks_excel(db, plan_id),
            "02_约束快照_教师禁排与机房规则.json": json.dumps(
                self._build_constraints_snapshot(db, plan.semester_id),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            "03_多维度总课表(班级+教师+机房).xlsx": export_multi_view_excel(db, plan_id),
            "04_教务系统回填标准模板.xlsx": export_edu_backfill_excel(db, plan_id, vendor=vendor),
            "05_排课质量与冲突自检报告.pdf": export_health_pdf(db, plan_id),
        }
        for fname, content in files_written.items():
            (staging_dir / fname).write_bytes(content)

        # 2. 双通道投递（主通道失败自动切备用通道，均失败则记录 FAILED 审计单待 Celery 重试）
        final_path = ""
        sync_status = "SYNCED"
        err_msg = ""
        try:
            final_path = self.primary.upload_directory(staging_dir, relative_folder)
        except Exception as primary_err:
            if self.fallback is not None:
                try:
                    final_path = self.fallback.upload_directory(staging_dir, relative_folder)
                except Exception as fb_err:
                    sync_status = "FAILED"
                    err_msg = f"主通道失败({primary_err})；备用通道失败({fb_err})"
            else:
                sync_status = "FAILED"
                err_msg = f"云盘归档通道异常({primary_err})，产物已安全暂存本地待异步重试"

        if sync_status == "SYNCED":
            plan.cloud_archive_path = final_path

        audit = ScheduleChangeAudit(
            plan_id=plan.id,
            operator_id=operator_id,
            audit_type="ARCHIVE_SYNC",
            status=sync_status,
            payload={
                "relative_folder": relative_folder,
                "staging_dir": str(staging_dir),
                "target_path": final_path,
                "files": list(files_written.keys()),
                "vendor": vendor,
            },
            retry_count=0,
            remark=err_msg or "5 类归档产物同步成功",
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)

        return {
            "audit_id": audit.id,
            "status": sync_status,
            "archive_path": final_path,
            "staging_dir": str(staging_dir),
            "files": list(files_written.keys()),
            "remark": audit.remark,
        }
