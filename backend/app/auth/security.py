"""零外部 C 编译依赖的标准 HS256 JWT 与 PBKDF2 密码哈希安全模块。"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import SysUser

bearer_scheme = HTTPBearer(auto_error=False)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def hash_password(raw_password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"pbkdf2${salt}${dk}"


def verify_password(raw_password: str, stored_hash: str) -> bool:
    if not stored_hash.startswith("pbkdf2$"):
        return hmac.compare_digest(raw_password, stored_hash)
    parts = stored_hash.split("$")
    if len(parts) != 3:
        return False
    _, salt, expected = parts
    actual = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return hmac.compare_digest(actual, expected)


def create_access_token(user_id: int, username: str, role_code: str, org_node_id: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    exp = int((datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)).timestamp())
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role_code,
        "org_node_id": org_node_id,
        "exp": exp,
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(settings.JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h_b64, p_b64, s_b64 = parts
        signing_input = f"{h_b64}.{p_b64}".encode("ascii")
        expected_sig = hmac.new(settings.JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected_sig), s_b64):
            return None
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except Exception:
        return None


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> SysUser:
    if creds is None:
        raise HTTPException(status_code=401, detail="请先登录后再访问")
    payload = decode_access_token(creds.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="登录凭证无效或已过期，请重新登录")
    user = db.query(SysUser).filter(SysUser.id == int(payload["sub"]), SysUser.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被停用")
    return user
