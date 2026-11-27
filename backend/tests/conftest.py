"""全局 pytest 配置：默认关闭 ENFORCE_API_AUTH 以兼容历史无 Token 单测；安全测试模块显式开启校验。"""
import os

os.environ["ENFORCE_API_AUTH"] = "false"

import pytest
from app.core.config import settings


@pytest.fixture(autouse=True)
def _default_test_auth_mode():
    prev = settings.ENFORCE_API_AUTH
    settings.ENFORCE_API_AUTH = False
    yield
    settings.ENFORCE_API_AUTH = prev
