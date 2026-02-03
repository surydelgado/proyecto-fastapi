"""
Pruebas del flujo QR de asistencia.
- GET con token válido muestra formulario HTML
- POST registra asistencia
- POST repetido no duplica (Ya registrado)
- Token inválido devuelve error claro
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.qr_token_service import generate_qr_token, validate_qr_token
from app.auth import get_current_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_token():
    return generate_qr_token(1, expiry_ts=9999999999)


@pytest.fixture
def auth_user():
    return {
        "id": "user-123",
        "email": "user@test.com",
        "role": "student",
        "user_metadata": {"role": "student"},
    }


def test_validate_qr_token_roundtrip():
    token = generate_qr_token(5)
    parsed = validate_qr_token(token)
    assert parsed is not None
    event_id, expiry_ts = parsed
    assert event_id == 5


def test_validate_qr_token_invalid_returns_none():
    assert validate_qr_token("") is None
    assert validate_qr_token("invalid") is None
    assert validate_qr_token("bad.token.here") is None


def test_get_scan_qr_sin_token_muestra_error(client):
    response = client.get("/attendance/scan-qr")
    assert response.status_code == 200
    assert "Falta el código" in response.text or "error" in response.text.lower()


def test_get_scan_qr_token_invalido_muestra_error(client):
    response = client.get("/attendance/scan-qr?token=token-invalido-xyz")
    assert response.status_code == 200
    assert "inválido" in response.text or "expirado" in response.text or "error" in response.text.lower()


def test_get_scan_qr_token_valido_requiere_login(client, valid_token):
    with patch("app.api.attendance._sb") as mock_sb:
        chain = MagicMock()
        chain.execute.return_value = MagicMock(
            data=[{"id": 1, "title": "Evento Test", "status": "approved", "is_active": True, "start_date": "2025-01-01T10:00:00", "end_date": "2025-12-31T18:00:00"}]
        )
        mock_sb.return_value.table.return_value.select.return_value.eq.return_value = chain
        response = client.get(f"/attendance/scan-qr?token={valid_token}")
    assert response.status_code == 200
    assert "Debes iniciar sesión" in response.text or "Iniciar Sesión" in response.text


def test_post_scan_qr_registra_ok(client, valid_token, auth_user):
    def table_side_effect(name):
        t = MagicMock()
        if name == "events":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "title": "E", "status": "approved", "is_active": True, "start_date": "2020-01-01T10:00:00", "end_date": "2030-12-31T18:00:00"}]
            )
        elif name == "attendances":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "user_id": auth_user["id"], "event_id": 1, "attended": False, "created_at": "2025-01-01T00:00:00"}]
            )
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "attended_at": "2025-01-01T01:00:00"}]
            )
        return t

    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        with patch("app.api.attendance._sb") as mock_sb:
            mock_sb.return_value.table.side_effect = table_side_effect
            response = client.post(
                "/attendance/scan-qr",
                json={"token": valid_token},
            )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "attended"
        assert data.get("event_id") == 1
    finally:
        app.dependency_overrides.clear()


def test_post_scan_qr_token_invalido_error(client, auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        response = client.post(
            "/attendance/scan-qr",
            json={"token": "invalid-token"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "inválido" in data["detail"].lower() or "expirado" in data["detail"].lower()


def test_post_scan_qr_repetido_no_duplica(client, valid_token, auth_user):
    def table_side_effect(name):
        t = MagicMock()
        if name == "events":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "title": "E", "status": "approved", "is_active": True, "start_date": "2020-01-01T10:00:00", "end_date": "2030-12-31T18:00:00"}]
            )
        elif name == "attendances":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "user_id": auth_user["id"], "event_id": 1, "attended": True, "created_at": "2025-01-01T00:00:00"}]
            )
        return t

    app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        with patch("app.api.attendance._sb") as mock_sb:
            mock_sb.return_value.table.side_effect = table_side_effect
            response = client.post(
                "/attendance/scan-qr",
                json={"token": valid_token},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "ya registraste" in data["detail"].lower()
