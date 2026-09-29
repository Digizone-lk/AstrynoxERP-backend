"""Postgres session-variable helper backing the org_units RLS policies.

Every platform table's RLS policy checks `current_setting('app.current_org_id', true)`.
Callers must set this for the current transaction before touching platform tables,
otherwise the policies see NULL and every row is filtered out (fail closed).

This is a no-op on SQLite (used by the IMS test suite / legacy tables), since SQLite
has no session GUCs and no RLS — platform tables are Postgres-only.
"""
import uuid
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


def set_tenant_context(db: Session | Connection, org_id: uuid.UUID | str) -> None:
    bind = db.get_bind() if isinstance(db, Session) else db
    if bind.dialect.name != "postgresql":
        return
    # Validate/normalize so this can never carry attacker-controlled SQL text.
    org_uuid = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
    db.execute(text(f"SET LOCAL app.current_org_id = '{org_uuid}'"))
