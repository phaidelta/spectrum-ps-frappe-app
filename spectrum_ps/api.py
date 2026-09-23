import frappe
from frappe import _
from frappe.utils.response import Response

from .integrations.config import require_setting
from .integrations.raven import RavenClient
from .realtime import publish_message
from .integrations.twilio import validate_webhook_signature


def get_raven_channel_from_sales_order(sender_phone: str) -> str:
	"""Fetch the Raven Channel ID linked to the Sales Order for the given customer phone."""
	clean_phone = sender_phone.replace("whatsapp:", "").strip()

	try:
		channel_id = frappe.db.get_value(
			"Sales Order",
			filters={"docstatus": ["<", 2], "contact_phone": ["like", f"%{clean_phone}%"]},
			fieldname="custom_raven_channel_id",
		)
		if channel_id:
			return channel_id
	except Exception as e:
		frappe.logger().warning(f"Could not query custom_raven_channel_id: {e}")

	return require_setting("raven_channel_id")
@frappe.whitelist(allow_guest=True)
def whatsapp_webhook(*args, **kwargs):
	"""Receive an inbound WhatsApp message from Twilio and forward it to Raven."""
	# Safely extract request URL for Twilio signature validation
	request_url = getattr(frappe.request, "url", "") if frappe.request else ""
	form = frappe.form_dict or {}

	if request_url and not validate_webhook_signature(request_url, form):
		frappe.throw(_("Invalid Twilio signature"), frappe.PermissionError)

	sender = form.get("From", "")
	profile_name = form.get("ProfileName") or sender
	body = form.get("Body", "")
	message_sid = form.get("MessageSid")

	# Fetch dynamic channel ID based on Sales Order
	channel_id = get_raven_channel_from_sales_order(sender)

	raven_text = f"WhatsApp - {profile_name}: {body}"
	raven_response = RavenClient().send_message(raven_text, channel_id)

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
