import frappe
from frappe import _
from frappe.utils.response import Response

from .integrations.config import require_setting
from .integrations.raven import RavenClient
from .realtime import publish_message
from .integrations.twilio import validate_webhook_signature


def get_raven_channel_and_sales_order(sender_phone: str):
	"""Find matching Sales Order or fallback to default channel."""
	clean_phone = sender_phone.replace("whatsapp:", "").strip()

	try:
		so = frappe.db.get_value(
			"Sales Order",
			filters={"docstatus": ["<", 2], "contact_phone": ["like", f"%{clean_phone}%"]},
			fieldname=["name", "custom_raven_channel", "contact_phone"],
			as_dict=True,
		)
		if so and so.get("custom_raven_channel_id"):
			return so.custom_raven_channel_id, so.name
	except Exception as e:
		frappe.logger().warning(f"Sales Order lookup error: {e}")

	# Fallback to the channel ID defined in your config (e.g., tkt-001 channel)
	default_channel = require_setting("raven_channel_id")
	return default_channel, None


@frappe.whitelist(allow_guest=True)
def whatsapp_webhook(*args, **kwargs):
	"""Receive an inbound WhatsApp message from Twilio and forward it to Raven."""
	request_url = getattr(frappe.request, "url", "") if frappe.request else ""
	form = frappe.form_dict or {}

	if request_url and not validate_webhook_signature(request_url, form):
		frappe.throw(_("Invalid Twilio signature"), frappe.PermissionError)

	sender = form.get("From", "")
	profile_name = form.get("ProfileName") or sender
	body = form.get("Body", "")
	message_sid = form.get("MessageSid")

	channel_id, so_name = get_raven_channel_and_sales_order(sender)

	raven_text = f"WhatsApp - {profile_name} ({sender}): {body}"
	
	# Send to Raven and tag flags to avoid loop
	raven_response = RavenClient().send_message(text=raven_text, channel=channel_id)
	if hasattr(raven_response, "flags"):
		raven_response.flags.from_whatsapp = True

	publish_message(
		"spectrum_ps_whatsapp_message",
		direction="whatsapp_to_raven",
		message={
			"message_sid": message_sid,
			"from": sender,
			"body": body,
			"channel_id": channel_id,
			"raven": raven_response,
		},
	)

	return Response(
		'<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
		content_type="application/xml",
	)
