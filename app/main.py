from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
def root():
    return {"service": "loadcargo-backend", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}
