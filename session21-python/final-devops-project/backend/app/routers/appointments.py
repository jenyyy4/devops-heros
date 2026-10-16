from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..config import settings
from ..db import get_db
from ..metrics import APPOINTMENT_STATUS_CHANGES, APPOINTMENTS_BOOKED, BOOKING_CONFLICTS
from ..models import Appointment, Doctor, Patient
from ..schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate, DoctorLoad, StatsOut, Status
from .doctors import get_doctor_or_404
from .patients import get_patient_or_404

router = APIRouter(prefix="/api/appointments", tags=["appointments"])

# Allowed status changes. Anything else (e.g. COMPLETED -> SCHEDULED) is rejected with 409.
TRANSITIONS: dict[str, set[str]] = {
    "SCHEDULED": {"CHECKED_IN", "CANCELLED", "NO_SHOW"},
    "CHECKED_IN": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "NO_SHOW": set(),
}
# Appointments in these states no longer block the doctor's calendar.
FREE_STATUSES = ("CANCELLED", "NO_SHOW")
MAX_DURATION = timedelta(minutes=240)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _with_relations():
    return select(Appointment).options(joinedload(Appointment.patient), joinedload(Appointment.doctor))


def get_appointment_or_404(db: Session, appointment_id: int) -> Appointment:
    appointment = db.scalars(_with_relations().where(Appointment.id == appointment_id)).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


def ensure_within_opening_hours(start: datetime, duration_minutes: int) -> None:
    end = start + timedelta(minutes=duration_minutes)
    opens = start.replace(hour=settings.opening_hour, minute=0, second=0, microsecond=0)
    closes = start.replace(hour=settings.closing_hour, minute=0, second=0, microsecond=0)
    if start < opens or end > closes:
        raise HTTPException(
            status_code=422,
            detail=f"Appointments must be between {settings.opening_hour:02d}:00 and {settings.closing_hour:02d}:00",
        )


def ensure_doctor_is_free(db: Session, doctor_id: int, start: datetime, duration_minutes: int, ignore_id: int | None = None) -> None:
    end = start + timedelta(minutes=duration_minutes)
    candidates = db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status.not_in(FREE_STATUSES),
            Appointment.scheduled_at < end,
            Appointment.scheduled_at > start - MAX_DURATION,
        )
    )
    for other in candidates:
        other_end = other.scheduled_at + timedelta(minutes=other.duration_minutes)
        if other.id != ignore_id and other_end > start:
            BOOKING_CONFLICTS.inc()
            raise HTTPException(
                status_code=409,
                detail=f"Doctor already has appointment #{other.id} at {other.scheduled_at:%H:%M}",
            )


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    day: date | None = Query(default=None, alias="date"),
    status_filter: Status | None = Query(default=None, alias="status"),
    doctor_id: int | None = None,
    patient_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = _with_relations().order_by(Appointment.scheduled_at)
    if day:
        start, end = _day_bounds(day)
        query = query.where(Appointment.scheduled_at >= start, Appointment.scheduled_at < end)
    if status_filter:
        query = query.where(Appointment.status == status_filter)
    if doctor_id:
        query = query.where(Appointment.doctor_id == doctor_id)
    if patient_id:
        query = query.where(Appointment.patient_id == patient_id)
    return list(db.scalars(query))


@router.get("/stats", response_model=StatsOut)
def stats(day: date | None = Query(default=None, alias="date"), db: Session = Depends(get_db)):
    day = day or date.today()
    start, end = _day_bounds(day)
    on_day = (Appointment.scheduled_at >= start, Appointment.scheduled_at < end)
    counts = dict(db.execute(select(Appointment.status, func.count(Appointment.id)).where(*on_day).group_by(Appointment.status)).all())
    load = db.execute(
        select(Doctor.id, Doctor.full_name, Doctor.specialty, func.count(Appointment.id))
        .join(Appointment, Appointment.doctor_id == Doctor.id)
        .where(*on_day, Appointment.status.not_in(FREE_STATUSES))
        .group_by(Doctor.id, Doctor.full_name, Doctor.specialty)
        .order_by(func.count(Appointment.id).desc())
    ).all()
    return StatsOut(
        date=day,
        total=sum(counts.values()),
        scheduled=counts.get("SCHEDULED", 0),
        checkedIn=counts.get("CHECKED_IN", 0),
        completed=counts.get("COMPLETED", 0),
        cancelled=counts.get("CANCELLED", 0),
        noShow=counts.get("NO_SHOW", 0),
        patients=db.scalar(select(func.count(Patient.id))),
        activeDoctors=db.scalar(select(func.count(Doctor.id)).where(Doctor.active.is_(True))),
        byDoctor=[DoctorLoad(doctor_id=i, full_name=n, specialty=s, appointments=c) for i, n, s, c in load],
    )


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return get_appointment_or_404(db, appointment_id)


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def book_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    get_patient_or_404(db, payload.patient_id)
    doctor = get_doctor_or_404(db, payload.doctor_id)
    if not doctor.active:
        raise HTTPException(status_code=409, detail="Doctor is not taking appointments")
    ensure_within_opening_hours(payload.scheduled_at, payload.duration_minutes)
    ensure_doctor_is_free(db, doctor.id, payload.scheduled_at, payload.duration_minutes)
    appointment = Appointment(**payload.model_dump())
    db.add(appointment)
    db.commit()
    APPOINTMENTS_BOOKED.labels(specialty=doctor.specialty).inc()
    return get_appointment_or_404(db, appointment.id)


@router.put("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(appointment_id: int, payload: AppointmentUpdate, db: Session = Depends(get_db)):
    appointment = get_appointment_or_404(db, appointment_id)
    changes = payload.model_dump(exclude_unset=True)

    new_status = changes.get("status")
    if new_status and new_status != appointment.status and new_status not in TRANSITIONS[appointment.status]:
        raise HTTPException(status_code=409, detail=f"Cannot change status from {appointment.status} to {new_status}")

    rescheduling = any(k in changes for k in ("doctor_id", "scheduled_at", "duration_minutes"))
    if rescheduling:
        if appointment.status != "SCHEDULED":
            raise HTTPException(status_code=409, detail="Only SCHEDULED appointments can be rescheduled")
        doctor_id = changes.get("doctor_id", appointment.doctor_id)
        start = changes.get("scheduled_at", appointment.scheduled_at)
        duration = changes.get("duration_minutes", appointment.duration_minutes)
        get_doctor_or_404(db, doctor_id)
        ensure_within_opening_hours(start, duration)
        ensure_doctor_is_free(db, doctor_id, start, duration, ignore_id=appointment.id)

    for key, value in changes.items():
        setattr(appointment, key, value)
    db.commit()
    if new_status:
        APPOINTMENT_STATUS_CHANGES.labels(status=new_status).inc()
    db.expire_all()
    return get_appointment_or_404(db, appointment_id)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = get_appointment_or_404(db, appointment_id)
    db.delete(appointment)
    db.commit()
