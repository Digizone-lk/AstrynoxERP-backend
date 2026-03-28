"""Tests for /api/auth — register, login, refresh, logout, me."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

BASE = "/api/auth"

VALID_REG = {
    "org_name": "Acme Corp",
    "org_slug": "acme-corp",
    "currency": "USD",
    "full_name": "Admin User",
    "email": "admin@acme.com",
    "password": "Secret123!",
}


# ─── Register ─────────────────────────────────────────────────────────────────

def test_register_success():
    tc = TestClient(app)
    r = tc.post(f"{BASE}/register", json=VALID_REG)
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "admin@acme.com"
    assert data["role"] == "super_admin"
    # Cookies must be set
    assert "access_token" in tc.cookies
    assert "refresh_token" in tc.cookies


def test_register_duplicate_slug():
    tc = TestClient(app)
    tc.post(f"{BASE}/register", json=VALID_REG)
    r = tc.post(f"{BASE}/register", json={**VALID_REG, "email": "other@acme.com"})
    assert r.status_code == 409
    assert "slug" in r.json()["detail"].lower()


def test_register_invalid_slug_uppercase():
    tc = TestClient(app)
    r = tc.post(f"{BASE}/register", json={**VALID_REG, "org_slug": "Acme Corp"})
    assert r.status_code == 400
    assert "slug" in r.json()["detail"].lower()


def test_register_invalid_slug_spaces():
    tc = TestClient(app)
    r = tc.post(f"{BASE}/register", json={**VALID_REG, "org_slug": "acme corp"})
    assert r.status_code == 400


def test_register_returns_user_without_password():
    tc = TestClient(app)
    r = tc.post(f"{BASE}/register", json=VALID_REG)
    assert r.status_code == 201
    assert "hashed_password" not in r.json()
    assert "password" not in r.json()


# ─── Login ────────────────────────────────────────────────────────────────────

def test_login_success(admin_client):
    tc = TestClient(app)
    r = tc.post(f"{BASE}/login", json={"email": "admin@acme.com", "password": "Secret123!"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert "access_token" in tc.cookies


def test_login_wrong_password(admin_client):
    tc = TestClient(app)
    r = tc.post(f"{BASE}/login", json={"email": "admin@acme.com", "password": "WrongPass!"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials"


def test_login_unknown_email():
    tc = TestClient(app)
    r = tc.post(f"{BASE}/login", json={"email": "nobody@acme.com", "password": "Secret123!"})
    assert r.status_code == 401


def test_login_inactive_user(admin_client):
    me = admin_client.get(f"{BASE}/me").json()
    admin_client.patch(f"/api/users/{me['id']}", json={"is_active": False})
    tc = TestClient(app)
    r = tc.post(f"{BASE}/login", json={"email": "admin@acme.com", "password": "Secret123!"})
    assert r.status_code == 401


def test_login_inactive_org(admin_client):
    # The org itself is inactive — user credentials are fine but login should be blocked
    from app.core.database import get_db as _get_db
    from tests.conftest import TestingSessionLocal
    from app.models.organization import Organization as OrgModel
    db = TestingSessionLocal()
    try:
        org = db.query(OrgModel).first()
        org.is_active = False
        db.commit()
    finally:
        db.close()
    tc = TestClient(app)
    r = tc.post(f"{BASE}/login", json={"email": "admin@acme.com", "password": "Secret123!"})
    assert r.status_code == 403
    assert "inactive" in r.json()["detail"].lower()


# ─── Refresh ──────────────────────────────────────────────────────────────────

def test_refresh_success(admin_client):
    # admin_client already has cookies; call refresh
    r = admin_client.post(f"{BASE}/refresh")
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_refresh_no_cookie():
    tc = TestClient(app)
    r = tc.post(f"{BASE}/refresh")
    assert r.status_code == 401
    assert r.json()["detail"] == "No refresh token"


def test_refresh_with_access_token_rejected(admin_client):
    """Passing the access_token as the refresh_token cookie must be rejected."""
    access = admin_client.cookies.get("access_token")
    tc = TestClient(app)
    tc.cookies.set("refresh_token", access)
    r = tc.post(f"{BASE}/refresh")
    assert r.status_code == 401
    assert "invalid" in r.json()["detail"].lower()


# ─── Logout ───────────────────────────────────────────────────────────────────

def test_logout(admin_client):
    r = admin_client.post(f"{BASE}/logout")
    assert r.status_code == 200
    assert r.json()["message"] == "Logged out"


def test_after_logout_me_is_rejected(admin_client):
    admin_client.post(f"{BASE}/logout")
    # Cookies are cleared; new client without cookies
    tc = TestClient(app)
    r = tc.get(f"{BASE}/me")
    assert r.status_code == 401


# ─── /me ──────────────────────────────────────────────────────────────────────

def test_me_authenticated(admin_client):
    r = admin_client.get(f"{BASE}/me")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@acme.com"
    assert data["role"] == "super_admin"
    assert "org_currency" in data


def test_me_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/me")
    assert r.status_code == 401


def test_me_rejects_refresh_token(admin_client):
    """Bug fix check: /me must reject a refresh token used as access token."""
    refresh = admin_client.cookies.get("refresh_token")
    tc = TestClient(app)
    tc.cookies.set("access_token", refresh)
    r = tc.get(f"{BASE}/me")
    assert r.status_code == 401
