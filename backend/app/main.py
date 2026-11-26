from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.importer import router as importer_router
from app.api.org import router as org_router
from app.api.solver import router as solver_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.5.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(org_router, prefix=settings.API_V1_PREFIX)
app.include_router(solver_router, prefix=settings.API_V1_PREFIX)
app.include_router(importer_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "mode": "multi-level-flexible",
        "version": "0.5.0",
    }
