from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import TestingSessionLocal
from app.modules.ims.models.organization import Organization


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
