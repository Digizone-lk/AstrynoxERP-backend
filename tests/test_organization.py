"""Tests for /api/org — get and update organization settings."""

BASE = "/api/org"


# ─── GET /api/org ─────────────────────────────────────────────────────────────

def test_get_org_success(admin_client):
    r = admin_client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"
    assert data["currency"] == "USD"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


def test_get_org_all_roles_can_read(sales_client, accountant_client, viewer_client):
    for tc in [sales_client, accountant_client, viewer_client]:
        r = tc.get(BASE)
        assert r.status_code == 200
        assert r.json()["name"] == "Acme Corp"


def test_get_org_unauthenticated(anon_client):
    r = anon_client.get(BASE)
    assert r.status_code == 401


def test_get_org_tenant_isolation(admin_client, second_org_admin):
    r1 = admin_client.get(BASE).json()
    r2 = second_org_admin.get(BASE).json()
    assert r1["id"] != r2["id"]
    assert r1["slug"] == "acme-corp"
    assert r2["slug"] == "other-org"


# ─── PATCH /api/org ───────────────────────────────────────────────────────────

def test_update_org_name(admin_client):
    r = admin_client.patch(BASE, json={"name": "Acme Corporation"})
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Corporation"


def test_update_org_currency(admin_client):
    r = admin_client.patch(BASE, json={"currency": "EUR"})
    assert r.status_code == 200
    assert r.json()["currency"] == "EUR"


def test_update_org_currency_case_insensitive(admin_client):
    r = admin_client.patch(BASE, json={"currency": "gbp"})
    assert r.status_code == 200
    assert r.json()["currency"] == "GBP"


def test_update_org_partial(admin_client):
    """Updating name should not change currency."""
    admin_client.patch(BASE, json={"currency": "LKR"})
    r = admin_client.patch(BASE, json={"name": "New Name"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "New Name"
    assert data["currency"] == "LKR"


def test_update_org_unsupported_currency(admin_client):
    r = admin_client.patch(BASE, json={"currency": "XYZ"})
    assert r.status_code == 422


def test_update_org_blank_name(admin_client):
    r = admin_client.patch(BASE, json={"name": "   "})
    assert r.status_code == 422


def test_update_org_slug_not_accepted(admin_client):
    """Slug is not a valid update field — should be ignored."""
    r = admin_client.patch(BASE, json={"slug": "new-slug"})
    assert r.status_code == 200
    assert r.json()["slug"] == "acme-corp"  # unchanged


def test_update_org_sales_forbidden(sales_client):
    r = sales_client.patch(BASE, json={"name": "Hacked"})
    assert r.status_code == 403


def test_update_org_viewer_forbidden(viewer_client):
    r = viewer_client.patch(BASE, json={"name": "Hacked"})
    assert r.status_code == 403


def test_update_org_accountant_forbidden(accountant_client):
    r = accountant_client.patch(BASE, json={"currency": "EUR"})
    assert r.status_code == 403


def test_update_org_unauthenticated(anon_client):
    r = anon_client.patch(BASE, json={"name": "Hacked"})
    assert r.status_code == 401


def test_update_org_reflected_in_get(admin_client):
    admin_client.patch(BASE, json={"name": "Updated Corp", "currency": "GBP"})
    r = admin_client.get(BASE)
    assert r.json()["name"] == "Updated Corp"
    assert r.json()["currency"] == "GBP"
