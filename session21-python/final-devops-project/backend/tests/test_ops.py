def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_ready_checks_database(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "READY"}


def test_root(client):
    body = client.get("/").json()
    assert body["service"] == "ClinicFlow API"
    assert body["version"] == "1.0.0"


def test_metrics_expose_http_and_business_metrics(client, book):
    book()
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert 'clinicflow_appointments_booked_total{specialty="General Medicine"}' in response.text


def test_cors_allows_only_configured_origins(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    blocked = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers
