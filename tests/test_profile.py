"""Tests for /api/users/me — profile, password, avatar, sessions, notifications, activity."""
import io

BASE = "/api/users/me"


# ─── GET profile ──────────────────────────────────────────────────────────────

def test_get_profile_success(admin_client):
    r = admin_client.get(f"{BASE}/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@acme.com"
    assert data["full_name"] == "Admin User"
    assert "phone" in data
    assert "job_title" in data
    assert "timezone" in data
    assert "language" in data
    assert "avatar_url" in data


def test_get_profile_all_roles(sales_client, viewer_client, accountant_client):
    for tc in [sales_client, viewer_client, accountant_client]:
        r = tc.get(f"{BASE}/profile")
        assert r.status_code == 200


def test_get_profile_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/profile")
    assert r.status_code == 401


# ─── PATCH profile ────────────────────────────────────────────────────────────

def test_update_profile_full_name(admin_client):
    r = admin_client.patch(f"{BASE}/profile", json={"full_name": "Admin Updated"})
    assert r.status_code == 200
    assert r.json()["full_name"] == "Admin Updated"


def test_update_profile_phone(admin_client):
    r = admin_client.patch(f"{BASE}/profile", json={"phone": "+94771234567"})
    assert r.status_code == 200
    assert r.json()["phone"] == "+94771234567"


def test_update_profile_job_title(admin_client):
    r = admin_client.patch(f"{BASE}/profile", json={"job_title": "CTO"})
    assert r.status_code == 200
    assert r.json()["job_title"] == "CTO"


def test_update_profile_timezone(admin_client):
    r = admin_client.patch(f"{BASE}/profile", json={"timezone": "Asia/Colombo"})
    assert r.status_code == 200
    assert r.json()["timezone"] == "Asia/Colombo"


def test_update_profile_language(admin_client):
    r = admin_client.patch(f"{BASE}/profile", json={"language": "si"})
    assert r.status_code == 200
    assert r.json()["language"] == "si"


def test_update_profile_partial_does_not_reset_other_fields(admin_client):
    admin_client.patch(f"{BASE}/profile", json={"phone": "+1234567890"})
    admin_client.patch(f"{BASE}/profile", json={"job_title": "Manager"})
    r = admin_client.get(f"{BASE}/profile")
    assert r.json()["phone"] == "+1234567890"
    assert r.json()["job_title"] == "Manager"


def test_update_profile_viewer_can_update_own(viewer_client):
    r = viewer_client.patch(f"{BASE}/profile", json={"full_name": "Viewer Updated"})
    assert r.status_code == 200
    assert r.json()["full_name"] == "Viewer Updated"


def test_update_profile_unauthenticated(anon_client):
    r = anon_client.patch(f"{BASE}/profile", json={"full_name": "Hacked"})
    assert r.status_code == 401


# ─── Change password ──────────────────────────────────────────────────────────

def test_change_password_success(admin_client):
    r = admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "NewSecret456!",
    })
    assert r.status_code == 204


def test_change_password_wrong_current(admin_client):
    r = admin_client.post(f"{BASE}/change-password", json={
        "current_password": "WrongPass!",
        "new_password": "NewSecret456!",
    })
    assert r.status_code == 400
    assert "incorrect" in r.json()["detail"].lower()


def test_change_password_same_as_current(admin_client):
    r = admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "Secret123!",
    })
    assert r.status_code == 400
    assert "different" in r.json()["detail"].lower()


def test_change_password_too_short(admin_client):
    r = admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "abc",
    })
    assert r.status_code == 422


def test_change_password_no_uppercase(admin_client):
    r = admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "allowercase1!",
    })
    assert r.status_code == 422


def test_change_password_no_digit(admin_client):
    r = admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "NoDigitsHere!",
    })
    assert r.status_code == 422


def test_change_password_enables_new_login(admin_client):
    from fastapi.testclient import TestClient
    from app.main import app
    admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "Changed456!",
    })
    tc = TestClient(app)
    r = tc.post("/api/auth/login", json={"email": "admin@acme.com", "password": "Changed456!"})
    assert r.status_code == 200


def test_change_password_old_password_rejected_after_change(admin_client):
    from fastapi.testclient import TestClient
    from app.main import app
    admin_client.post(f"{BASE}/change-password", json={
        "current_password": "Secret123!",
        "new_password": "Changed456!",
    })
    tc = TestClient(app)
    r = tc.post("/api/auth/login", json={"email": "admin@acme.com", "password": "Secret123!"})
    assert r.status_code == 401


