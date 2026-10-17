from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import get_url

from spectrum_ps.config import TEMPLATE_SALES_INVOICE
from spectrum_ps.utils import enqueue_outbound_sales_order_whatsapp_template


def on_sales_invoice_submit(doc, method=None):
	"""Invoice submitted: send the customer their invoice link on WhatsApp."""
	if doc.is_return:
		return

	try:
		_send_invoice_message(doc)
	except Exception:
		frappe.log_error(
			title="WhatsApp invoice message failed to queue",
			message=f"Sales Invoice: {doc.name}\n{frappe.get_traceback()}",
		)


def _invoice_download_link(doc):
	"""Public PDF link, opens without a login thanks to the document's signature key."""
	params = urlencode({"doctype": doc.doctype, "name": doc.name, "key": doc.get_signature()})
	return get_url(f"/api/method/frappe.utils.print_format.download_pdf?{params}")


def _send_invoice_message(doc):
	sales_order = next((row.sales_order for row in doc.items if row.sales_order), None)
	if not sales_order:
		frappe.log(f"Sales Invoice `{doc.name}` has no Sales Order on its items; skipping customer message")
		return

	customer_name = frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer

	template_params = {
		"customer_name": customer_name,
		"invoice_number": doc.name,
		"order_id": sales_order,
		"invoice_download_link": _invoice_download_link(doc),
	}

	enqueue_outbound_sales_order_whatsapp_template(
		sales_order,
		customer_name,
		f"{doc.name}-Sale-Invoice-Generated-Message",
		TEMPLATE_SALES_INVOICE,
		template_params,
	)
