"""
tools.py

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

from sqlalchemy import func, or_, extract, case
from sqlalchemy.orm import Session

from app.modules.ims.models.client import Client
from app.modules.ims.models.invoice import Invoice, InvoiceStatus
from app.modules.ims.models.product import Product
from app.modules.ims.models.quotation import Quotation, QuotationStatus
from app.modules.ims.models.organization import Organization


# Default Constant Values
MAX_DATE_RANGE_DAYS = 365
MAX_RESULTS = 50

# Pre-compute valid status values once so validators don't re-build the set on
# every call.
_VALID_INVOICE_STATUSES = {s.value for s in InvoiceStatus}
_VALID_QUOTATION_STATUSES = {s.value for s in QuotationStatus}

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
                "Such as 'What is the due date of INV-0001?', 'Show me the last 5 invoices issued to Acme Corp.', 'List the overdue invoices from Acme so far.' "
                "Do not use this for total amounts or revenue questions — use get_invoice_summary instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_numbers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of invoice numbers to look up. "
                            "Each value must be in exact format e.g. 'INV-0001'. "
                            "Use when the user mentions specific invoice numbers."
                        ),
                    },
                    "client_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of client names to filter by. "
                            "Partial names are accepted e.g. 'Acme' matches 'Acme Corp Pvt Ltd'."
                        ),
                    },
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of statuses to filter by. "
                            "Valid values: 'draft', 'sent', 'paid', 'overdue', 'cancelled'."
                        ),
                    },
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
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_invoice_summary - aggregate revenue stats
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_invoice_summary",
            "description": (
                "Get total income for a given date range. "
                "Income is defined as the sum of totals of all PAID invoices within the range. "
                "Use this when the user asks about revenue, earnings, money received, or total income "
                "for any time period such as 'this month', 'last year', 'between two dates', etc."
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
    },

    # -----------------------------------------------------------------------
    # TOOL: get_outstanding_amount - total unpaid receivables
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_outstanding_amount",
            "description": (
                "Get the total outstanding (unpaid) amount across all invoices that have been sent or are overdue. "
                "Use this when the user asks 'what is outstanding?', 'how much do clients owe?', "
                "'what are total receivables?', or 'how much unpaid money is there?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_overdue_invoices - list overdue invoices
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_overdue_invoices",
            "description": (
                "List invoices that are overdue. "
                "Use this when the user asks 'which invoices are overdue?', "
                "'show me late payments', or 'what is past due?'. "
                "Returns invoice details including how many days overdue each one is."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of overdue invoices to return. Defaults to 20.",
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_quotations - list quotations
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_quotations",
            "description": (
                "Get a list of quotations/quotes. "
                "Use this when the user asks to see, list, find, or look up quotations. "
                "Such as 'Show me all sent quotes', 'List quotations for Acme this month', "
                "'Which quotes are pending approval?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of statuses to filter by. "
                            "Valid values: 'draft', 'sent', 'approved', 'rejected', 'converted'."
                        ),
                    },
                    "client_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of client names to filter by. Partial names accepted.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start of the date range in YYYY-MM-DD format (inclusive).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End of the date range in YYYY-MM-DD format (inclusive).",
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_quotation_summary - aggregate quotation stats
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_quotation_summary",
            "description": (
                "Get count and total value of quotations grouped by status. "
                "Use this when the user asks 'how many quotes were sent this month?', "
                "'what is the total value of approved quotations?', or "
                "'give me a summary of our pipeline'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Filter summary to specific statuses. "
                            "Valid values: 'draft', 'sent', 'approved', 'rejected', 'converted'. "
                            "Omit to include all statuses."
                        ),
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start of the date range in YYYY-MM-DD format (inclusive).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End of the date range in YYYY-MM-DD format (inclusive).",
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_client_summary - per-client financial stats
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_client_summary",
            "description": (
                "Get total invoiced amount, total paid, and outstanding balance for a specific client. "
                "Use this when the user asks 'how much has Acme paid us?', "
                "'what does TechCorp owe?', or 'give me Acme's account summary'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client. Partial names are accepted.",
                    },
                },
                "required": ["client_name"],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_top_clients - clients ranked by revenue
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_top_clients",
            "description": (
                "Get clients ranked by total amount paid. "
                "Use this when the user asks 'who are our best clients?', "
                "'which clients bring the most revenue?', or 'top 5 clients by sales'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of top clients to return. Defaults to 10.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start of the date range in YYYY-MM-DD format (inclusive).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End of the date range in YYYY-MM-DD format (inclusive).",
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_clients - list clients
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_clients",
            "description": (
                "Get a list of clients. "
                "Use this when the user asks to see, search, or list clients. "
                "Such as 'show me all active clients', 'find a client named Acme', "
                "'how many clients do we have?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Search term to filter clients by name, email, or contact person.",
                    },
                    "is_active": {
                        "type": "boolean",
                        "description": "Filter by active (true) or inactive (false) clients. Omit to return all.",
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_products - list products
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_products",
            "description": (
                "Get a list of products or services offered. "
                "Use this when the user asks to see, search, or list products. "
                "Such as 'what products do we sell?', 'find a product called Web Design', "
                "'show me all active services'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Search term to filter products by name or description.",
                    },
                    "is_active": {
                        "type": "boolean",
                        "description": "Filter by active (true) or inactive (false) products. Omit to return all.",
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_revenue_trend - monthly revenue for trend/prediction analysis
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_revenue_trend",
            "description": (
                "Get month-by-month revenue breakdown for trend analysis and forecasting. "
                "Use this when the user asks about revenue trends, growth, predictions, "
                "or forecasts such as 'how is revenue trending?', 'predict next month revenue', "
                "'are sales growing?', 'what will we earn next quarter?'. "
                "Returns monthly totals so you can identify patterns and project future earnings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "integer",
                        "description": (
                            "Number of past months to include. Defaults to 12. "
                            "Use more months (e.g. 24) for longer-term trend predictions."
                        ),
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_cash_flow_forecast - expected inflows from outstanding invoices
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_cash_flow_forecast",
            "description": (
                "Get a forecast of expected cash inflows from outstanding invoices grouped by due date. "
                "Use this when the user asks 'what cash is coming in?', 'when will we get paid?', "
                "'forecast cash flow for next month', or 'what payments are expected soon?'. "
                "Returns sent and overdue invoices grouped by due date bucket."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": (
                            "Number of days into the future to include in the forecast. "
                            "Defaults to 90. Also includes already-overdue invoices."
                        ),
                    },
                },
                "required": [],
            },
        },
    },

    # -----------------------------------------------------------------------
    # TOOL: get_client_payment_behavior - avg payment time per client
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_client_payment_behavior",
            "description": (
                "Analyse how quickly each client pays their invoices. "
                "Use this when the user asks 'which clients pay on time?', "
                "'who are the slow payers?', 'what is Acme's average payment time?', "
                "or 'predict when TechCorp will pay'. "
                "Returns average days-to-pay and late payment rate per client."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": (
                            "Filter to a specific client. "
                            "Omit to get behaviour data for all clients."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of clients to return. Defaults to 20.",
                    },
                },
                "required": [],
            },
        },
    },

]


# ═══════════════════════════════════════════════════════════════════════════════
# Executor helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_dates(start_date: str | None, end_date: str | None, default_days: int = MAX_DATE_RANGE_DAYS):
    """Parse and validate date strings. Returns (start, end, error_dict | None)."""
    try:
        if start_date and end_date:
            start = date.fromisoformat(start_date)
            end   = date.fromisoformat(end_date)
        elif start_date:
            start = date.fromisoformat(start_date)
            end   = date.today()
        elif end_date:
            end   = date.fromisoformat(end_date)
            start = end - timedelta(days=default_days)
        else:
            end   = date.today()
            start = end - timedelta(days=default_days)
    except ValueError:
        return None, None, {"error": f"Invalid date format. Expected YYYY-MM-DD, got '{start_date}' / '{end_date}'."}

    if (end - start).days > MAX_DATE_RANGE_DAYS:
        return None, None, {"error": f"Date range exceeds maximum allowed {MAX_DATE_RANGE_DAYS} days."}

    return start, end, None


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 01: get_invoices
# ═══════════════════════════════════════════════════════════════════════════════
def get_invoices(
    db: Session,
    org_id,
    invoice_numbers: list[str] = None,
    client_names: list[str] = None,
    status: list[str] = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:

    start, end, err = _parse_dates(start_date, end_date)
    if err:
        return err

    if status:
        invalid = [s for s in status if s not in _VALID_INVOICE_STATUSES]
        if invalid:
            return {"error": f"Invalid status value(s): {invalid}. Valid values are: {sorted(_VALID_INVOICE_STATUSES)}."}

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
        query = query.filter(or_(*[Client.name.ilike(f"%{n}%") for n in client_names]))
    if status:
        query = query.filter(Invoice.status.in_(status))

    rows = query.order_by(Invoice.issue_date.desc()).limit(MAX_RESULTS).all()

    return {
        "invoices": [
            {
                "invoice_number": inv.invoice_number,
                "client_name":    client_name,
                "status":         inv.status.value,
                "issue_date":     str(inv.issue_date),
                "due_date":       str(inv.due_date) if inv.due_date else None,
                "total":          float(inv.total),
                "currency":       inv.currency,
            }
            for inv, client_name in rows
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 02: get_invoice_summary
# ═══════════════════════════════════════════════════════════════════════════════
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

    paid_date = func.date(Invoice.paid_at)
    base_filter = [
        Invoice.org_id == org_id,
        Invoice.status == InvoiceStatus.PAID,
        Invoice.paid_at.isnot(None),
        paid_date >= start,
        paid_date <= end,
    ]

    total = db.query(func.coalesce(func.sum(Invoice.total), 0)).filter(*base_filter).scalar()
    count = db.query(func.count(Invoice.id)).filter(*base_filter).scalar()

    org = db.query(Organization).filter(Organization.id == org_id).first()
    default_currency = org.currency if org else "USD"

    currency_row = (
        db.query(Invoice.currency)
        .filter(Invoice.org_id == org_id, Invoice.status == InvoiceStatus.PAID)
        .order_by(Invoice.paid_at.desc())
        .first()
    )
    currency = currency_row[0] if currency_row else default_currency

    return {
        "total":         float(Decimal(str(total))),
        "invoice_count": count,
        "currency":      currency,
        "start_date":    start_date,
        "end_date":      end_date,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 03: get_outstanding_amount
# ═══════════════════════════════════════════════════════════════════════════════
def get_outstanding_amount(db: Session, org_id) -> dict:
    unpaid_statuses = [InvoiceStatus.SENT, InvoiceStatus.OVERDUE]

    total = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(Invoice.org_id == org_id, Invoice.status.in_(unpaid_statuses))
        .scalar()
    )
    count = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.org_id == org_id, Invoice.status.in_(unpaid_statuses))
        .scalar()
    )
    overdue_total = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(Invoice.org_id == org_id, Invoice.status == InvoiceStatus.OVERDUE)
        .scalar()
    )

    org = db.query(Organization).filter(Organization.id == org_id).first()
    currency = org.currency if org else "USD"

    return {
        "outstanding_total":  float(Decimal(str(total))),
        "overdue_total":      float(Decimal(str(overdue_total))),
        "invoice_count":      count,
        "currency":           currency,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 04: get_overdue_invoices
# ═══════════════════════════════════════════════════════════════════════════════
def get_overdue_invoices(db: Session, org_id, limit: int = 20) -> dict:
    limit = min(int(limit), MAX_RESULTS)
    today = date.today()

    rows = (
        db.query(Invoice, Client.name)
        .join(Client, Invoice.client_id == Client.id)
        .filter(Invoice.org_id == org_id, Invoice.status == InvoiceStatus.OVERDUE)
        .order_by(Invoice.due_date.asc())
        .limit(limit)
        .all()
    )

    results = []
    for inv, client_name in rows:
        days_overdue = (today - inv.due_date).days if inv.due_date else None
        results.append({
            "invoice_number": inv.invoice_number,
            "client_name":    client_name,
            "due_date":       str(inv.due_date) if inv.due_date else None,
            "days_overdue":   days_overdue,
            "total":          float(inv.total),
            "currency":       inv.currency,
        })

    return {"overdue_invoices": results, "count": len(results)}


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 05: get_quotations
# ═══════════════════════════════════════════════════════════════════════════════
def get_quotations(
    db: Session,
    org_id,
    status: list[str] = None,
    client_names: list[str] = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:

    start, end, err = _parse_dates(start_date, end_date)
    if err:
        return err

    if status:
        invalid = [s for s in status if s not in _VALID_QUOTATION_STATUSES]
        if invalid:
            return {"error": f"Invalid status value(s): {invalid}. Valid values are: {sorted(_VALID_QUOTATION_STATUSES)}."}

    query = (
        db.query(Quotation, Client.name)
        .join(Client, Quotation.client_id == Client.id)
        .filter(Quotation.org_id == org_id)
        .filter(Quotation.issue_date >= start)
        .filter(Quotation.issue_date <= end)
    )

    if client_names:
        query = query.filter(or_(*[Client.name.ilike(f"%{n}%") for n in client_names]))
    if status:
        query = query.filter(Quotation.status.in_(status))

    rows = query.order_by(Quotation.issue_date.desc()).limit(MAX_RESULTS).all()

    return {
        "quotations": [
            {
                "quote_number":  q.quote_number,
                "client_name":   client_name,
                "status":        q.status.value,
                "issue_date":    str(q.issue_date),
                "valid_until":   str(q.valid_until) if q.valid_until else None,
                "total":         float(q.total),
                "currency":      q.currency,
            }
            for q, client_name in rows
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 06: get_quotation_summary
# ═══════════════════════════════════════════════════════════════════════════════
def get_quotation_summary(
    db: Session,
    org_id,
    status: list[str] = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:

    start, end, err = _parse_dates(start_date, end_date)
    if err:
        return err

    if status:
        invalid = [s for s in status if s not in _VALID_QUOTATION_STATUSES]
        if invalid:
            return {"error": f"Invalid status value(s): {invalid}. Valid values are: {sorted(_VALID_QUOTATION_STATUSES)}."}

    query = (
        db.query(
            Quotation.status,
            func.count(Quotation.id).label("count"),
            func.coalesce(func.sum(Quotation.total), 0).label("total"),
        )
        .filter(Quotation.org_id == org_id)
        .filter(Quotation.issue_date >= start)
        .filter(Quotation.issue_date <= end)
        .group_by(Quotation.status)
    )

    if status:
        query = query.filter(Quotation.status.in_(status))

    rows = query.all()

    return {
        "summary": [
            {
                "status": row.status.value,
                "count":  row.count,
                "total":  float(row.total),
            }
            for row in rows
        ],
        "start_date": str(start),
        "end_date":   str(end),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 07: get_client_summary
# ═══════════════════════════════════════════════════════════════════════════════
def get_client_summary(db: Session, org_id, client_name: str) -> dict:
    client = (
        db.query(Client)
        .filter(Client.org_id == org_id, Client.name.ilike(f"%{client_name}%"))
        .first()
    )
    if not client:
        return {"error": f"No client found matching '{client_name}'."}

    total_invoiced = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(
            Invoice.org_id == org_id,
            Invoice.client_id == client.id,
            Invoice.status.notin_([InvoiceStatus.CANCELLED, InvoiceStatus.DRAFT]),
        )
        .scalar()
    )
    total_paid = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(
            Invoice.org_id == org_id,
            Invoice.client_id == client.id,
            Invoice.status == InvoiceStatus.PAID,
        )
        .scalar()
    )
    outstanding = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(
            Invoice.org_id == org_id,
            Invoice.client_id == client.id,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]),
        )
        .scalar()
    )
    invoice_count = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.org_id == org_id, Invoice.client_id == client.id)
        .scalar()
    )

    org = db.query(Organization).filter(Organization.id == org_id).first()
    currency = org.currency if org else "USD"

    return {
        "client_name":     client.name,
        "email":           client.email,
        "is_active":       client.is_active,
        "total_invoiced":  float(Decimal(str(total_invoiced))),
        "total_paid":      float(Decimal(str(total_paid))),
        "outstanding":     float(Decimal(str(outstanding))),
        "invoice_count":   invoice_count,
        "currency":        currency,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 08: get_top_clients
# ═══════════════════════════════════════════════════════════════════════════════
def get_top_clients(
    db: Session,
    org_id,
    limit: int = 10,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    limit = min(int(limit), MAX_RESULTS)

    filters = [
        Invoice.org_id == org_id,
        Invoice.status == InvoiceStatus.PAID,
    ]

    if start_date or end_date:
        start, end, err = _parse_dates(start_date, end_date)
        if err:
            return err
        paid_date = func.date(Invoice.paid_at)
        filters += [Invoice.paid_at.isnot(None), paid_date >= start, paid_date <= end]

    rows = (
        db.query(
            Client.name,
            Client.email,
            func.coalesce(func.sum(Invoice.total), 0).label("total_paid"),
            func.count(Invoice.id).label("invoice_count"),
        )
        .join(Invoice, Invoice.client_id == Client.id)
        .filter(*filters)
        .group_by(Client.id, Client.name, Client.email)
        .order_by(func.sum(Invoice.total).desc())
        .limit(limit)
        .all()
    )

    org = db.query(Organization).filter(Organization.id == org_id).first()
    currency = org.currency if org else "USD"

    return {
        "top_clients": [
            {
                "client_name":   row.name,
                "email":         row.email,
                "total_paid":    float(Decimal(str(row.total_paid))),
                "invoice_count": row.invoice_count,
            }
            for row in rows
        ],
        "currency": currency,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 09: get_clients
# ═══════════════════════════════════════════════════════════════════════════════
def get_clients(
    db: Session,
    org_id,
    search: str = None,
    is_active: bool = None,
) -> dict:
    query = db.query(Client).filter(Client.org_id == org_id)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Client.name.ilike(pattern),
                Client.email.ilike(pattern),
                Client.contact_person.ilike(pattern),
            )
        )
    if is_active is not None:
        query = query.filter(Client.is_active == is_active)

    clients = query.order_by(Client.name.asc()).limit(MAX_RESULTS).all()

    return {
        "clients": [
            {
                "name":           c.name,
                "email":          c.email,
                "phone":          c.phone,
                "contact_person": c.contact_person,
                "is_active":      c.is_active,
            }
            for c in clients
        ],
        "count": len(clients),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 10: get_products
# ═══════════════════════════════════════════════════════════════════════════════
def get_products(
    db: Session,
    org_id,
    search: str = None,
    is_active: bool = None,
) -> dict:
    query = db.query(Product).filter(Product.org_id == org_id)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(pattern),
                Product.description.ilike(pattern),
            )
        )
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)

    products = query.order_by(Product.name.asc()).limit(MAX_RESULTS).all()

    return {
        "products": [
            {
                "name":        p.name,
                "description": p.description,
                "unit_price":  float(p.unit_price),
                "unit":        p.unit,
                "currency":    p.currency,
                "is_active":   p.is_active,
            }
            for p in products
        ],
        "count": len(products),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 11: get_revenue_trend (prediction support)
# ═══════════════════════════════════════════════════════════════════════════════
def get_revenue_trend(db: Session, org_id, months: int = 12) -> dict:
    months = min(max(int(months), 1), 24)
    today  = date.today()
    start  = date(today.year, today.month, 1) - timedelta(days=30 * (months - 1))
    # Normalise to first of month
    start  = date(start.year, start.month, 1)

    paid_date = func.date(Invoice.paid_at)

    rows = (
        db.query(
            extract("year",  Invoice.paid_at).label("year"),
            extract("month", Invoice.paid_at).label("month"),
            func.coalesce(func.sum(Invoice.total), 0).label("revenue"),
            func.count(Invoice.id).label("invoice_count"),
        )
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
            paid_date >= start,
            paid_date <= today,
        )
        .group_by("year", "month")
        .order_by("year", "month")
        .all()
    )

    org = db.query(Organization).filter(Organization.id == org_id).first()
    currency = org.currency if org else "USD"

    monthly = [
        {
            "period":        f"{int(row.year):04d}-{int(row.month):02d}",
            "revenue":       float(Decimal(str(row.revenue))),
            "invoice_count": row.invoice_count,
        }
        for row in rows
    ]

    # Include months with zero revenue so the model can see gaps.
    # Build a full month list and merge.
    month_map = {m["period"]: m for m in monthly}
    full = []
    cur = start
    while cur <= today:
        key = f"{cur.year:04d}-{cur.month:02d}"
        full.append(month_map.get(key, {"period": key, "revenue": 0.0, "invoice_count": 0}))
        # Advance to next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    return {
        "monthly_revenue": full,
        "currency":        currency,
        "months_included": len(full),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 12: get_cash_flow_forecast (prediction support)
# ═══════════════════════════════════════════════════════════════════════════════
def get_cash_flow_forecast(db: Session, org_id, days_ahead: int = 90) -> dict:
    days_ahead = min(max(int(days_ahead), 1), 365)
    today      = date.today()
    future_end = today + timedelta(days=days_ahead)

    rows = (
        db.query(Invoice, Client.name)
        .join(Client, Invoice.client_id == Client.id)
        .filter(
            Invoice.org_id == org_id,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]),
        )
        .order_by(Invoice.due_date.asc())
        .all()
    )

    overdue_bucket    = []
    due_soon_bucket   = []   # within 30 days
    due_later_bucket  = []   # 31–days_ahead days

    for inv, client_name in rows:
        entry = {
            "invoice_number": inv.invoice_number,
            "client_name":    client_name,
            "due_date":       str(inv.due_date) if inv.due_date else None,
            "total":          float(inv.total),
            "status":         inv.status.value,
            "currency":       inv.currency,
        }
        if inv.due_date is None or inv.due_date < today:
            entry["days_overdue"] = (today - inv.due_date).days if inv.due_date else None
            overdue_bucket.append(entry)
        elif inv.due_date <= today + timedelta(days=30):
            entry["days_until_due"] = (inv.due_date - today).days
            due_soon_bucket.append(entry)
        elif inv.due_date <= future_end:
            entry["days_until_due"] = (inv.due_date - today).days
            due_later_bucket.append(entry)

    def _sum(bucket):
        return round(sum(e["total"] for e in bucket), 2)

    return {
        "forecast_as_of":      str(today),
        "forecast_horizon_days": days_ahead,
        "overdue": {
            "invoices": overdue_bucket,
            "total":    _sum(overdue_bucket),
            "count":    len(overdue_bucket),
        },
        "due_within_30_days": {
            "invoices": due_soon_bucket,
            "total":    _sum(due_soon_bucket),
            "count":    len(due_soon_bucket),
        },
        "due_later": {
            "invoices": due_later_bucket,
            "total":    _sum(due_later_bucket),
            "count":    len(due_later_bucket),
        },
        "total_expected": _sum(overdue_bucket) + _sum(due_soon_bucket) + _sum(due_later_bucket),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 13: get_client_payment_behavior (prediction support)
# ═══════════════════════════════════════════════════════════════════════════════
def get_client_payment_behavior(
    db: Session,
    org_id,
    client_name: str = None,
    limit: int = 20,
) -> dict:
    limit = min(int(limit), MAX_RESULTS)

    query = (
        db.query(Invoice, Client.name)
        .join(Client, Invoice.client_id == Client.id)
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
            Invoice.issue_date.isnot(None),
        )
    )

    if client_name:
        query = query.filter(Client.name.ilike(f"%{client_name}%"))

    rows = query.all()

    # Aggregate per client
    client_data: dict[str, dict] = {}
    for inv, cname in rows:
        paid_date_val = inv.paid_at.date() if hasattr(inv.paid_at, "date") else inv.paid_at
        days_to_pay   = (paid_date_val - inv.issue_date).days
        due_days      = (inv.due_date - inv.issue_date).days if inv.due_date else None
        late          = (paid_date_val > inv.due_date) if inv.due_date else False

        if cname not in client_data:
            client_data[cname] = {"days_list": [], "late_count": 0, "total_count": 0}

        client_data[cname]["days_list"].append(days_to_pay)
        client_data[cname]["total_count"] += 1
        if late:
            client_data[cname]["late_count"] += 1

    results = []
    for cname, data in client_data.items():
        days_list = data["days_list"]
        avg_days  = round(sum(days_list) / len(days_list), 1) if days_list else None
        late_rate = round(data["late_count"] / data["total_count"] * 100, 1)
        results.append({
            "client_name":        cname,
            "avg_days_to_pay":    avg_days,
            "late_payment_rate":  f"{late_rate}%",
            "paid_invoices":      data["total_count"],
        })

    results.sort(key=lambda x: x["avg_days_to_pay"] or 9999)

    return {
        "client_payment_behavior": results[:limit],
        "note": (
            "avg_days_to_pay is measured from issue date to payment date. "
            "late_payment_rate is the percentage of invoices paid after the due date."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Dispatcher
# ═══════════════════════════════════════════════════════════════════════════════
_TOOL_MAP = {
    "get_invoices":                get_invoices,
    "get_invoice_summary":         get_invoice_summary,
    "get_outstanding_amount":      get_outstanding_amount,
    "get_overdue_invoices":        get_overdue_invoices,
    "get_quotations":              get_quotations,
    "get_quotation_summary":       get_quotation_summary,
    "get_client_summary":          get_client_summary,
    "get_top_clients":             get_top_clients,
    "get_clients":                 get_clients,
    "get_products":                get_products,
    "get_revenue_trend":           get_revenue_trend,
    "get_cash_flow_forecast":      get_cash_flow_forecast,
    "get_client_payment_behavior": get_client_payment_behavior,
}


def execute_tool(tool_name: str, tool_parameters: dict, db: Session, org_id) -> dict:
    fn = _TOOL_MAP.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return fn(db, org_id, **tool_parameters)