# ─── Avatar ───────────────────────────────────────────────────────────────────

def test_upload_avatar_png(admin_client):
    # Minimal 1x1 PNG
    png_bytes = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
        b'\x00\x11\x00\x01\x1d\xb3\xcd\xe5\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    r = admin_client.post(
        f"{BASE}/avatar",
        files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["avatar_url"] is not None
    assert "avatars" in r.json()["avatar_url"]


def test_upload_avatar_invalid_type(admin_client):
    r = admin_client.post(
        f"{BASE}/avatar",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert r.status_code == 400
    assert "jpeg" in r.json()["detail"].lower() or "png" in r.json()["detail"].lower()


def test_delete_avatar(admin_client):
    png_bytes = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
        b'\x00\x11\x00\x01\x1d\xb3\xcd\xe5\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    admin_client.post(
        f"{BASE}/avatar",
        files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
    )
    r = admin_client.delete(f"{BASE}/avatar")
    assert r.status_code == 200
    assert r.json()["avatar_url"] is None


# ─── Sessions ─────────────────────────────────────────────────────────────────

def test_list_sessions_returns_current(admin_client):
    r = admin_client.get(f"{BASE}/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) >= 1
    assert any(s["is_current"] for s in sessions)


def test_list_sessions_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/sessions")
    assert r.status_code == 401


def test_revoke_session(admin_client):
    sessions = admin_client.get(f"{BASE}/sessions").json()
    # Create a second session by logging in again
    from fastapi.testclient import TestClient
    from app.main import app
    tc2 = TestClient(app)
    tc2.post("/api/auth/login", json={"email": "admin@acme.com", "password": "Secret123!"})
    all_sessions = admin_client.get(f"{BASE}/sessions").json()
    assert len(all_sessions) >= 1
    # Revoke non-current sessions
    non_current = [s for s in all_sessions if not s["is_current"]]
    if non_current:
        r = admin_client.delete(f"{BASE}/sessions/{non_current[0]['id']}")
        assert r.status_code == 204


def test_revoke_other_org_session_not_found(admin_client, second_org_admin):
    other_sessions = second_org_admin.get(f"{BASE}/sessions").json()
    if other_sessions:
        r = admin_client.delete(f"{BASE}/sessions/{other_sessions[0]['id']}")
        assert r.status_code == 404


def test_revoke_all_other_sessions(admin_client):
    r = admin_client.delete(f"{BASE}/sessions")
    assert r.status_code == 204


# ─── Notification preferences ─────────────────────────────────────────────────

def test_get_notifications_defaults(admin_client):
    r = admin_client.get(f"{BASE}/notifications")
    assert r.status_code == 200
    data = r.json()
    assert "invoice_paid" in data
    assert "invoice_overdue" in data
    assert "quotation_approved" in data
    assert "quotation_rejected" in data
    assert "new_user_added" in data


def test_update_notifications(admin_client):
    r = admin_client.patch(f"{BASE}/notifications", json={
        "invoice_paid": False,
        "invoice_overdue": True,
        "quotation_approved": False,
        "quotation_rejected": True,
        "new_user_added": True,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["invoice_paid"] is False
    assert data["new_user_added"] is True


def test_update_notifications_persisted(admin_client):
    admin_client.patch(f"{BASE}/notifications", json={
        "invoice_paid": False,
        "invoice_overdue": True,
        "quotation_approved": True,
        "quotation_rejected": False,
        "new_user_added": True,
    })
    r = admin_client.get(f"{BASE}/notifications")
    assert r.json()["invoice_paid"] is False
    assert r.json()["new_user_added"] is True


def test_notifications_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/notifications")
    assert r.status_code == 401


# ─── Activity log ─────────────────────────────────────────────────────────────

def test_get_activity_returns_list(admin_client):
    r = admin_client.get(f"{BASE}/activity")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_activity_contains_own_actions(admin_client):
    # Trigger an auditable action
    admin_client.patch(f"{BASE}/profile", json={"full_name": "Audit Test"})
    r = admin_client.get(f"{BASE}/activity")
    actions = [entry["action"] for entry in r.json()]
    assert "UPDATE" in actions


def test_get_activity_pagination(admin_client):
    r = admin_client.get(f"{BASE}/activity", params={"skip": 0, "limit": 5})
    assert r.status_code == 200
    assert len(r.json()) <= 5


def test_get_activity_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/activity")
    assert r.status_code == 401
