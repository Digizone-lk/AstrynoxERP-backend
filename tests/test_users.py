"""Tests for /api/users — CRUD, RBAC, tenant isolation, admin actions."""

BASE = "/api/users"


# ─── List ─────────────────────────────────────────────────────────────────────

def test_list_users_returns_own_org(admin_client):
    r = admin_client.get(f"{BASE}/")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "admin@acme.com" in emails


def test_list_users_non_admin_forbidden(sales_client, viewer_client, accountant_client):
    for tc in [sales_client, viewer_client, accountant_client]:
        r = tc.get(f"{BASE}/")
        assert r.status_code == 403


def test_list_users_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/")
    assert r.status_code == 401


def test_list_users_tenant_isolation(admin_client, second_org_admin):
    r = second_org_admin.get(f"{BASE}/")
    emails = [u["email"] for u in r.json()]
    assert "admin@acme.com" not in emails
    assert "admin@other.com" in emails


# ─── Create ───────────────────────────────────────────────────────────────────

def test_create_user_success(admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "new@acme.com",
        "full_name": "New User",
        "password": "Secret123!",
        "role": "viewer",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "new@acme.com"
    assert data["role"] == "viewer"
    assert "hashed_password" not in data


def test_create_user_duplicate_email(admin_client):
    admin_client.post(f"{BASE}/", json={
        "email": "dup@acme.com", "full_name": "Dup", "password": "Secret123!", "role": "viewer",
    })
    r = admin_client.post(f"{BASE}/", json={
        "email": "dup@acme.com", "full_name": "Dup2", "password": "Secret123!", "role": "viewer",
    })
    assert r.status_code == 409


def test_create_user_non_admin_forbidden(sales_client):
    r = sales_client.post(f"{BASE}/", json={
        "email": "x@acme.com", "full_name": "X", "password": "Secret123!", "role": "viewer",
    })
    assert r.status_code == 403


def test_create_user_all_roles(admin_client):
    for role in ["accountant", "sales", "viewer", "super_admin"]:
        r = admin_client.post(f"{BASE}/", json={
            "email": f"{role}@acme.com",
            "full_name": role.title(),
            "password": "Secret123!",
            "role": role,
        })
        assert r.status_code == 201
        assert r.json()["role"] == role


# ─── Get by ID ────────────────────────────────────────────────────────────────

def test_get_user_success(admin_client):
    r = admin_client.get(f"{BASE}/")
    user_id = r.json()[0]["id"]
    r2 = admin_client.get(f"{BASE}/{user_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == user_id


def test_get_user_not_found(admin_client):
    r = admin_client.get(f"{BASE}/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404


def test_get_user_other_org_returns_404(admin_client, second_org_admin):
    other_users = second_org_admin.get(f"{BASE}/").json()
    r = admin_client.get(f"{BASE}/{other_users[0]['id']}")
    assert r.status_code == 404


# ─── Update ───────────────────────────────────────────────────────────────────

def test_update_user_role(admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "u@acme.com", "full_name": "U", "password": "Secret123!", "role": "viewer",
    })
    uid = r.json()["id"]
    r2 = admin_client.patch(f"{BASE}/{uid}", json={"role": "sales"})
    assert r2.status_code == 200
    assert r2.json()["role"] == "sales"


def test_update_user_name(admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "u2@acme.com", "full_name": "Old Name", "password": "Secret123!", "role": "viewer",
    })
    uid = r.json()["id"]
    r2 = admin_client.patch(f"{BASE}/{uid}", json={"full_name": "New Name"})
    assert r2.status_code == 200
    assert r2.json()["full_name"] == "New Name"


def test_update_user_non_admin_forbidden(sales_client, admin_client):
    uid = admin_client.get(f"{BASE}/").json()[0]["id"]
    r = sales_client.patch(f"{BASE}/{uid}", json={"full_name": "Hacked"})
    assert r.status_code == 403


# ─── Deactivate ───────────────────────────────────────────────────────────────

def test_deactivate_user(admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "deact@acme.com", "full_name": "Deact", "password": "Secret123!", "role": "viewer",
    })
    uid = r.json()["id"]
    r2 = admin_client.post(f"{BASE}/{uid}/deactivate")
    assert r2.status_code == 200
    assert r2.json()["is_active"] is False


def test_deactivate_self_forbidden(admin_client):
    me = admin_client.get("/api/auth/me").json()
    r = admin_client.post(f"{BASE}/{me['id']}/deactivate")
    assert r.status_code == 400


def test_deactivate_user_blocks_login(admin_client):
    from fastapi.testclient import TestClient
    from app.main import app
    admin_client.post(f"{BASE}/", json={
        "email": "deact2@acme.com", "full_name": "D", "password": "Secret123!", "role": "viewer",
    })
    users = admin_client.get(f"{BASE}/").json()
    uid = next(u["id"] for u in users if u["email"] == "deact2@acme.com")
    admin_client.post(f"{BASE}/{uid}/deactivate")
    tc = TestClient(app)
    r = tc.post("/api/auth/login", json={"email": "deact2@acme.com", "password": "Secret123!"})
    assert r.status_code == 401


