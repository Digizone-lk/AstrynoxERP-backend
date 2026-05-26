from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import TestingSessionLocal
from app.modules.ims.models.organization import Organization
from app.modules.ims.models.user_session import UserSession


ADMIN_EMAIL = "brayanjayawardhana@gmail.com"
ADMIN_PASSWORD = "Password123"


def _product_admin_token():
    tc = TestClient(app)
    r = tc.post("/api/product-admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_product_admin_login_rejects_wrong_password():
    tc = TestClient(app)
    r = tc.post("/api/product-admin/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_product_admin_invite_creates_trial_org_and_temp_login(monkeypatch):
    sent = {}

    def fake_send(to, username, temporary_password, invite_link):
        sent.update({
            "to": to,
            "username": username,
            "temporary_password": temporary_password,
            "invite_link": invite_link,
        })

    monkeypatch.setattr("app.modules.ims.routers.product_admin.send_organization_invite_email", fake_send)
    token = _product_admin_token()

    tc = TestClient(app)
    r = tc.post(
        "/api/product-admin/organizations/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "new-org", "email": "owner@example.com"},
    )

    assert r.status_code == 201, r.text
    data = r.json()
    assert data["username"] == "new-org"
    assert sent["to"] == "owner@example.com"
    assert sent["username"] == "new-org"
    assert len(sent["temporary_password"]) == 32

    login = tc.post("/api/auth/login", json={"email": "new-org", "password": sent["temporary_password"]})
    assert login.status_code == 200, login.text
    login_data = login.json()
    assert login_data["must_change_password"] is True
    assert login_data["email_verified"] is False
    assert login_data["onboarding_status"] == "invited"
    assert login_data["subscription_status"] == "trial"


def test_product_admin_can_activate_paid_plan(admin_client):
    token = _product_admin_token()
    db = TestingSessionLocal()
    try:
        org = db.query(Organization).first()
        org.subscription_status = "trial_expired"
        db.commit()
        org_id = str(org.id)
    finally:
        db.close()

    tc = TestClient(app)
    r = tc.post(
        f"/api/product-admin/organizations/{org_id}/activate-paid",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan": "business"},
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["subscription_status"] == "paid"
    assert data["plan"] == "business"


def test_expired_trial_blocks_normal_api_but_allows_me(admin_client):
    db = TestingSessionLocal()
    try:
        org = db.query(Organization).first()
        org.subscription_status = "trial"
        org.trial_end_date = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    me = admin_client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["subscription_status"] == "trial_expired"

    blocked = admin_client.get("/api/clients/")
    assert blocked.status_code == 402
    assert blocked.json()["detail"]["code"] == "TRIAL_EXPIRED"


def _invited_onboarding_client(monkeypatch):
    sent_invite = {}

    def fake_invite_send(to, username, temporary_password, invite_link):
        sent_invite.update({
            "to": to,
            "username": username,
            "temporary_password": temporary_password,
            "invite_link": invite_link,
        })
        return True

    monkeypatch.setattr("app.modules.ims.routers.product_admin.send_organization_invite_email", fake_invite_send)
    token = _product_admin_token()

    tc = TestClient(app)
    invite = tc.post(
        "/api/product-admin/organizations/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "otp-org", "email": "otp-owner@example.com"},
    )
    assert invite.status_code == 201, invite.text

    login = tc.post("/api/auth/login", json={"email": "otp-org", "password": sent_invite["temporary_password"]})
    assert login.status_code == 200, login.text

    changed = tc.post("/api/auth/onboarding/change-password", json={"new_password": "NewSecret123!"})
    assert changed.status_code == 200, changed.text

    login = tc.post("/api/auth/login", json={"email": "otp-org", "password": "NewSecret123!"})
    assert login.status_code == 200, login.text
    return tc


def test_onboarding_send_otp_is_rate_limited(monkeypatch):
    sent_otps = []

    def fake_otp_send(to, otp):
        sent_otps.append(otp)
        return True

    monkeypatch.setattr("app.modules.ims.routers.auth.send_onboarding_otp_email", fake_otp_send)
    tc = _invited_onboarding_client(monkeypatch)

    for _ in range(3):
        response = tc.post("/api/auth/onboarding/send-otp")
        assert response.status_code == 200, response.text

    limited = tc.post("/api/auth/onboarding/send-otp")
    assert limited.status_code == 429
    assert "Too many OTP requests" in limited.json()["detail"]
    assert len(sent_otps) == 3


def test_onboarding_verify_otp_is_rate_limited(monkeypatch):
    monkeypatch.setattr("app.modules.ims.routers.auth.send_onboarding_otp_email", lambda to, otp: True)
    tc = _invited_onboarding_client(monkeypatch)

    sent = tc.post("/api/auth/onboarding/send-otp")
    assert sent.status_code == 200, sent.text

    for _ in range(5):
        response = tc.post("/api/auth/onboarding/verify-otp", json={"otp": "000000"})
        assert response.status_code == 400, response.text

    limited = tc.post("/api/auth/onboarding/verify-otp", json={"otp": "000000"})
    assert limited.status_code == 429
    assert "Too many OTP requests" in limited.json()["detail"]


def test_inactive_user_requires_otp_on_login(monkeypatch):
    sent_otps = []

    def fake_otp_send(to, otp):
        sent_otps.append(otp)
        return True

    monkeypatch.setattr("app.modules.ims.routers.auth.send_onboarding_otp_email", fake_otp_send)

    tc = TestClient(app)
    registered = tc.post("/api/auth/register", json={
        "org_name": "Inactive Corp",
        "org_slug": "inactive-corp",
        "currency": "USD",
        "full_name": "Inactive Admin",
        "email": "inactive@example.com",
        "password": "Secret123!",
    })
    assert registered.status_code == 201, registered.text

    db = TestingSessionLocal()
    try:
        old_activity = datetime.now(timezone.utc) - timedelta(days=4)
        db.query(UserSession).update({"last_active_at": old_activity})
        db.commit()
    finally:
        db.close()

    login = tc.post("/api/auth/login", json={"email": "inactive@example.com", "password": "Secret123!"})
    assert login.status_code == 200, login.text
    assert login.json()["requires_otp_verification"] is True

    blocked = tc.get("/api/clients/")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "OTP_REQUIRED"

    sent = tc.post("/api/auth/onboarding/send-otp")
    assert sent.status_code == 200, sent.text
    assert len(sent_otps) == 1

    verified = tc.post("/api/auth/onboarding/verify-otp", json={"otp": sent_otps[0]})
    assert verified.status_code == 200, verified.text
    assert verified.json()["requires_otp_verification"] is False

    allowed = tc.get("/api/clients/")
    assert allowed.status_code == 200, allowed.text
