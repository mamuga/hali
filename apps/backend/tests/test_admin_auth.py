from fastapi.testclient import TestClient

from hali.config import settings
from hali.main import app


def test_admin_requires_key_when_configured(monkeypatch) -> None:
    """Admin endpoints return 401 without a key when auth is enabled."""
    monkeypatch.setattr(settings, "admin_api_key", "test-secret-key-abc")
    client = TestClient(app)
    response = client.get("/api/admin/pipeline-status")
    assert response.status_code == 401


def test_admin_rejects_wrong_key(monkeypatch) -> None:
    """Admin endpoints return 403 with the wrong key."""
    monkeypatch.setattr(settings, "admin_api_key", "test-secret-key-abc")
    client = TestClient(app)
    response = client.get("/api/admin/pipeline-status", headers={"X-Admin-Key": "wrong"})
    assert response.status_code == 403


def test_admin_accepts_correct_key(monkeypatch) -> None:
    """Admin endpoints return 200 with the correct key."""
    monkeypatch.setattr(settings, "admin_api_key", "test-secret-key-abc")
    client = TestClient(app)
    response = client.get("/api/admin/pipeline-status", headers={"X-Admin-Key": "test-secret-key-abc"})
    assert response.status_code == 200


def test_admin_open_without_key_configured(monkeypatch) -> None:
    """Admin endpoints stay open (dev mode) when no key is configured."""
    monkeypatch.setattr(settings, "admin_api_key", "")
    client = TestClient(app)
    response = client.get("/api/admin/pipeline-status")
    assert response.status_code == 200


def test_admin_disabled_returns_403(monkeypatch) -> None:
    """The enable_admin_endpoints master switch still takes priority."""
    monkeypatch.setattr(settings, "enable_admin_endpoints", False)
    client = TestClient(app)
    response = client.get("/api/admin/pipeline-status", headers={"X-Admin-Key": "anything"})
    assert response.status_code == 403
