import html
import re

import frappe

from spectrum_ps.integrations.twilio import send_whatsapp_message
from spectrum_ps.messaging import get_sales_order_by_raven_channel

logger = frappe.logger("api", allow_site=True, file_count=50)

_TAG_RE = re.compile(r"<[^>]*>")


def _clean(value: str) -> str:
	"""Raven stores message text as HTML; strip it down to plain text."""
	return html.unescape(_TAG_RE.sub("", value or "")).strip()


def send_outbound_whatsapp(doc, method=None):
	"""Raven Message after_insert: forward admin/technician messages to WhatsApp."""

	# Loop guards: never send back anything that came from WhatsApp
	if frappe.flags.get("in_whatsapp_webhook"):
		return
	if doc.get("is_bot_message") or doc.get("bot"):
		return
	if doc.get("message_type") not in (None, "Text"):
		return

	body = _clean(doc.get("text"))
	if not doc.channel_id or not body:
		return

	sales_order = get_sales_order_by_raven_channel(doc.channel_id)
	if not sales_order:
		return  # not a Sales Order channel, ignore

	# Send in a background job so Raven stays fast and a Twilio error
	# can never roll back the admin's message.
	frappe.enqueue(
		"spectrum_ps.spectrum_ps.doc_events.raven_message.deliver_to_whatsapp",
		queue="short",
		enqueue_after_commit=True,
		message_id=doc.name,
		sales_order=sales_order.name,
		customer=sales_order.customer,
		body=body,
	)


def deliver_to_whatsapp(message_id, sales_order, customer, body):
	"""Background job: send the message through Twilio."""

	key = f"spectrum_ps:raven_out:{message_id}"
	if frappe.cache.get_value(key):
		return  # already delivered

	mobile = (frappe.db.get_value("Customer", customer, "mobile_no") or "").strip()
	if not mobile:
		frappe.log_error(
			title="Raven → WhatsApp: customer has no mobile_no",
			message=f"Customer: {customer}\nSales Order: {sales_order}",
		)
		return

	logger.info(f"Sending WhatsApp message to customer {customer} with mobile no. {mobile}")

	try:
		sid = send_whatsapp_message(to=mobile, body=body)
	except Exception:
		frappe.log_error(title="Raven → WhatsApp failed", message=frappe.get_traceback())
		return

	frappe.cache.set_value(key, sid, expires_in_sec=86400)
