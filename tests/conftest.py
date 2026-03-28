"""
Shared fixtures for the BillFlow test suite.

Database strategy: SQLite (in-memory via shared cache) — no PostgreSQL needed.
The postgresql.UUID type gracefully degrades to CHAR(32) on SQLite.
"""
import os

# Must be set BEFORE any app imports so config.py reads these values
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_billflow.db")
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-do-not-use-in-production")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db

# Import all models so Base.metadata is fully populated
import app.models.organization  # noqa
import app.models.user          # noqa
import app.models.client        # noqa
import app.models.product       # noqa
import app.models.client_product  # noqa
import app.models.quotation     # noqa
import app.models.invoice       # noqa
import app.models.audit_log     # noqa
import app.models.user_session  # noqa

from app.main import app  # import after env vars are set

TEST_DB_URL = "sqlite:///./test_billflow.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ─── Schema-level setup (once per session) ────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def mock_cloudinary():
    """Mock Cloudinary so avatar tests don't need real credentials."""
    fake_result = {"secure_url": "https://res.cloudinary.com/test/image/upload/avatars/test.jpg"}
    with patch("cloudinary.uploader.upload", return_value=fake_result), \
         patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
        yield


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    import os as _os
    try:
        if _os.path.exists("./test_billflow.db"):
            _os.remove("./test_billflow.db")
    except OSError:
        pass  # Windows: file still locked; cleaned up on next run


# ─── Table truncation between tests ──────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    yield
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


# ─── Payload helpers ──────────────────────────────────────────────────────────

ADMIN_REG = {
    "org_name": "Acme Corp",
    "org_slug": "acme-corp",
    "currency": "USD",
    "full_name": "Admin User",
    "email": "admin@acme.com",
    "password": "Secret123!",
}


def _register_org(org_slug="acme-corp", email="admin@acme.com"):
    """Register a new org and return an authenticated TestClient."""
    tc = TestClient(app)
    r = tc.post("/api/auth/register", json={
        **ADMIN_REG,
        "org_slug": org_slug,
        "email": email,
    })
    assert r.status_code == 201, r.text
    return tc


def _login(email: str, password: str) -> TestClient:
    """Login and return an authenticated TestClient."""
    tc = TestClient(app)
    r = tc.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return tc


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_client():
    """Authenticated TestClient as super_admin."""
    return _register_org()


@pytest.fixture
def second_org_admin():
    """Authenticated TestClient for a DIFFERENT org (for tenant isolation tests)."""
    return _register_org(org_slug="other-org", email="admin@other.com")


@pytest.fixture
def sales_client(admin_client):
    """Authenticated TestClient as a sales user in the same org as admin_client."""
    admin_client.post("/api/users/", json={
        "email": "sales@acme.com",
        "full_name": "Sales User",
        "password": "Secret123!",
        "role": "sales",
    })
    return _login("sales@acme.com", "Secret123!")


@pytest.fixture
def accountant_client(admin_client):
    """Authenticated TestClient as an accountant in the same org."""
    admin_client.post("/api/users/", json={
        "email": "accountant@acme.com",
        "full_name": "Accountant User",
        "password": "Secret123!",
        "role": "accountant",
    })
    return _login("accountant@acme.com", "Secret123!")


@pytest.fixture
def viewer_client(admin_client):
    """Authenticated TestClient as a viewer in the same org."""
    admin_client.post("/api/users/", json={
        "email": "viewer@acme.com",
        "full_name": "Viewer User",
        "password": "Secret123!",
        "role": "viewer",
    })
    return _login("viewer@acme.com", "Secret123!")


@pytest.fixture
def anon_client():
    """Unauthenticated TestClient."""
    return TestClient(app)


# ─── Domain object factories ──────────────────────────────────────────────────

@pytest.fixture
def make_client(admin_client):
    """Factory: creates a Client record and returns its JSON."""
    def _make(name="Globex Inc", email="contact@globex.com"):
        r = admin_client.post("/api/clients/", json={"name": name, "email": email})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture
def make_product(admin_client):
    """Factory: creates a Product record and returns its JSON."""
    def _make(name="Widget A", price="100.00", is_global=True):
        r = admin_client.post("/api/products/", json={
            "name": name,
            "description": "Test product",
            "unit_price": price,
            "currency": "USD",
            "is_global": is_global,
        })
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture
def make_quotation(admin_client, make_client, make_product):
    """Factory: creates a Quotation and returns its JSON."""
    def _make():
        client = make_client()
        product = make_product()
        r = admin_client.post("/api/quotations/", json={
            "client_id": client["id"],
            "issue_date": "2026-03-01",
            "valid_until": "2026-03-31",
            "currency": "USD",
            "notes": "Test quotation",
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "description": "Test item",
                    "qty": "2",
                    "unit_price": "100.00",
                }
            ],
        })
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture
def make_invoice(admin_client, make_client, make_product):
    """Factory: creates an Invoice directly and returns its JSON."""
    def _make():
        client = make_client()
        product = make_product()
        r = admin_client.post("/api/invoices/", json={
            "client_id": client["id"],
            "issue_date": "2026-03-01",
            "due_date": "2026-03-31",
            "currency": "USD",
            "notes": "Test invoice",
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "description": "Test item",
                    "qty": "2",
                    "unit_price": "150.00",
                }
            ],
        })
        assert r.status_code == 201, r.text
        return r.json()
    return _make
