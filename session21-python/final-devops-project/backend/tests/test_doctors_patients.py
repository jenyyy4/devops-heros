from datetime import date, timedelta


# ---------------------------------------------------------------- doctors
def test_create_and_list_doctors(client, doctor):
    client.post("/api/doctors", json={"full_name": "Dr. Arjun Mehta", "specialty": "Cardiology"})
    names = [d["full_name"] for d in client.get("/api/doctors").json()]
    assert names == ["Dr. Arjun Mehta", "Dr. Meera Iyer"]  # alphabetical
    assert doctor["active"] is True


def test_get_doctor_and_404(client, doctor):
    assert client.get(f"/api/doctors/{doctor['id']}").json()["specialty"] == "General Medicine"
    assert client.get("/api/doctors/9999").status_code == 404


def test_deactivated_doctor_hidden_from_active_list(client, doctor):
    response = client.put(f"/api/doctors/{doctor['id']}", json={"active": False})
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert client.get("/api/doctors?active_only=true").json() == []
    assert len(client.get("/api/doctors").json()) == 1


def test_create_doctor_validation(client):
    assert client.post("/api/doctors", json={"full_name": "X", "specialty": "Cardiology"}).status_code == 422


# ---------------------------------------------------------------- patients
def test_register_patient(client, patient):
    assert patient["id"] > 0
    assert patient["email"] == "riya@example.com"
    assert "created_at" in patient


def test_patient_validation(client):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.post("/api/patients", json={"full_name": "Aman", "phone": "abc"}).status_code == 422
    assert client.post("/api/patients", json={"full_name": "Aman", "phone": "9820011111", "email": "not-an-email"}).status_code == 422
    assert client.post("/api/patients", json={"full_name": "Aman", "phone": "9820011111", "date_of_birth": tomorrow}).status_code == 422


def test_search_patients_by_name_or_phone(client, patient):
    client.post("/api/patients", json={"full_name": "Kabir Singh", "phone": "+91 99300 22222"})
    assert [p["full_name"] for p in client.get("/api/patients?search=riya").json()] == ["Riya Sharma"]
    assert [p["full_name"] for p in client.get("/api/patients?search=99300").json()] == ["Kabir Singh"]
    assert len(client.get("/api/patients").json()) == 2


def test_update_patient_partial(client, patient):
    response = client.put(f"/api/patients/{patient['id']}", json={"phone": "+91 90000 00000"})
    assert response.status_code == 200
    assert response.json()["phone"] == "+91 90000 00000"
    assert response.json()["full_name"] == "Riya Sharma"  # untouched fields are kept
    assert client.put("/api/patients/9999", json={"phone": "9820011111"}).status_code == 404


def test_delete_patient(client, patient):
    assert client.delete(f"/api/patients/{patient['id']}").status_code == 204
    assert client.get(f"/api/patients/{patient['id']}").status_code == 404
    assert client.delete(f"/api/patients/{patient['id']}").status_code == 404


def test_patient_with_appointments_cannot_be_deleted(client, patient, book):
    book()
    response = client.delete(f"/api/patients/{patient['id']}")
    assert response.status_code == 409
    assert "appointments" in response.json()["detail"]
