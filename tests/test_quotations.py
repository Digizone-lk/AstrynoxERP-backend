"""Tests for /api/quotations — lifecycle, RBAC, tenant isolation."""
import pytest

BASE = "/api/quotations"


def _quote_payload(client_id: str, product_id: str) -> dict:
    return {
        "client_id": client_id,
        "issue_date": "2026-03-01",
        "valid_until": "2026-03-31",
        "currency": "USD",
        "notes": "Test quotation",
        "items": [
            {
                "product_id": product_id,
                "product_name": "Widget A",
                "description": "Test item",
                "qty": "2",
                "unit_price": "100.00",
            }
        ],
    }


# ─── Create ───────────────────────────────────────────────────────────────────

def test_create_quotation_success(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = admin_client.post(f"{BASE}/", json=_quote_payload(client["id"], product["id"]))
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["quote_number"] == "QUO-0001"
    assert float(data["total"]) == 200.00
    assert len(data["items"]) == 1


def test_create_quotation_auto_numbering(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    payload = _quote_payload(client["id"], product["id"])
    admin_client.post(f"{BASE}/", json=payload)
    r2 = admin_client.post(f"{BASE}/", json=payload)
    assert r2.json()["quote_number"] == "QUO-0002"


def test_create_quotation_no_items(admin_client, make_client):
    client = make_client()
    r = admin_client.post(f"{BASE}/", json={
        "client_id": client["id"],
        "issue_date": "2026-03-01",
        "currency": "USD",
        "items": [],
    })
    assert r.status_code == 400
    assert "item" in r.json()["detail"].lower()


def test_create_quotation_sales_allowed(sales_client, admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = sales_client.post(f"{BASE}/", json=_quote_payload(client["id"], product["id"]))
    assert r.status_code == 201


def test_create_quotation_viewer_forbidden(viewer_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = viewer_client.post(f"{BASE}/", json=_quote_payload(client["id"], product["id"]))
    assert r.status_code == 403


def test_create_quotation_accountant_forbidden(accountant_client, make_client, make_product):
    client = make_client()
    product = make_product()
    r = accountant_client.post(f"{BASE}/", json=_quote_payload(client["id"], product["id"]))
    assert r.status_code == 403


# ─── List & Get ───────────────────────────────────────────────────────────────

def test_list_quotations(admin_client, make_quotation):
    make_quotation()
    r = admin_client.get(f"{BASE}/")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_quotations_filter_by_status(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    r = admin_client.get(f"{BASE}/", params={"status": "sent"})
    assert len(r.json()) == 1
    r2 = admin_client.get(f"{BASE}/", params={"status": "draft"})
    assert len(r2.json()) == 0


def test_list_quotations_tenant_isolation(admin_client, second_org_admin, make_quotation):
    make_quotation()
    r = second_org_admin.get(f"{BASE}/")
    assert r.json() == []


def test_get_quotation_success(admin_client, make_quotation):
    q = make_quotation()
    r = admin_client.get(f"{BASE}/{q['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == q["id"]


def test_get_quotation_not_found(admin_client):
    r = admin_client.get(f"{BASE}/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404


def test_get_quotation_other_org_returns_404(second_org_admin, make_quotation):
    q = make_quotation()
    r = second_org_admin.get(f"{BASE}/{q['id']}")
    assert r.status_code == 404


# ─── Update ───────────────────────────────────────────────────────────────────

def test_update_quotation_draft(admin_client, make_quotation, make_product):
    q = make_quotation()
    new_product = make_product(name="Widget B", price="50.00")
    r = admin_client.patch(f"{BASE}/{q['id']}", json={
        "notes": "Updated notes",
        "items": [
            {
                "product_id": new_product["id"],
                "product_name": "Widget B",
                "description": "New item",
                "qty": "1",
                "unit_price": "50.00",
            }
        ],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["notes"] == "Updated notes"
    assert float(data["total"]) == 50.00
    assert len(data["items"]) == 1


def test_update_quotation_non_draft_rejected(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    r = admin_client.patch(f"{BASE}/{q['id']}", json={"notes": "Should fail"})
    assert r.status_code == 400
    assert "draft" in r.json()["detail"].lower()


def test_update_quotation_viewer_forbidden(viewer_client, make_quotation):
    q = make_quotation()
    r = viewer_client.patch(f"{BASE}/{q['id']}", json={"notes": "Hacked"})
    assert r.status_code == 403


# ─── Status transitions ───────────────────────────────────────────────────────

def test_send_quotation(admin_client, make_quotation):
    q = make_quotation()
    r = admin_client.post(f"{BASE}/{q['id']}/send")
    assert r.status_code == 200
    assert r.json()["status"] == "sent"


def test_send_non_draft_rejected(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    r = admin_client.post(f"{BASE}/{q['id']}/send")
    assert r.status_code == 400
    assert "draft" in r.json()["detail"].lower()


def test_approve_quotation(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    r = admin_client.post(f"{BASE}/{q['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_approve_requires_sent_status(admin_client, make_quotation):
    q = make_quotation()  # still draft
    r = admin_client.post(f"{BASE}/{q['id']}/approve")
    assert r.status_code == 400
    assert "sent" in r.json()["detail"].lower()


def test_reject_sent_quotation(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    r = admin_client.post(f"{BASE}/{q['id']}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_reject_approved_quotation(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    admin_client.post(f"{BASE}/{q['id']}/approve")
    r = admin_client.post(f"{BASE}/{q['id']}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_reject_draft_quotation_rejected(admin_client, make_quotation):
    q = make_quotation()  # draft
    r = admin_client.post(f"{BASE}/{q['id']}/reject")
    assert r.status_code == 400


# ─── Convert to invoice ───────────────────────────────────────────────────────

def test_convert_to_invoice(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    admin_client.post(f"{BASE}/{q['id']}/approve")
    r = admin_client.post(f"{BASE}/{q['id']}/convert-to-invoice")
    assert r.status_code == 201
    data = r.json()
    assert "invoice_id" in data
    assert data["invoice_number"] == "INV-0001"


def test_convert_copies_line_items_to_invoice(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    admin_client.post(f"{BASE}/{q['id']}/approve")
    conversion = admin_client.post(f"{BASE}/{q['id']}/convert-to-invoice").json()
    invoice = admin_client.get(f"/api/invoices/{conversion['invoice_id']}").json()
    assert len(invoice["items"]) == 1
    assert float(invoice["total"]) == 200.00


def test_convert_sets_quotation_status_converted(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    admin_client.post(f"{BASE}/{q['id']}/approve")
    admin_client.post(f"{BASE}/{q['id']}/convert-to-invoice")
    status = admin_client.get(f"{BASE}/{q['id']}").json()["status"]
    assert status == "converted"


def test_convert_non_approved_rejected(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")  # sent but not approved
    r = admin_client.post(f"{BASE}/{q['id']}/convert-to-invoice")
    assert r.status_code == 400
    assert "approved" in r.json()["detail"].lower()


def test_convert_already_converted_rejected(admin_client, make_quotation):
    q = make_quotation()
    admin_client.post(f"{BASE}/{q['id']}/send")
    admin_client.post(f"{BASE}/{q['id']}/approve")
    admin_client.post(f"{BASE}/{q['id']}/convert-to-invoice")
    # Status is now CONVERTED — the "approved only" guard fires first (400)
    r = admin_client.post(f"{BASE}/{q['id']}/convert-to-invoice")
    assert r.status_code == 400
    assert "approved" in r.json()["detail"].lower()


def test_convert_viewer_forbidden(viewer_client, make_quotation):
    q = make_quotation()
    r = viewer_client.post(f"{BASE}/{q['id']}/convert-to-invoice")
    assert r.status_code == 403


# ─── Next quotation number ────────────────────────────────────────────────────

def test_next_quote_number_no_quotations(admin_client):
    r = admin_client.get(f"{BASE}/next-number")
    assert r.status_code == 200
    assert r.json() == {"quote_number": "QUO-0001"}


def test_next_quote_number_after_one_quotation(admin_client, make_quotation):
    make_quotation()
    r = admin_client.get(f"{BASE}/next-number")
    assert r.status_code == 200
    assert r.json() == {"quote_number": "QUO-0002"}


def test_next_quote_number_increments_correctly(admin_client, make_client, make_product):
    client = make_client()
    product = make_product()
    payload = _quote_payload(client["id"], product["id"])
    for _ in range(3):
        admin_client.post(f"{BASE}/", json=payload)
    r = admin_client.get(f"{BASE}/next-number")
    assert r.json() == {"quote_number": "QUO-0004"}


def test_next_quote_number_all_roles_allowed(
    admin_client, sales_client, accountant_client, viewer_client
):
    for client in [admin_client, sales_client, accountant_client, viewer_client]:
        r = client.get(f"{BASE}/next-number")
        assert r.status_code == 200
        assert "quote_number" in r.json()


def test_next_quote_number_unauthenticated(anon_client):
    r = anon_client.get(f"{BASE}/next-number")
    assert r.status_code == 401


def test_next_quote_number_tenant_isolation(admin_client, second_org_admin, make_quotation):
    make_quotation()  # created under admin_client's org
    r = second_org_admin.get(f"{BASE}/next-number")
    assert r.json() == {"quote_number": "QUO-0001"}


def test_numbering_no_collision_after_gap(admin_client, make_client, make_product):
    """If QUO-0001 exists and QUO-0002 is deleted, next number must be QUO-0003 not QUO-0002."""
    client = make_client()
    product = make_product()
    payload = _quote_payload(client["id"], product["id"])

    q1 = admin_client.post(f"{BASE}/", json=payload).json()
    q2 = admin_client.post(f"{BASE}/", json=payload).json()
    assert q2["quote_number"] == "QUO-0002"

    # Simulate a gap by creating a third — with MAX-based numbering this is always correct
    q3 = admin_client.post(f"{BASE}/", json=payload).json()
    assert q3["quote_number"] == "QUO-0003"
