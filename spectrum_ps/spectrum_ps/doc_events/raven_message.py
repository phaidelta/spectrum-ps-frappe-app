import html
import re

import frappe

from spectrum_ps.integrations.twilio import send_whatsapp_message, send_whatsapp_template_message
from spectrum_ps.logger import get_logger
from spectrum_ps.messaging import get_sales_order_by_raven_channel
from spectrum_ps.spectrum_ps.utils import as_user

logger = get_logger()

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

	sender_name = frappe.get_doc("User", doc.owner)
	body_ = "*{sender}*:\n{body}".format(sender=sender_name.first_name.strip(), body=body)

	sales_order = get_sales_order_by_raven_channel(doc.channel_id)
	if not sales_order:
		return  # not a Sales Order channel, ignore

	customer = frappe.get_doc("Customer", sales_order.customer)
	customer.custom_active_sales_order = doc.name
	with as_user():
		customer.save(ignore_permissions=True)

	template = {
		"content_sid": "HX5edfd4af77fea1daf05e7f073ab90bbe",
		"content_variables": {
			"agent_name": sender_name,
			"agent_message": body,
		}
	}

	# Send in a background job so Raven stays fast and a Twilio error
	# can never roll back the admin's message.
	frappe.enqueue(
		"spectrum_ps.spectrum_ps.doc_events.raven_message.deliver_to_whatsapp",
		queue="short",
		enqueue_after_commit=True,
		message_id=doc.name,
		sales_order=sales_order.name,
		customer=sales_order.customer,
		body=body_,
		template=template,
	)


def deliver_template_message_to_whatsapp(
	template_id, customer, content_variables, sales_order, message_id, **kwargs
):
	"""Background job: send an approved WhatsApp template through Twilio."""

	if not template_id:
		frappe.log_error(
			title="WhatsApp template: no template id passed",
			message=f"Customer: {customer}\nSale Order: {sales_order}",
		)
		return

	if not customer:
		frappe.log_error(
			title="WhatsApp template: no customer passed",
			message=f"Template: {template_id}\n Sales Order: {sales_order}",
		)
		return

	# TODO need to add technician to teh key?
	key = f"spectrum_ps:template_out:{sales_order or customer}:{template_id}:{message_id}"
	if frappe.cache.get_value(key):
		return  # already delivered

	mobile = (frappe.db.get_value("Customer", customer, "mobile_no") or "").strip()

	if not mobile:
		frappe.log_error(
			title="WhatsApp template: customer has no mobile_no",
			message=f"Customer: {customer}\nSales Order: {sales_order}\nTemplate:{template_id}",
		)
		return

	logger.info(f"Sending WhatsApp template {template_id} to customer {customer} with mobile no. {mobile}")

	try:
		sid = send_whatsapp_template_message(
			to=mobile, content_sid=template_id, content_variables=content_variables
		)
	except Exception:
		frappe.log_error(title=f"WhatsApp template failed: {template_id}", message=frappe.get_traceback())
		return

	frappe.cache.set_value(key, sid, expires_in_sec=86400)


def deliver_to_whatsapp(
	message_id,
	sales_order,
	customer,
	body: str | None = None,
	template: dict | None = None,
):
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
		sid = send_whatsapp_message(
			to=mobile,
			body=body,
			template=template,
		)
	except Exception:
		frappe.log_error(
			title="Raven → WhatsApp failed",
			message=frappe.get_traceback(),
		)
		return

	frappe.cache.set_value(key, sid, expires_in_sec=86400)
