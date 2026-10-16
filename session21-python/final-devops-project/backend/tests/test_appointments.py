import pytest


def test_book_appointment(book, doctor, patient):
    appt = book()
    assert appt["status"] == "SCHEDULED"
    assert appt["scheduled_at"] == "2030-01-15T10:00:00"
    assert appt["patient"] == {"id": patient["id"], "full_name": "Riya Sharma", "phone": "+91 98200 11111"}
    assert appt["doctor"]["specialty"] == "General Medicine"


def test_booking_requires_existing_patient_and_doctor(book):
    assert book(expected=404, patient_id=9999)["detail"] == "Patient not found"
    assert book(expected=404, doctor_id=9999)["detail"] == "Doctor not found"


def test_cannot_book_inactive_doctor(client, book, doctor):
    client.put(f"/api/doctors/{doctor['id']}", json={"active": False})
    book(expected=409)


@pytest.mark.parametrize("start, duration", [("2030-01-15T07:30:00", 30), ("2030-01-15T19:45:00", 30)])
def test_booking_outside_opening_hours_rejected(book, start, duration):
    assert "between 08:00 and 20:00" in book(expected=422, scheduled_at=start, duration_minutes=duration)["detail"]


def test_timezone_aware_times_rejected(book):
    book(expected=422, scheduled_at="2030-01-15T10:00:00Z")


def test_double_booking_same_doctor_conflicts(book):
    first = book()
    clash = book(expected=409, scheduled_at="2030-01-15T10:15:00")
    assert f"#{first['id']}" in clash["detail"]
    book(scheduled_at="2030-01-15T10:30:00")  # back-to-back is fine


def test_cancelled_slot_can_be_rebooked(client, book):
    first = book()
    client.put(f"/api/appointments/{first['id']}", json={"status": "CANCELLED"})
    book()


def test_conflict_counter_in_metrics(client, book):
    book()
    book(expected=409)
    assert "clinicflow_booking_conflicts_total" in client.get("/metrics").text


def test_list_filters_by_date_status_doctor_patient(client, book, doctor, patient):
    a = book(scheduled_at="2030-01-15T09:00:00")
    b = book(scheduled_at="2030-01-16T09:00:00")
    client.put(f"/api/appointments/{b['id']}", json={"status": "CHECKED_IN"})
    assert [x["id"] for x in client.get("/api/appointments").json()] == [a["id"], b["id"]]  # chronological
    assert [x["id"] for x in client.get("/api/appointments?date=2030-01-15").json()] == [a["id"]]
    assert [x["id"] for x in client.get("/api/appointments?status=CHECKED_IN").json()] == [b["id"]]
    assert len(client.get(f"/api/appointments?doctor_id={doctor['id']}&patient_id={patient['id']}").json()) == 2


def test_get_appointment_and_404(client, book):
    appt = book()
    assert client.get(f"/api/appointments/{appt['id']}").json()["reason"] == "Fever and cough"
    assert client.get("/api/appointments/9999").status_code == 404


def test_status_workflow(client, book):
    appt = book()
    for status in ("CHECKED_IN", "COMPLETED"):
        response = client.put(f"/api/appointments/{appt['id']}", json={"status": status, "notes": "BP normal"})
        assert response.status_code == 200
        assert response.json()["status"] == status
    assert response.json()["notes"] == "BP normal"


@pytest.mark.parametrize("path", [["COMPLETED"], ["NO_SHOW", "SCHEDULED"], ["CANCELLED", "CHECKED_IN"]])
def test_invalid_status_transitions_rejected(client, book, path):
    appt = book()
    *allowed, forbidden = path
    for status in allowed:
        assert client.put(f"/api/appointments/{appt['id']}", json={"status": status}).status_code == 200
    response = client.put(f"/api/appointments/{appt['id']}", json={"status": forbidden})
    assert response.status_code == 409
    assert "Cannot change status" in response.json()["detail"]


def test_reschedule(client, book):
    appt = book()
    other = book(scheduled_at="2030-01-15T11:00:00")
    # moving onto another booking clashes, moving within its own slot does not
    assert client.put(f"/api/appointments/{appt['id']}", json={"scheduled_at": "2030-01-15T11:00:00"}).status_code == 409
    response = client.put(f"/api/appointments/{appt['id']}", json={"scheduled_at": "2030-01-15T10:10:00", "duration_minutes": 45})
    assert response.status_code == 200
    assert response.json()["scheduled_at"] == "2030-01-15T10:10:00"
    assert client.put(f"/api/appointments/{other['id']}", json={"doctor_id": 9999}).status_code == 404


def test_only_scheduled_appointments_can_be_rescheduled(client, book):
    appt = book()
    client.put(f"/api/appointments/{appt['id']}", json={"status": "CHECKED_IN"})
    response = client.put(f"/api/appointments/{appt['id']}", json={"scheduled_at": "2030-01-15T12:00:00"})
    assert response.status_code == 409


def test_update_missing_appointment_returns_404(client):
    assert client.put("/api/appointments/9999", json={"status": "CANCELLED"}).status_code == 404


def test_delete_appointment(client, book):
    appt = book()
    assert client.delete(f"/api/appointments/{appt['id']}").status_code == 204
    assert client.delete(f"/api/appointments/{appt['id']}").status_code == 404


def test_daily_stats(client, book, doctor):
    second_doctor = client.post("/api/doctors", json={"full_name": "Dr. Arjun Mehta", "specialty": "Cardiology"}).json()
    a = book(scheduled_at="2030-01-15T09:00:00")
    b = book(scheduled_at="2030-01-15T10:00:00")
    c = book(scheduled_at="2030-01-15T11:00:00")
    book(scheduled_at="2030-01-15T09:00:00", doctor_id=second_doctor["id"])
    book(scheduled_at="2030-01-16T09:00:00")  # other day, not counted
    client.put(f"/api/appointments/{a['id']}", json={"status": "CHECKED_IN"})
    client.put(f"/api/appointments/{b['id']}", json={"status": "CANCELLED"})
    client.put(f"/api/appointments/{c['id']}", json={"status": "NO_SHOW"})

    stats = client.get("/api/appointments/stats?date=2030-01-15").json()
    assert stats["date"] == "2030-01-15"
    assert (stats["total"], stats["scheduled"], stats["checkedIn"], stats["cancelled"], stats["noShow"], stats["completed"]) == (4, 1, 1, 1, 1, 0)
    assert (stats["patients"], stats["activeDoctors"]) == (1, 2)
    # cancelled / no-show appointments do not count towards a doctor's load
    assert {d["full_name"]: d["appointments"] for d in stats["byDoctor"]} == {"Dr. Meera Iyer": 1, "Dr. Arjun Mehta": 1}


def test_stats_defaults_to_today(client):
    stats = client.get("/api/appointments/stats").json()
    assert stats["total"] == 0
    assert stats["byDoctor"] == []
