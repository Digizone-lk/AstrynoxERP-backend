"""Generate PDF for invoices and quotations using WeasyPrint.

Three built-in templates (set via org.pdf_template):
  classic  — blue header, clean table  (default)
  modern   — indigo accent bar, card layout
  minimal  — serif, black-and-white, professional
"""
from __future__ import annotations
import html as html_lib
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.modules.ims.models.invoice import Invoice
    from app.modules.ims.models.quotation import Quotation
    from app.modules.ims.models.organization import Organization


def _esc(value) -> str:
    """HTML-escape a value for safe embedding."""
    return html_lib.escape(str(value)) if value else ""


def _format_amount(amount) -> str:
    return f"{float(amount):,.2f}"


# ─── Template: Classic (blue) ─────────────────────────────────────────────────

_CLASSIC_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 13px; color: #1a1a1a; padding: 40px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 40px; }
.company-name { font-size: 24px; font-weight: 700; color: #1e40af; }
.company-sub { font-size: 12px; color: #6b7280; margin-top: 4px; line-height: 1.6; }
.doc-info { text-align: right; }
.doc-title { font-size: 28px; font-weight: 700; color: #1e40af; text-transform: uppercase; }
.doc-number { font-size: 16px; color: #6b7280; margin-top: 4px; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px; }
.info-block h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; margin-bottom: 8px; }
.info-block p { line-height: 1.6; }
table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
thead th { background: #1e40af; color: white; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; }
tbody tr:nth-child(even) { background: #f8fafc; }
td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; }
.text-right { text-align: right; }
.totals { margin-left: auto; width: 280px; }
.totals table { margin-bottom: 0; }
.totals td { padding: 8px 12px; }
.total-row td { font-weight: 700; font-size: 15px; background: #1e40af; color: white; }
.notes { margin-top: 30px; padding: 16px; background: #f8fafc; border-left: 4px solid #1e40af; border-radius: 4px; }
.notes h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; margin-bottom: 6px; }
.status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
.status-paid,.status-approved { background: #dcfce7; color: #166534; }
.status-overdue,.status-rejected { background: #fee2e2; color: #991b1b; }
.status-sent { background: #dbeafe; color: #1e40af; }
.status-draft,.status-converted { background: #f3f4f6; color: #374151; }
"""

_CLASSIC_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>
  <div class="header">
    <div>
      {logo_html}
      <div class="company-name">{org_name}</div>
      <div class="company-sub">{org_sub}</div>
    </div>
    <div class="doc-info">
      <div class="doc-title">{doc_type}</div>
      <div class="doc-number">#{number}</div>
      <div style="margin-top:8px"><span class="status-badge status-{status_class}">{status}</span></div>
    </div>
  </div>
  <div class="info-grid">
    <div class="info-block"><h3>Bill To</h3><p><strong>{client_name}</strong></p>{client_email}{client_address}</div>
    <div class="info-block"><h3>Details</h3>
      <p><strong>Date:</strong> {issue_date}</p>{date2_line}
      <p><strong>Currency:</strong> {currency}</p>
    </div>
  </div>
  <table><thead><tr><th>#</th><th>Description</th><th class="text-right">Qty</th><th class="text-right">Unit Price</th><th class="text-right">Subtotal</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="totals"><table>
    <tr><td>Subtotal</td><td class="text-right">{currency} {subtotal}</td></tr>
    <tr class="total-row"><td>Total</td><td class="text-right">{currency} {total}</td></tr>
  </table></div>
  {notes_block}
</body></html>"""


# ─── Template: Modern (indigo accent) ─────────────────────────────────────────

_MODERN_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 13px; color: #1a1a1a; }
.accent { height: 6px; background: #6366f1; }
.content { padding: 40px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 36px; }
.company-name { font-size: 22px; font-weight: 800; color: #1e1b4b; letter-spacing: -0.5px; }
.company-sub { font-size: 12px; color: #6b7280; margin-top: 4px; line-height: 1.6; }
.doc-badge { background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 8px; padding: 12px 20px; text-align: right; }
.doc-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #6366f1; }
.doc-number { font-size: 22px; font-weight: 700; color: #1e1b4b; margin-top: 4px; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; padding: 24px; background: #f9fafb; border-radius: 8px; }
.info-block h3 { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; color: #9ca3af; margin-bottom: 8px; }
.info-block p { line-height: 1.7; color: #374151; }
table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
thead th { padding: 11px 14px; text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: #6b7280; border-bottom: 2px solid #e5e7eb; }
td { padding: 12px 14px; border-bottom: 1px solid #f3f4f6; color: #374151; }
.text-right { text-align: right; }
.totals { margin-left: auto; width: 260px; border-top: 2px solid #e5e7eb; padding-top: 16px; }
.totals tr { display: flex; justify-content: space-between; padding: 5px 0; }
.totals .total-final { font-size: 16px; font-weight: 800; color: #1e1b4b; border-top: 2px solid #6366f1; padding-top: 10px; margin-top: 6px; }
.notes { margin-top: 32px; padding: 16px; background: #f5f3ff; border-radius: 8px; border-left: 3px solid #6366f1; }
.notes h4 { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: #6366f1; margin-bottom: 6px; }
.status-badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
.status-paid,.status-approved { background: #dcfce7; color: #166534; }
.status-overdue,.status-rejected { background: #fee2e2; color: #991b1b; }
.status-sent { background: #dbeafe; color: #1d4ed8; }
.status-draft,.status-converted { background: #f3f4f6; color: #374151; }
"""

_MODERN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>
  <div class="accent"></div>
  <div class="content">
    <div class="header">
      <div>
        {logo_html}
        <div class="company-name">{org_name}</div>
        <div class="company-sub">{org_sub}</div>
      </div>
      <div class="doc-badge">
        <div class="doc-label">{doc_type}</div>
        <div class="doc-number">#{number}</div>
        <div style="margin-top:8px"><span class="status-badge status-{status_class}">{status}</span></div>
      </div>
    </div>
    <div class="info-grid">
      <div class="info-block"><h3>Bill To</h3><p><strong>{client_name}</strong></p>{client_email}{client_address}</div>
      <div class="info-block"><h3>Details</h3>
        <p><strong>Date:</strong> {issue_date}</p>{date2_line}
        <p><strong>Currency:</strong> {currency}</p>
      </div>
    </div>
    <table><thead><tr><th>#</th><th>Description</th><th class="text-right">Qty</th><th class="text-right">Unit Price</th><th class="text-right">Subtotal</th></tr></thead>
    <tbody>{rows}</tbody></table>
    <div class="totals">
      <div style="display:flex;justify-content:space-between;padding:5px 0"><span>Subtotal</span><span>{currency} {subtotal}</span></div>
      <div class="total-final" style="display:flex;justify-content:space-between"><span>Total</span><span>{currency} {total}</span></div>
    </div>
    {notes_block}
  </div>
</body></html>"""


# ─── Template: Minimal (serif, B&W) ───────────────────────────────────────────

_MINIMAL_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, 'Times New Roman', serif; font-size: 12px; color: #111; padding: 50px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #111; padding-bottom: 20px; margin-bottom: 28px; }
.company-name { font-size: 20px; font-weight: bold; text-transform: uppercase; letter-spacing: 2px; }
.company-sub { font-size: 10px; color: #555; margin-top: 6px; line-height: 1.8; letter-spacing: 0.5px; }
.doc-right { text-align: right; }
.doc-title { font-size: 22px; font-weight: bold; text-transform: uppercase; letter-spacing: 4px; }
.doc-number { font-size: 13px; color: #555; margin-top: 6px; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 28px; }
.info-block h3 { font-size: 9px; text-transform: uppercase; letter-spacing: 2px; color: #777; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-bottom: 10px; font-family: Arial, sans-serif; }
.info-block p { line-height: 1.9; }
table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
thead th { padding: 8px 10px; font-size: 10px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; border-top: 1px solid #111; border-bottom: 1px solid #111; font-family: Arial, sans-serif; }
td { padding: 10px; border-bottom: 1px solid #ddd; }
.text-right { text-align: right; }
.totals { margin-left: auto; width: 240px; margin-top: 8px; border-top: 1px solid #111; padding-top: 12px; }
.totals div { display: flex; justify-content: space-between; padding: 5px 0; }
.total-final { font-weight: bold; font-size: 14px; border-top: 2px solid #111; padding-top: 8px; margin-top: 4px; }
.notes { margin-top: 28px; padding: 14px; border: 1px solid #ccc; }
.notes h4 { font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px; color: #777; margin-bottom: 8px; font-family: Arial, sans-serif; }
.status-badge { display: inline-block; padding: 2px 10px; border: 1px solid #111; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-family: Arial, sans-serif; }
.status-paid,.status-approved,.status-sent { }
.status-overdue,.status-rejected { text-decoration: underline; }
.status-draft,.status-converted { color: #888; border-color: #aaa; }
"""

_MINIMAL_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>
  <div class="header">
    <div>
      {logo_html}
      <div class="company-name">{org_name}</div>
      <div class="company-sub">{org_sub}</div>
    </div>
    <div class="doc-right">
      <div class="doc-title">{doc_type}</div>
      <div class="doc-number">No. {number}</div>
      <div style="margin-top:10px"><span class="status-badge status-{status_class}">{status}</span></div>
    </div>
  </div>
  <div class="info-grid">
    <div class="info-block"><h3>Bill To</h3><p><strong>{client_name}</strong></p>{client_email}{client_address}</div>
    <div class="info-block"><h3>Document Details</h3>
      <p><strong>Date:</strong> {issue_date}</p>{date2_line}
      <p><strong>Currency:</strong> {currency}</p>
    </div>
  </div>
  <table><thead><tr><th>#</th><th>Description</th><th class="text-right">Qty</th><th class="text-right">Unit Price</th><th class="text-right">Subtotal</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="totals">
    <div><span>Subtotal</span><span>{currency} {subtotal}</span></div>
    <div class="total-final"><span>Total</span><span>{currency} {total}</span></div>
  </div>
  {notes_block}
</body></html>"""


# ─── Shared build helpers ─────────────────────────────────────────────────────

def _build_rows(items) -> str:
    rows = ""
    for i, item in enumerate(items, 1):
        desc = f'<br><small style="color:#6b7280">{_esc(item.description)}</small>' if item.description else ""
        rows += (
            f"<tr><td>{i}</td>"
            f"<td><strong>{_esc(item.product_name)}</strong>{desc}</td>"
            f"<td class='text-right'>{item.qty}</td>"
            f"<td class='text-right'>{_format_amount(item.unit_price)}</td>"
            f"<td class='text-right'>{_format_amount(item.subtotal)}</td></tr>"
        )
    return rows


def _org_meta(org: Optional["Organization"]):
    """Return (name, sub_lines, logo_html, template)."""
    if not org:
        return "BillFlow", "", "", "classic"

    name = _esc(org.name)
    sub_parts = []
    if org.address:
        sub_parts.append(_esc(org.address))
    if org.phone:
        sub_parts.append(_esc(org.phone))
    if org.email:
        sub_parts.append(_esc(org.email))
    if org.website:
        sub_parts.append(_esc(org.website))
    sub_html = "<br>".join(sub_parts)

    logo_html = ""
    if org.logo_url:
        logo_html = f'<img src="{_esc(org.logo_url)}" style="max-height:50px;max-width:160px;object-fit:contain;margin-bottom:8px;display:block" alt="{name} logo">'

    template = getattr(org, "pdf_template", None) or "classic"
    return name, sub_html, logo_html, template


def _render(template: str, **kwargs) -> str:
    tpl_map = {
        "classic": (_CLASSIC_CSS, _CLASSIC_HTML),
        "modern":  (_MODERN_CSS,  _MODERN_HTML),
        "minimal": (_MINIMAL_CSS, _MINIMAL_HTML),
    }
    css, html_tpl = tpl_map.get(template, tpl_map["classic"])
    return html_tpl.format(css=css, **kwargs)


def _to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except ImportError:
        return html.encode("utf-8")


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_invoice_pdf(invoice: "Invoice", org: Optional["Organization"] = None) -> bytes:
    org_name, org_sub, logo_html, template = _org_meta(org)
    status_class = invoice.status.value.lower()
    notes_block = (
        f'<div class="notes"><h4>Notes</h4><p>{_esc(invoice.notes)}</p></div>'
        if invoice.notes else ""
    )

    html = _render(
        template,
        org_name=org_name,
        org_sub=org_sub,
        logo_html=logo_html,
        doc_type="Invoice",
        number=_esc(invoice.invoice_number),
        status=invoice.status.value.upper(),
        status_class=status_class,
        client_name=_esc(invoice.client.name),
        client_email=f"<p>{_esc(invoice.client.email)}</p>" if invoice.client.email else "",
        client_address=f"<p>{_esc(invoice.client.address)}</p>" if invoice.client.address else "",
        issue_date=invoice.issue_date,
        date2_line=f"<p><strong>Due Date:</strong> {invoice.due_date}</p>" if invoice.due_date else "",
        currency=_esc(invoice.currency),
        rows=_build_rows(invoice.items),
        subtotal=_format_amount(invoice.subtotal),
        total=_format_amount(invoice.total),
        notes_block=notes_block,
    )
    return _to_pdf(html)


def generate_quotation_pdf(quotation: "Quotation", org: Optional["Organization"] = None) -> bytes:
    org_name, org_sub, logo_html, template = _org_meta(org)
    status_class = quotation.status.value.lower()
    notes_block = (
        f'<div class="notes"><h4>Notes</h4><p>{_esc(quotation.notes)}</p></div>'
        if quotation.notes else ""
    )

    html = _render(
        template,
        org_name=org_name,
        org_sub=org_sub,
        logo_html=logo_html,
        doc_type="Quotation",
        number=_esc(quotation.quote_number),
        status=quotation.status.value.upper(),
        status_class=status_class,
        client_name=_esc(quotation.client.name),
        client_email=f"<p>{_esc(quotation.client.email)}</p>" if quotation.client.email else "",
        client_address=f"<p>{_esc(quotation.client.address)}</p>" if quotation.client.address else "",
        issue_date=quotation.issue_date,
        date2_line=f"<p><strong>Valid Until:</strong> {quotation.valid_until}</p>" if quotation.valid_until else "",
        currency=_esc(quotation.currency),
        rows=_build_rows(quotation.items),
        subtotal=_format_amount(quotation.subtotal),
        total=_format_amount(quotation.total),
        notes_block=notes_block,
    )
    return _to_pdf(html)
