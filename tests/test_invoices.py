"""Tests for /api/invoices — lifecycle, RBAC, tenant isolation."""
import pytest

BASE = "/api/invoices"


def _invoice_payload(client_id: str, product_id: str) -> dict:
    return {
        "client_id": client_id,
        "issue_date": "2026-03-01",
        "due_date": "2026-03-31",
        "currency": "USD",
        "notes": "Test invoice",
        "items": [
            {
                "product_id": product_id,
                "product_name": "Widget A",
                "description": "Test item",
                "qty": "2",
                "unit_price": "150.00",
            }
        ],
    }


# ─── Create ───────────────────────────────────────────────────────────────────

def test_create_invoice_success(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = admin_client.post(f"{BASE}/", json=_invoice_payload(client["id"], product["id"]))
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["invoice_number"] == "INV-0001"
    assert float(data["total"]) == 300.00
    assert len(data["items"]) == 1


def test_create_invoice_auto_numbering(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    payload = _invoice_payload(client["id"], product["id"])
    admin_client.post(f"{BASE}/", json=payload)
    r2 = admin_client.post(f"{BASE}/", json=payload)
    assert r2.json()["invoice_number"] == "INV-0002"


def test_create_invoice_no_items_rejected(admin_client, make_client):
    client = make_client()
    r = admin_client.post(f"{BASE}/", json={
        "client_id": client["id"],
        "issue_date": "2026-03-01",
        "currency": "USD",
        "items": [],
    })
    assert r.status_code == 400
    assert "item" in r.json()["detail"].lower()


def test_create_invoice_sales_allowed(sales_client, admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = sales_client.post(f"{BASE}/", json=_invoice_payload(client["id"], product["id"]))
    assert r.status_code == 201


def test_create_invoice_viewer_forbidden(viewer_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = viewer_client.post(f"{BASE}/", json=_invoice_payload(client["id"], product["id"]))
    assert r.status_code == 403


def test_create_invoice_accountant_forbidden(accountant_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = accountant_client.post(f"{BASE}/", json=_invoice_payload(client["id"], product["id"]))
    assert r.status_code == 403


# ─── List & Get ───────────────────────────────────────────────────────────────

def test_list_invoices(admin_client, make_invoice):
    make_invoice()
    r = admin_client.get(f"{BASE}/")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_invoices_filter_by_status(admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = admin_client.get(f"{BASE}/", params={"status": "sent"})
    assert len(r.json()) == 1
    r2 = admin_client.get(f"{BASE}/", params={"status": "draft"})
    assert len(r2.json()) == 0


def test_list_invoices_tenant_isolation(admin_client, second_org_admin, make_invoice):
    make_invoice()
    r = second_org_admin.get(f"{BASE}/")
    assert r.json() == []


def test_get_invoice_success(admin_client, make_invoice):
    inv = make_invoice()
    r = admin_client.get(f"{BASE}/{inv['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == inv["id"]


def test_get_invoice_not_found(admin_client):
    r = admin_client.get(f"{BASE}/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404


def test_get_invoice_other_org_returns_404(second_org_admin, make_invoice):
    inv = make_invoice()
    r = second_org_admin.get(f"{BASE}/{inv['id']}")
    assert r.status_code == 404


# ─── Update ───────────────────────────────────────────────────────────────────

def test_update_invoice_draft(admin_client, make_invoice, make_product):
    inv = make_invoice()
    new_product = make_product(name="Widget B", price="75.00")
    r = admin_client.patch(f"{BASE}/{inv['id']}", json={
        "notes": "Updated notes",
        "items": [
            {
                "product_id": new_product["id"],
                "product_name": "Widget B",
                "description": "Updated item",
                "qty": "3",
                "unit_price": "75.00",
            }
        ],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["notes"] == "Updated notes"
    assert float(data["total"]) == 225.00
    assert len(data["items"]) == 1


def test_update_invoice_non_draft_rejected(admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = admin_client.patch(f"{BASE}/{inv['id']}", json={"notes": "Should fail"})
    assert r.status_code == 400
    assert "draft" in r.json()["detail"].lower()


def test_update_invoice_viewer_forbidden(viewer_client, make_invoice):
    inv = make_invoice()
    r = viewer_client.patch(f"{BASE}/{inv['id']}", json={"notes": "Hacked"})
    assert r.status_code == 403


# ─── Send ─────────────────────────────────────────────────────────────────────

def test_send_invoice(admin_client, make_invoice):
    inv = make_invoice()
    r = admin_client.post(f"{BASE}/{inv['id']}/send")
    assert r.status_code == 200
    assert r.json()["status"] == "sent"


def test_send_non_draft_rejected(admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = admin_client.post(f"{BASE}/{inv['id']}/send")
    assert r.status_code == 400


# ─── Mark paid ────────────────────────────────────────────────────────────────

def test_mark_paid_accountant(accountant_client, admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = accountant_client.post(f"{BASE}/{inv['id']}/mark-paid")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "paid"
    assert data["paid_at"] is not None


def test_mark_paid_admin(admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = admin_client.post(f"{BASE}/{inv['id']}/mark-paid")
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_mark_paid_sales_forbidden(sales_client, admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = sales_client.post(f"{BASE}/{inv['id']}/mark-paid")
    assert r.status_code == 403


def test_mark_paid_viewer_forbidden(viewer_client, admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = viewer_client.post(f"{BASE}/{inv['id']}/mark-paid")
    assert r.status_code == 403


def test_mark_paid_draft_invoice_rejected(admin_client, make_invoice):
    inv = make_invoice()  # draft, not sent
    r = admin_client.post(f"{BASE}/{inv['id']}/mark-paid")
    assert r.status_code == 400
    assert "sent" in r.json()["detail"].lower() or "overdue" in r.json()["detail"].lower()


def test_mark_paid_overdue_invoice(admin_client, make_invoice):
    """Overdue invoices can also be marked paid."""
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    admin_client.post(f"{BASE}/{inv['id']}/mark-overdue")
    r = admin_client.post(f"{BASE}/{inv['id']}/mark-paid")
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


# ─── Mark overdue ─────────────────────────────────────────────────────────────

def test_mark_overdue_accountant(accountant_client, admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = accountant_client.post(f"{BASE}/{inv['id']}/mark-overdue")
    assert r.status_code == 200
    assert r.json()["status"] == "overdue"


def test_mark_overdue_sales_forbidden(sales_client, admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = sales_client.post(f"{BASE}/{inv['id']}/mark-overdue")
    assert r.status_code == 403


def test_mark_overdue_draft_rejected(admin_client, make_invoice):
    inv = make_invoice()  # draft
    r = admin_client.post(f"{BASE}/{inv['id']}/mark-overdue")
    assert r.status_code == 400
    assert "sent" in r.json()["detail"].lower()


# ─── Cancel ───────────────────────────────────────────────────────────────────

def test_cancel_draft_invoice(admin_client, make_invoice):
    inv = make_invoice()
    r = admin_client.post(f"{BASE}/{inv['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_sent_invoice(admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    r = admin_client.post(f"{BASE}/{inv['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_paid_invoice_rejected(admin_client, make_invoice):
    inv = make_invoice()
    admin_client.post(f"{BASE}/{inv['id']}/send")
    admin_client.post(f"{BASE}/{inv['id']}/mark-paid")
    r = admin_client.post(f"{BASE}/{inv['id']}/cancel")
    assert r.status_code == 400
    assert "paid" in r.json()["detail"].lower()


def test_cancel_viewer_forbidden(viewer_client, make_invoice):
    inv = make_invoice()
    r = viewer_client.post(f"{BASE}/{inv['id']}/cancel")
    assert r.status_code == 403


# ─── Next invoice number ──────────────────────────────────────────────────────

def test_next_invoice_number_no_invoices(admin_client):
    r = admin_client.get(f"{BASE}/next-number")
    assert r.status_code == 200
    assert r.json() == {"invoice_number": "INV-0001"}


def test_next_invoice_number_after_one_invoice(admin_client, make_invoice):
    make_invoice()
    r = admin_client.get(f"{BASE}/next-number")
    assert r.status_code == 200
    assert r.json() == {"invoice_number": "INV-0002"}


def test_next_invoice_number_increments_correctly(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    payload = _invoice_payload(client["id"], product["id"])
    for _ in range(3):
        admin_client.post(f"{BASE}/", json=payload)
    r = admin_client.get(f"{BASE}/next-number")
    assert r.json() == {"invoice_number": "INV-0004"}


def test_next_invoice_number_all_roles_allowed(
    admin_client, sales_client, accountant_client, viewer_client
):
    for client in [admin_client, sales_client, accountant_client, viewer_client]:
        r = client.get(f"{BASE}/next-number")
        assert r.status_code == 200
        assert "invoice_number" in r.json()


def test_next_invoice_number_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/next-number")
    assert r.status_code == 401


def test_next_invoice_number_tenant_isolation(admin_client, second_org_admin, make_invoice):
    make_invoice()  # created under admin_client's org
    r = second_org_admin.get(f"{BASE}/next-number")
    assert r.json() == {"invoice_number": "INV-0001"}


# ─── Pagination ───────────────────────────────────────────────────────────────

def test_list_invoices_pagination(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    payload = _invoice_payload(client["id"], product["id"])
    for _ in range(5):
        admin_client.post(f"{BASE}/", json=payload)

    r = admin_client.get(f"{BASE}/", params={"limit": 3, "skip": 0})
    assert len(r.json()) == 3

    r2 = admin_client.get(f"{BASE}/", params={"limit": 3, "skip": 3})
    assert len(r2.json()) == 2
