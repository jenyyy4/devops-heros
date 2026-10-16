import os

# Point the app at a throwaway SQLite file BEFORE app.config is imported,
# so tests never touch the real PostgreSQL database.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    # Fresh schema for every test so tests never depend on each other.
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:  # `with` runs the lifespan (create_all)
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def doctor(client):
    response = client.post("/api/doctors", json={"full_name": "Dr. Meera Iyer", "specialty": "General Medicine", "room": "101"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def patient(client):
    response = client.post("/api/patients", json={"full_name": "Riya Sharma", "phone": "+91 98200 11111", "email": "riya@example.com"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def book(client, doctor, patient):
    """Book an appointment for the default doctor/patient; override any field."""
    def _book(expected=201, **overrides):
        payload = {
            "patient_id": patient["id"],
            "doctor_id": doctor["id"],
            "scheduled_at": "2030-01-15T10:00:00",
            "duration_minutes": 30,
            "reason": "Fever and cough",
        }
        payload.update(overrides)
        response = client.post("/api/appointments", json=payload)
        assert response.status_code == expected, response.text
        return response.json()
    return _book
