"""Tests for /api/products — CRUD, soft delete, RBAC, tenant isolation."""
import pytest

BASE = "/api/products"

PRODUCT_PAYLOAD = {
    "name": "Widget A",
    "description": "A fine widget",
    "unit_price": "99.99",
    "currency": "USD",
    "is_global": True,
}


# ─── List ─────────────────────────────────────────────────────────────────────

def test_list_products_empty(admin_client):
    r = admin_client.get(f"{BASE}/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_products_all_roles(admin_client, sales_client, accountant_client, viewer_client, make_product):
    make_product()
    for tc in [sales_client, accountant_client, viewer_client]:
        r = tc.get(f"{BASE}/")
        assert r.status_code == 200
        assert len(r.json()) == 1


def test_list_products_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/")
    assert r.status_code == 401


def test_list_products_filter_global(admin_client, make_product):
    make_product(name="Global", is_global=True)
    make_product(name="Specific", is_global=False)
    r = admin_client.get(f"{BASE}/", params={"is_global": "true"})
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Global" in names
    assert "Specific" not in names


def test_list_products_filter_non_global(admin_client, make_product):
    make_product(name="Global", is_global=True)
    make_product(name="Specific", is_global=False)
    r = admin_client.get(f"{BASE}/", params={"is_global": "false"})
    names = [p["name"] for p in r.json()]
    assert "Specific" in names
    assert "Global" not in names


def test_list_products_tenant_isolation(admin_client, second_org_admin, make_product):
    make_product()
    r = second_org_admin.get(f"{BASE}/")
    assert r.json() == []


# ─── Create ───────────────────────────────────────────────────────────────────

def test_create_product_admin(admin_client):
    r = admin_client.post(f"{BASE}/", json=PRODUCT_PAYLOAD)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Widget A"
    assert data["currency"] == "USD"
    assert data["is_active"] is True


def test_create_product_sales(sales_client, admin_client):
    r = sales_client.post(f"{BASE}/", json=PRODUCT_PAYLOAD)
    assert r.status_code == 201


def test_create_product_viewer_forbidden(viewer_client):
    r = viewer_client.post(f"{BASE}/", json=PRODUCT_PAYLOAD)
    assert r.status_code == 403


def test_create_product_accountant_forbidden(accountant_client):
    r = accountant_client.post(f"{BASE}/", json=PRODUCT_PAYLOAD)
    assert r.status_code == 403


# ─── Get by ID ────────────────────────────────────────────────────────────────

def test_get_product_success(admin_client, make_product):
    product = make_product()
    r = admin_client.get(f"{BASE}/{product['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == product["id"]


def test_get_product_not_found(admin_client):
    r = admin_client.get(f"{BASE}/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404


def test_get_product_other_org_returns_404(second_org_admin, make_product):
    product = make_product()
    r = second_org_admin.get(f"{BASE}/{product['id']}")
    assert r.status_code == 404


# ─── Update ───────────────────────────────────────────────────────────────────

def test_update_product_name(admin_client, make_product):
    product = make_product()
    r = admin_client.patch(f"{BASE}/{product['id']}", json={"name": "Updated Widget"})
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Widget"


def test_update_product_price(admin_client, make_product):
    product = make_product()
    r = admin_client.patch(f"{BASE}/{product['id']}", json={"unit_price": "199.99"})
    assert r.status_code == 200
    assert float(r.json()["unit_price"]) == 199.99


def test_update_product_viewer_forbidden(viewer_client, make_product):
    product = make_product()
    r = viewer_client.patch(f"{BASE}/{product['id']}", json={"name": "Hacked"})
    assert r.status_code == 403


def test_update_product_not_found(admin_client):
    r = admin_client.patch(
        f"{BASE}/00000000-0000-0000-0000-000000000001",
        json={"name": "Ghost"},
    )
    assert r.status_code == 404


# ─── Soft Delete ──────────────────────────────────────────────────────────────

def test_delete_product_soft(admin_client, make_product):
    product = make_product()
    r = admin_client.delete(f"{BASE}/{product['id']}")
    assert r.status_code == 204


def test_deleted_product_not_in_list(admin_client, make_product):
    product = make_product()
    admin_client.delete(f"{BASE}/{product['id']}")
    products = admin_client.get(f"{BASE}/").json()
    ids = [p["id"] for p in products]
    assert product["id"] not in ids


def test_delete_product_viewer_forbidden(viewer_client, make_product):
    product = make_product()
    r = viewer_client.delete(f"{BASE}/{product['id']}")
    assert r.status_code == 403


def test_delete_product_not_found(admin_client):
    r = admin_client.delete(f"{BASE}/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404


# ─── Assigned clients ─────────────────────────────────────────────────────────

def test_get_assigned_clients(admin_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    admin_client.post(f"/api/clients/{client['id']}/assigned-products", json={"product_id": product["id"]})
    r = admin_client.get(f"{BASE}/{product['id']}/assigned-clients")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == client["id"]


def test_get_assigned_clients_empty(admin_client, make_product):
    product = make_product()
    r = admin_client.get(f"{BASE}/{product['id']}/assigned-clients")
    assert r.status_code == 200
    assert r.json() == []
