from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.constraints import router as constraints_router
from app.api.curriculum import router as curriculum_router
from app.api.exporter import router as exporter_router
from app.api.importer import router as importer_router
from app.api.locks import router as locks_router
from app.api.org import router as org_router
from app.api.resources import router as resources_router
from app.api.solver import router as solver_router
from app.api.system import router as system_router
from app.api.validator import router as validator_router
from app.api.week_plan import router as week_plan_router
from app.api.workbench import router as workbench_router
from app.auth.security import decode_access_token
from app.core.config import settings
from app.org.rbac import SCHEDULER_ROLES

app = FastAPI(title=settings.PROJECT_NAME, version=settings.APP_VERSION)

_raw_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_is_wildcard = not _raw_origins or _raw_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _is_wildcard else _raw_origins,
    allow_credentials=not _is_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PUBLIC_WRITE_PATHS = {
    f"{settings.API_V1_PREFIX}/auth/login",
    f"{settings.API_V1_PREFIX}/auth/seed-demo",
}
_PUBLIC_GET_PATHS = {
    f"{settings.API_V1_PREFIX}/resources/site-config",
    f"{settings.API_V1_PREFIX}/system/version",
}
_ADMIN_OR_LEAD_READ_PREFIXES = (
    f"{settings.API_V1_PREFIX}/resources/students",
    f"{settings.API_V1_PREFIX}/curriculum/teacher-workload",
    f"{settings.API_V1_PREFIX}/export/",
)


@app.middleware("http")
async def enforce_api_auth_middleware(request: Request, call_next):
    """V1.8 全局读/写接口服务端鉴权与角色分级守卫。"""
    if settings.ENFORCE_API_AUTH and request.url.path.startswith(settings.API_V1_PREFIX):
        path = request.url.path
        method = request.method

        # 放行极少数公开读/登录接口
        if (method == "GET" and path in _PUBLIC_GET_PATHS) or (
            method == "POST" and path in _PUBLIC_WRITE_PATHS
        ):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "请先登录后再访问接口"})
        payload = decode_access_token(auth_header[7:].strip())
        if payload is None:
            return JSONResponse(status_code=401, content={"detail": "登录凭证无效或已过期，请重新登录"})

        role = str(payload.get("role", ""))

        # 1. 敏感读接口权限拦截（防止学生拉取全校学生名单与导出包）
        if method == "GET":
            if any(path.startswith(pref) for pref in _ADMIN_OR_LEAD_READ_PREFIXES):
                if role not in SCHEDULER_ROLES | {"TEACHING_LEAD"}:
                    return JSONResponse(status_code=403, content={"detail": "当前角色无权查看全校敏感统计或名单"})
            return await call_next(request)

        # 2. 写接口角色分级拦截
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            if path.startswith(f"{settings.API_V1_PREFIX}/auth/change-password"):
                pass
            elif path.startswith(f"{settings.API_V1_PREFIX}/constraints/teacher-unavailable"):
                if role not in SCHEDULER_ROLES | {"TEACHING_LEAD", "TEACHER"}:
                    return JSONResponse(status_code=403, content={"detail": "当前角色无权填报教师禁排"})
            elif path.startswith(f"{settings.API_V1_PREFIX}/workbench/change-requests") and not path.endswith("/review"):
                if role not in SCHEDULER_ROLES | {"TEACHING_LEAD", "TEACHER"}:
                    return JSONResponse(status_code=403, content={"detail": "当前角色无权发起调课申请"})
            elif path.startswith(f"{settings.API_V1_PREFIX}/curriculum"):
                if role not in SCHEDULER_ROLES | {"TEACHING_LEAD"}:
                    return JSONResponse(status_code=403, content={"detail": "仅排课管理员或教研室主任可管理课程与合班任务"})
            elif path.startswith(f"{settings.API_V1_PREFIX}/constraints/rooms") or path.startswith(f"{settings.API_V1_PREFIX}/constraints/room-rules"):
                if role not in SCHEDULER_ROLES | {"LAB_ADMIN"}:
                    return JSONResponse(status_code=403, content={"detail": "仅排课管理员或机房管理员可修改机房规则"})
            else:
                if role not in SCHEDULER_ROLES:
                    return JSONResponse(status_code=403, content={"detail": "该操作仅限排课管理员执行"})

    return await call_next(request)


app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(resources_router, prefix=settings.API_V1_PREFIX)
app.include_router(week_plan_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(org_router, prefix=settings.API_V1_PREFIX)
app.include_router(locks_router, prefix=settings.API_V1_PREFIX)
app.include_router(constraints_router, prefix=settings.API_V1_PREFIX)
app.include_router(curriculum_router, prefix=settings.API_V1_PREFIX)
app.include_router(solver_router, prefix=settings.API_V1_PREFIX)
app.include_router(importer_router, prefix=settings.API_V1_PREFIX)
app.include_router(validator_router, prefix=settings.API_V1_PREFIX)
app.include_router(workbench_router, prefix=settings.API_V1_PREFIX)
app.include_router(exporter_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "mode": "multi-level-flexible",
        "version": settings.APP_VERSION,
        "auth_enforced": settings.ENFORCE_API_AUTH,
    }
