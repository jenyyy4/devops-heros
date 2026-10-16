from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["SCHEDULED", "CHECKED_IN", "COMPLETED", "CANCELLED", "NO_SHOW"]

PHONE_PATTERN = r"^\+?[0-9 -]{7,20}$"


def _not_in_future(value: date | None) -> date | None:
    if value is not None and value > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    return value


def _naive_wall_clock(value: datetime | None) -> datetime | None:
    # Appointments are stored as clinic-local wall-clock time, so a timezone offset
    # would be ambiguous ("10:00Z" is not "10:00 at the clinic"). Reject it explicitly.
    if value is not None and value.tzinfo is not None:
        raise ValueError("send clinic-local time without a timezone, e.g. 2026-10-20T10:30:00")
    return value


# ---------------------------------------------------------------- doctors
class DoctorCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    specialty: str = Field(min_length=2, max_length=80)
    room: str = Field(default="", max_length=20)
    active: bool = True


class DoctorUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    specialty: str | None = Field(default=None, min_length=2, max_length=80)
    room: str | None = Field(default=None, max_length=20)
    active: bool | None = None


class DoctorOut(DoctorCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class DoctorRef(BaseModel):
    id: int
    full_name: str
    specialty: str
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- patients
class PatientCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(pattern=PHONE_PATTERN)
    email: str | None = Field(default=None, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    date_of_birth: date | None = None

    _check_dob = field_validator("date_of_birth")(_not_in_future)


class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    email: str | None = Field(default=None, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    date_of_birth: date | None = None

    _check_dob = field_validator("date_of_birth")(_not_in_future)


class PatientOut(PatientCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PatientRef(BaseModel):
    id: int
    full_name: str
    phone: str
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- appointments
class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    scheduled_at: datetime = Field(examples=["2026-10-20T10:30:00"])
    duration_minutes: int = Field(default=30, ge=10, le=240)
    reason: str = Field(min_length=2, max_length=200)
    notes: str = ""

    _check_tz = field_validator("scheduled_at")(_naive_wall_clock)


class AppointmentUpdate(BaseModel):
    doctor_id: int | None = None
    scheduled_at: datetime | None = Field(default=None, examples=["2026-10-20T11:00:00"])
    duration_minutes: int | None = Field(default=None, ge=10, le=240)
    reason: str | None = Field(default=None, min_length=2, max_length=200)
    status: Status | None = None
    notes: str | None = None

    _check_tz = field_validator("scheduled_at")(_naive_wall_clock)


class AppointmentOut(BaseModel):
    id: int
    scheduled_at: datetime
    duration_minutes: int
    reason: str
    status: Status
    notes: str
    created_at: datetime
    patient: PatientRef
    doctor: DoctorRef
    model_config = ConfigDict(from_attributes=True)


class DoctorLoad(BaseModel):
    doctor_id: int
    full_name: str
    specialty: str
    appointments: int


class StatsOut(BaseModel):
    date: date
    total: int
    scheduled: int
    checkedIn: int
    completed: int
    cancelled: int
    noShow: int
    patients: int
    activeDoctors: int
    byDoctor: list[DoctorLoad]
