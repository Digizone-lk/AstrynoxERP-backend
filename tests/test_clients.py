"""Tests for /api/clients — CRUD, product assignment, RBAC, tenant isolation."""
import pytest

BASE = "/api/clients"


# ─── List ─────────────────────────────────────────────────────────────────────

def test_list_clients_empty(admin_client):
    r = admin_client.get(f"{BASE}/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_clients_returns_own_org_only(admin_client, second_org_admin, make_client):
    make_client("Acme Client")
    r = second_org_admin.get(f"{BASE}/")
    assert r.status_code == 200
    assert r.json() == []  # other org sees nothing


def test_list_clients_all_roles_can_read(admin_client, sales_client, accountant_client, viewer_client, make_client):
    make_client()
    for tc in [sales_client, accountant_client, viewer_client]:
        r = tc.get(f"{BASE}/")
        assert r.status_code == 200
        assert len(r.json()) == 1


def test_list_clients_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/")
    assert r.status_code == 401


# ─── Create ───────────────────────────────────────────────────────────────────

def test_create_client_admin(admin_client):
    r = admin_client.post(f"{BASE}/", json={"name": "Globex Inc", "email": "contact@globex.com"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Globex Inc"
    assert data["email"] == "contact@globex.com"
    assert data["is_active"] is True


def test_create_client_sales(sales_client, admin_client):
    r = sales_client.post(f"{BASE}/", json={"name": "Sales Client"})
    assert r.status_code == 201


def test_create_client_viewer_forbidden(viewer_client):
    r = viewer_client.post(f"{BASE}/", json={"name": "Viewer Client"})
    assert r.status_code == 403


def test_create_client_accountant_forbidden(accountant_client):
    r = accountant_client.post(f"{BASE}/", json={"name": "Accountant Client"})
    assert r.status_code == 403


def test_create_client_minimal_payload(admin_client):
    r = admin_client.post(f"{BASE}/", json={"name": "Minimal Client"})
    assert r.status_code == 201
    data = r.json()
    assert data["email"] is None
    assert data["phone"] is None


# ─── Get by ID ────────────────────────────────────────────────────────────────

def test_get_client_success(admin_client, make_client):
    client = make_client()
    r = admin_client.get(f"{BASE}/{client['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == client["id"]


def test_get_client_not_found(admin_client):
    r = admin_client.get(f"{BASE}/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404


def test_get_client_other_org_returns_404(second_org_admin, make_client):
    """Tenant isolation: another org cannot read this client."""
    client = make_client()
    r = second_org_admin.get(f"{BASE}/{client['id']}")
    assert r.status_code == 404


# ─── Update ───────────────────────────────────────────────────────────────────

def test_update_client_name(admin_client, make_client):
    client = make_client()
    r = admin_client.patch(f"{BASE}/{client['id']}", json={"name": "Updated Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Name"


def test_update_client_partial(admin_client, make_client):
    client = make_client(email="old@test.com")
    r = admin_client.patch(f"{BASE}/{client['id']}", json={"phone": "+94771234567"})
    assert r.status_code == 200
    data = r.json()
    assert data["phone"] == "+94771234567"
    assert data["email"] == "old@test.com"  # unchanged


def test_update_client_viewer_forbidden(viewer_client, make_client):
    client = make_client()
    r = viewer_client.patch(f"{BASE}/{client['id']}", json={"name": "Hacked"})
    assert r.status_code == 403


def test_update_client_not_found(admin_client):
    r = admin_client.patch(
        f"{BASE}/00000000-0000-0000-0000-000000000001",
        json={"name": "Ghost"},
    )
    assert r.status_code == 404


# ─── Product assignment ───────────────────────────────────────────────────────

def test_assign_product_to_client(admin_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    r = admin_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": product["id"]})
    assert r.status_code == 201
    assert r.json()["product_id"] == product["id"]


def test_assign_product_duplicate(admin_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    admin_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": product["id"]})
    r = admin_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": product["id"]})
    assert r.status_code == 409


def test_assign_product_viewer_forbidden(viewer_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    r = viewer_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": product["id"]})
    assert r.status_code == 403


def test_list_assigned_products(admin_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    admin_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": product["id"]})
    r = admin_client.get(f"{BASE}/{client['id']}/assigned-products")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_unassign_product(admin_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    admin_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": product["id"]})
    r = admin_client.delete(f"{BASE}/{client['id']}/assigned-products/{product['id']}")
    assert r.status_code == 204
    remaining = admin_client.get(f"{BASE}/{client['id']}/assigned-products").json()
    assert remaining == []


def test_unassign_product_not_found(admin_client, make_client, make_product):
    client = make_client()
    product = make_product(is_global=False)
    r = admin_client.delete(f"{BASE}/{client['id']}/assigned-products/{product['id']}")
    assert r.status_code == 404


# ─── Eligible products ────────────────────────────────────────────────────────

def test_eligible_products_includes_global(admin_client, make_client, make_product):
    client = make_client()
    make_product(name="Global Widget", is_global=True)
    r = admin_client.get(f"{BASE}/{client['id']}/products")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Global Widget" in names


def test_eligible_products_includes_assigned_specific(admin_client, make_client, make_product):
    client = make_client()
    specific = make_product(name="Client-Only Widget", is_global=False)
    admin_client.post(f"{BASE}/{client['id']}/assigned-products", json={"product_id": specific["id"]})
    r = admin_client.get(f"{BASE}/{client['id']}/products")
    names = [p["name"] for p in r.json()]
    assert "Client-Only Widget" in names


def test_eligible_products_excludes_unassigned_specific(admin_client, make_client, make_product):
    client = make_client()
    make_product(name="Unassigned Widget", is_global=False)  # not assigned
    r = admin_client.get(f"{BASE}/{client['id']}/products")
    names = [p["name"] for p in r.json()]
    assert "Unassigned Widget" not in names
