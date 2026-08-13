from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    briefing,
    driving,
    onboarding,
    pipeline,
    qna,
    registration,
    retrospective,
    risk,
)

app = FastAPI(
    title="만차 백엔드 API",
    description="만차 백엔드 서비스",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(onboarding.router, prefix="/api")
app.include_router(registration.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(briefing.router, prefix="/api")
app.include_router(qna.router, prefix="/api")
app.include_router(driving.router, prefix="/api")
app.include_router(retrospective.router, prefix="/api")

@app.get("/")
def root():
    return {"service": "loadcargo-backend", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}
