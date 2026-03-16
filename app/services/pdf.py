"""Generate PDF for invoices and quotations using WeasyPrint."""
from __future__ import annotations
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.quotation import Quotation


INVOICE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 13px; color: #1a1a1a; padding: 40px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 40px; }}
  .company-name {{ font-size: 24px; font-weight: 700; color: #1e40af; }}
  .doc-info {{ text-align: right; }}
  .doc-title {{ font-size: 28px; font-weight: 700; color: #1e40af; text-transform: uppercase; }}
  .doc-number {{ font-size: 16px; color: #6b7280; margin-top: 4px; }}
  .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px; }}
  .info-block h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; margin-bottom: 8px; }}
  .info-block p {{ line-height: 1.6; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  thead th {{ background: #1e40af; color: white; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; }}
  tbody tr:nth-child(even) {{ background: #f8fafc; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; }}
  .text-right {{ text-align: right; }}
  .totals {{ margin-left: auto; width: 280px; }}
  .totals table {{ margin-bottom: 0; }}
  .totals td {{ padding: 8px 12px; }}
  .total-row td {{ font-weight: 700; font-size: 15px; background: #1e40af; color: white; }}
  .notes {{ margin-top: 30px; padding: 16px; background: #f8fafc; border-left: 4px solid #1e40af; border-radius: 4px; }}
  .notes h4 {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; margin-bottom: 6px; }}
  .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
  .status-paid {{ background: #dcfce7; color: #166534; }}
  .status-overdue {{ background: #fee2e2; color: #991b1b; }}
  .status-sent {{ background: #dbeafe; color: #1e40af; }}
  .status-draft {{ background: #f3f4f6; color: #374151; }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="company-name">BillFlow</div>
    </div>
    <div class="doc-info">
      <div class="doc-title">{doc_type}</div>
      <div class="doc-number">#{number}</div>
      <div style="margin-top:8px">
        <span class="status-badge status-{status_class}">{status}</span>
      </div>
    </div>
  </div>

  <div class="info-grid">
    <div class="info-block">
      <h3>Bill To</h3>
      <p><strong>{client_name}</strong></p>
      {client_email}
      {client_address}
    </div>
    <div class="info-block">
      <h3>Details</h3>
      <p><strong>Date:</strong> {issue_date}</p>
      {due_date_line}
      <p><strong>Currency:</strong> {currency}</p>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Description</th>
        <th class="text-right">Qty</th>
        <th class="text-right">Unit Price</th>
        <th class="text-right">Subtotal</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <div class="totals">
    <table>
      <tr>
        <td>Subtotal</td>
        <td class="text-right">{currency} {subtotal}</td>
      </tr>
      <tr class="total-row">
        <td>Total</td>
        <td class="text-right">{currency} {total}</td>
      </tr>
    </table>
  </div>

  {notes_block}
</body>
</html>
"""


def _format_amount(amount) -> str:
    return f"{float(amount):,.2f}"


def generate_invoice_pdf(invoice: "Invoice") -> bytes:
    rows = ""
    for i, item in enumerate(invoice.items, 1):
        rows += f"""
        <tr>
          <td>{i}</td>
          <td>
            <strong>{item.product_name}</strong>
            {f'<br><small style="color:#6b7280">{item.description}</small>' if item.description else ""}
          </td>
          <td class="text-right">{item.qty}</td>
          <td class="text-right">{_format_amount(item.unit_price)}</td>
          <td class="text-right">{_format_amount(item.subtotal)}</td>
        </tr>"""

    status_class = invoice.status.value.lower()
    due_line = f"<p><strong>Due Date:</strong> {invoice.due_date}</p>" if invoice.due_date else ""
    notes_block = f'<div class="notes"><h4>Notes</h4><p>{invoice.notes}</p></div>' if invoice.notes else ""
    client_email = f"<p>{invoice.client.email}</p>" if invoice.client.email else ""
    client_address = f"<p>{invoice.client.address}</p>" if invoice.client.address else ""

    html = INVOICE_TEMPLATE.format(
        doc_type="INVOICE",
        number=invoice.invoice_number,
        status=invoice.status.value.upper(),
        status_class=status_class,
        client_name=invoice.client.name,
        client_email=client_email,
        client_address=client_address,
        issue_date=invoice.issue_date,
        due_date_line=due_line,
        currency=invoice.currency,
        rows=rows,
        subtotal=_format_amount(invoice.subtotal),
        total=_format_amount(invoice.total),
        notes_block=notes_block,
    )

    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except ImportError:
        # Fallback: return HTML as bytes if weasyprint not available
        return html.encode("utf-8")


def generate_quotation_pdf(quotation: "Quotation") -> bytes:
    rows = ""
    for i, item in enumerate(quotation.items, 1):
        rows += f"""
        <tr>
          <td>{i}</td>
          <td>
            <strong>{item.product_name}</strong>
            {f'<br><small style="color:#6b7280">{item.description}</small>' if item.description else ""}
          </td>
          <td class="text-right">{item.qty}</td>
          <td class="text-right">{_format_amount(item.unit_price)}</td>
          <td class="text-right">{_format_amount(item.subtotal)}</td>
        </tr>"""

    status_class = quotation.status.value.lower()
    valid_line = f"<p><strong>Valid Until:</strong> {quotation.valid_until}</p>" if quotation.valid_until else ""
    notes_block = f'<div class="notes"><h4>Notes</h4><p>{quotation.notes}</p></div>' if quotation.notes else ""
    client_email = f"<p>{quotation.client.email}</p>" if quotation.client.email else ""
    client_address = f"<p>{quotation.client.address}</p>" if quotation.client.address else ""

    html = INVOICE_TEMPLATE.format(
        doc_type="QUOTATION",
        number=quotation.quote_number,
        status=quotation.status.value.upper(),
        status_class=status_class,
        client_name=quotation.client.name,
        client_email=client_email,
        client_address=client_address,
        issue_date=quotation.issue_date,
        due_date_line=valid_line,
        currency=quotation.currency,
        rows=rows,
        subtotal=_format_amount(quotation.subtotal),
        total=_format_amount(quotation.total),
        notes_block=notes_block,
    )

    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except ImportError:
        return html.encode("utf-8")