# ─── Reactivate ───────────────────────────────────────────────────────────────

def test_reactivate_user(admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "react@acme.com", "full_name": "React", "password": "Secret123!", "role": "viewer",
    })
    uid = r.json()["id"]
    admin_client.post(f"{BASE}/{uid}/deactivate")
    r2 = admin_client.post(f"{BASE}/{uid}/reactivate")
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True


def test_reactivate_already_active_rejected(admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "react2@acme.com", "full_name": "React2", "password": "Secret123!", "role": "viewer",
    })
    uid = r.json()["id"]
    r2 = admin_client.post(f"{BASE}/{uid}/reactivate")
    assert r2.status_code == 400
    assert "already active" in r2.json()["detail"].lower()


def test_reactivate_user_not_found(admin_client):
    r = admin_client.post(f"{BASE}/00000000-0000-0000-0000-000000000001/reactivate")
    assert r.status_code == 404


def test_reactivate_user_other_org_returns_404(admin_client, second_org_admin):
    other_users = second_org_admin.get(f"{BASE}/").json()
    uid = other_users[0]["id"]
    # deactivate in the other org first
    second_org_admin.post(f"{BASE}/{uid}/deactivate")
    r = admin_client.post(f"{BASE}/{uid}/reactivate")
    assert r.status_code == 404


def test_reactivate_non_admin_forbidden(sales_client, admin_client):
    r = admin_client.post(f"{BASE}/", json={
        "email": "react3@acme.com", "full_name": "React3", "password": "Secret123!", "role": "viewer",
    })
    uid = r.json()["id"]
    admin_client.post(f"{BASE}/{uid}/deactivate")
    r2 = sales_client.post(f"{BASE}/{uid}/reactivate")
    assert r2.status_code == 403


def test_reactivate_restores_login(admin_client):
    from fastapi.testclient import TestClient
    from app.main import app
    admin_client.post(f"{BASE}/", json={
        "email": "react4@acme.com", "full_name": "React4", "password": "Secret123!", "role": "viewer",
    })
    users = admin_client.get(f"{BASE}/").json()
    uid = next(u["id"] for u in users if u["email"] == "react4@acme.com")
    admin_client.post(f"{BASE}/{uid}/deactivate")
    admin_client.post(f"{BASE}/{uid}/reactivate")
    tc = TestClient(app)
    r = tc.post("/api/auth/login", json={"email": "react4@acme.com", "password": "Secret123!"})
    assert r.status_code == 200


# ─── Admin password reset ─────────────────────────────────────────────────────

def test_admin_reset_password(admin_client):
    admin_client.post(f"{BASE}/", json={
        "email": "reset@acme.com", "full_name": "Reset", "password": "Secret123!", "role": "viewer",
    })
    users = admin_client.get(f"{BASE}/").json()
    uid = next(u["id"] for u in users if u["email"] == "reset@acme.com")
    r = admin_client.post(f"{BASE}/{uid}/reset-password", json={"new_password": "NewPass456!"})
    assert r.status_code == 204


def test_admin_reset_password_weak_rejected(admin_client):
    admin_client.post(f"{BASE}/", json={
        "email": "reset2@acme.com", "full_name": "R2", "password": "Secret123!", "role": "viewer",
    })
    users = admin_client.get(f"{BASE}/").json()
    uid = next(u["id"] for u in users if u["email"] == "reset2@acme.com")
    r = admin_client.post(f"{BASE}/{uid}/reset-password", json={"new_password": "weak"})
    assert r.status_code == 422


def test_admin_reset_enables_new_login(admin_client):
    from fastapi.testclient import TestClient
    from app.main import app
    admin_client.post(f"{BASE}/", json={
        "email": "reset3@acme.com", "full_name": "R3", "password": "Secret123!", "role": "viewer",
    })
    users = admin_client.get(f"{BASE}/").json()
    uid = next(u["id"] for u in users if u["email"] == "reset3@acme.com")
    admin_client.post(f"{BASE}/{uid}/reset-password", json={"new_password": "Brand456New!"})
    tc = TestClient(app)
    r = tc.post("/api/auth/login", json={"email": "reset3@acme.com", "password": "Brand456New!"})
    assert r.status_code == 200


def test_admin_reset_non_admin_forbidden(sales_client, admin_client):
    uid = admin_client.get(f"{BASE}/").json()[0]["id"]
    r = sales_client.post(f"{BASE}/{uid}/reset-password", json={"new_password": "Hacked123!"})
    assert r.status_code == 403


# ─── User activity log ────────────────────────────────────────────────────────

def test_get_user_activity_returns_list(admin_client):
    me = admin_client.get("/api/auth/me").json()
    r = admin_client.get(f"{BASE}/{me['id']}/activity")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_user_activity_non_admin_forbidden(sales_client, admin_client):
    uid = admin_client.get(f"{BASE}/").json()[0]["id"]
    r = sales_client.get(f"{BASE}/{uid}/activity")
    assert r.status_code == 403
