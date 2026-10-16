from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .models import Doctor
from .routers import appointments, doctors, patients

VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Production containers run Alembic before Uvicorn; create_all keeps tests self-contained.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version=VERSION,
    description="Appointment booking for a multi-specialty clinic: doctors, patients and their appointments.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["ops"])

app.include_router(doctors.router)
app.include_router(patients.router)
app.include_router(appointments.router)


@app.get("/", tags=["ops"])
def root():
    return {"service": settings.app_name, "version": VERSION, "docs": "/docs"}


@app.get("/health", tags=["ops"])
def health():
    return {"status": "UP"}


@app.get("/ready", tags=["ops"])
def ready(db: Session = Depends(get_db)):
    db.execute(select(func.count(Doctor.id)))
    return {"status": "READY"}
