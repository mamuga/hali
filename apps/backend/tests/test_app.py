from fastapi.testclient import TestClient

from hali.main import app


def test_root_and_health_import_without_scheduler() -> None:
    client = TestClient(app)
    assert client.get("/").json()["name"] == "HALI"
    assert client.get("/health").json() == {"status": "ok"}


def test_ussd_main_menu() -> None:
    client = TestClient(app)
    response = client.post("/ussd", data={"sessionId": "s", "serviceCode": "*123#", "phoneNumber": "+254700000000", "text": ""})
    assert response.text.startswith("CON")
