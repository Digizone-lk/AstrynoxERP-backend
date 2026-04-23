"""
chat_tools.py

Two responsibilities, kept in one file because they are tightly coupled:
  1. TOOL_DEFINITIONS  — the list of dicts we send to OpenAI so it knows what
                         tools exist and when to call them.
  2. Executor functions — the actual Python/SQL functions that run when the
                         model decides to call a tool.

Rule: executor functions never receive org_id from the model's inputs.
org_id always comes from the authenticated user's JWT (passed by the service
layer). This prevents any prompt-injection attack where a crafted message
tries to read another org's data.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.invoice import Invoice, InvoiceStatus
from app.models.organization import Organization


#Default Constant Values
MAX_DATE_RANGE_DAYS = 365
MAX_RESULTS = 50

# Pre-compute valid status values once so validators don't re-build the set on
# every call.
_VALID_STATUSES = {s.value for s in InvoiceStatus}

TOOL_DEFINITIONS = [

    # -----------------------------------------------------------------------
    # TOOL: get_invoices - for details
    # -----------------------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "get_invoices",
            "description": (
                "Get a list of invoices. "
                "Use this when the user asks to see, list, show, find or look up invoices. "
                "such as 'What is the duedate of INV-0001 invoice? ', 'Who created INV-0002 and INV-0004 invoices? ', 'Show me the last 5 invoices issued to Acme Corps. ', 'List out the overdue invoices from Acme so far. ' "
                "Do not use this for total amounts or revenue questions, use get_invoice_summary instead. "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_numbers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of invoice numbers to look up. "
                            "Each value must be in exact format  eg:-'INV-0001'. "
                            "Use this when the user mentions specific invoice numbers. "
                            "If multiple invoice numbers are mentioned, include all of them in the array."
                            ),
                    },
                    "client_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of client names to look up. "
                            "Each value can be in several formats  eg:- as full name: 'Acme Corps Pvt Ltd', as business name: 'Acme Corps', as short name: 'Acme'. "
                            "Use this when the user mentions specific client names. "
                            "If multiple client names are mentioned, include all of them in the array."
                            ),
                    },
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of status type to look up. "
                            "Valid status values are: 'draft', 'sent', 'paid', 'overdue', 'cancelled'."
                            "Use this when the user mentions status type. "
                            "If multiple status types are mentioned, include all of them in the array."
                        ),
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start of the date range in YYYY-MM-DD format (inclusive)."
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "End of the date range in YYYY-MM-DD format (inclusive). "
                            "Use today's date when the user says 'up to now' or 'so far'."
                        ),
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_invoice_summary - for calculations
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_invoice_summary",
            "description": (
                "Get total income for a given date range. "
                "Income is defined as the sum of totals of all PAID invoices "
                "within the range. Use this when the user asks about revenue, "
                "earnings, money received, or total income for any time period "
                "such as 'this month', 'last year', 'between two dates', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start of the date range in YYYY-MM-DD format (inclusive).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "End of the date range in YYYY-MM-DD format (inclusive). "
                            "Use today's date when the user says 'up to now' or 'so far'."
                        ),
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    }

]


#TOOL 01: Execute Function get_invoices
def get_invoices(
        db: Session,
        org_id,
        invoice_numbers: list[str] = None,
        client_names: list[str] = None,
        status: list[str] = None,
        start_date: str = None,
        end_date: str = None
        ) -> dict:

    start = None
    end = None

    try:
        if start_date and end_date:
            start = date.fromisoformat(start_date)
            end   = date.fromisoformat(end_date)
        elif start_date:
            start   = date.fromisoformat(start_date)
            end     = date.today()
        elif end_date:
            end = date.fromisoformat(end_date)
            start = end - timedelta(days=MAX_DATE_RANGE_DAYS)
        else:
            end = date.today()
            start = end - timedelta(days=MAX_DATE_RANGE_DAYS)

    except ValueError:
        return {"error": f"Invalid date format. Expected YYYY-MM-DD, got '{start_date}' / '{end_date}'."}

    if (end - start).days > MAX_DATE_RANGE_DAYS:
        return {"error": f"Date range exceeds maximum allowed {MAX_DATE_RANGE_DAYS} days."}

    # Validate status values before they reach the SQLAlchemy Enum binding.
    if status:
        invalid = [s for s in status if s not in _VALID_STATUSES]
        if invalid:
            return {
                "error": (
                    f"Invalid status value(s): {invalid}. "
                    f"Valid values are: {sorted(_VALID_STATUSES)}."
                )
            }

    query = (
            db.query(Invoice, Client.name)
            .join(Client, Invoice.client_id == Client.id)
            .filter(Invoice.org_id == org_id)
            .filter(Invoice.issue_date >= start)
            .filter(Invoice.issue_date <= end)
    )

    if invoice_numbers:
        query = query.filter(Invoice.invoice_number.in_(invoice_numbers))

    if client_names:
        query = query.filter(or_(*[Client.name.ilike(f"%{name}%") for name in client_names]))

    if status:
        query = query.filter(Invoice.status.in_(status))

    invoices = query.order_by(Invoice.issue_date.desc()).limit(MAX_RESULTS).all()

    results = []
    for invoice, client_name in invoices:
        results.append({
            "invoice_numbers": invoice.invoice_number,
            "client_names": client_name,
            "status": invoice.status.value,
            "issue_date": str(invoice.issue_date),
            "due_date": str(invoice.due_date) if invoice.due_date else None,
            "total": float(invoice.total),
            "currency": invoice.currency
        })
    return {"invoices": results}


#TOOL 02: Execute Function get_invoice_summary
def get_invoice_summary(
    db: Session,
    org_id,
    start_date: str,
    end_date: str,
) -> dict:

    try:
        start = date.fromisoformat(start_date)
        end   = date.fromisoformat(end_date)
    except ValueError:
        return {"error": f"Invalid date format. Expected YYYY-MM-DD, got '{start_date}' / '{end_date}'."}

    # Filter on paid_at (the date payment was actually received) rather than
    # issue_date, so income is attributed to the correct period.
    paid_date = func.date(Invoice.paid_at)

    total = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
            paid_date >= start,
            paid_date <= end,
        )
        .scalar()
    )

    count = (
        db.query(func.count(Invoice.id))
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
            paid_date >= start,
            paid_date <= end,
        )
        .scalar()
    )

    # Use the org's configured currency as the default rather than a hard-coded
    # value.  Fall back to "USD" only if the org record is unexpectedly missing.
    org = db.query(Organization).filter(Organization.id == org_id).first()
    default_currency = org.currency if org else "USD"

    currency_row = (
        db.query(Invoice.currency)
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
        )
        .order_by(Invoice.paid_at.desc())
        .first()
    )
    currency = currency_row[0] if currency_row else default_currency

    return {
        "total": float(Decimal(str(total))),
        "invoice_count": count,
        "currency": currency,
        "start_date": start_date,
        "end_date": end_date,
    }


# -------------------------- Dispatcher --------------------------- #
def execute_tool(tool_name: str, tool_parameters: dict, db: Session, org_id) -> dict:
    if tool_name == "get_invoices":
        return get_invoices(db, org_id, **tool_parameters)
    elif tool_name == "get_invoice_summary":
        return get_invoice_summary(db, org_id, **tool_parameters)
    else:
        return {"error": f"Unknown tool: {tool_name}"}
