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


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def valid_token():
    return generate_qr_token(1, expiry_ts=9999999999)


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


def test_get_qr_asistencia_sin_token_muestra_error(client):
    response = client.get("/qr/asistencia")
    assert response.status_code == 200
    assert "Falta el código" in response.text or "error" in response.text.lower()


def test_get_qr_asistencia_token_invalido_muestra_error(client):
    response = client.get("/qr/asistencia?token=token-invalido-xyz")
    assert response.status_code == 200
    assert "inválido" in response.text or "expirado" in response.text or "error" in response.text.lower()


def test_get_qr_asistencia_token_valido_muestra_formulario(client, valid_token):
    with patch("app.api.qr_asistencia._sb") as mock_sb:
        chain = MagicMock()
        chain.execute.return_value = MagicMock(
            data=[{"id": 1, "title": "Evento Test", "status": "approved", "is_active": True, "start_date": "2025-01-01T10:00:00", "end_date": "2025-12-31T18:00:00"}]
        )
        mock_sb.table.return_value.select.return_value.eq.return_value = chain
        response = client.get(f"/qr/asistencia?token={valid_token}")
    assert response.status_code == 200
    assert "form" in response.text.lower()
    assert "Registrar" in response.text or "asistencia" in response.text


def test_post_qr_asistencia_registra_ok(client, valid_token):
    def table_side_effect(name):
        t = MagicMock()
        if name == "events":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "title": "E", "status": "approved", "is_active": True, "start_date": "2020-01-01T10:00:00", "end_date": "2030-12-31T18:00:00"}]
            )
        elif name == "event_checkins":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
        return t

    with patch("app.api.qr_asistencia._sb") as mock_sb:
        mock_sb.table.side_effect = table_side_effect
        response = client.post(
            "/qr/asistencia",
            json={"token": valid_token, "names": "Juan Pérez", "email": "juan@test.com", "cedula": None},
        )
    assert response.status_code == 201
    data = response.json()
    assert data.get("success") is True
    assert "registrada" in data.get("message", "").lower() or "Asistencia" in data.get("message", "")


def test_post_qr_asistencia_token_invalido_error(client):
    response = client.post(
        "/qr/asistencia",
        json={"token": "invalid-token", "names": "Juan", "email": "j@t.com"},
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "inválido" in data["detail"].lower() or "expirado" in data["detail"].lower()


def test_post_qr_asistencia_repetido_no_duplica(client, valid_token):
    def table_side_effect(name):
        t = MagicMock()
        if name == "events":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "title": "E", "status": "approved", "is_active": True, "start_date": "2020-01-01T10:00:00", "end_date": "2030-12-31T18:00:00"}]
            )
        elif name == "event_checkins":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
        return t

    with patch("app.api.qr_asistencia._sb") as mock_sb:
        mock_sb.table.side_effect = table_side_effect
        response = client.post(
            "/qr/asistencia",
            json={"token": valid_token, "names": "Juan Pérez", "email": "juan@test.com"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is False
    assert data.get("duplicate") is True or "Ya registrado" in data.get("message", "")
