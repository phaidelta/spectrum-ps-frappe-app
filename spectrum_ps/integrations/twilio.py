import frappe
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from .config import require_setting


class FormDictWrapper(dict):
	"""Wrapper around frappe.form_dict to provide the .getall() method expected by Twilio's RequestValidator."""

	def getall(self, key):
		val = self.get(key)
		if val is None:
			return []
		return [val] if not isinstance(val, list) else val


def validate_webhook_signature(url: str, form_data: dict) -> bool:
	"""Validate Twilio X-Twilio-Signature header for incoming webhooks."""
	# Bypass signature verification in local development if configured or needed
	if frappe.conf.get("developer_mode"):
		return True

	signature = frappe.get_request_header("X-Twilio-Signature")
	if not signature:
		return False

	auth_token = require_setting("twilio_auth_token")
	validator = RequestValidator(auth_token)

	# Reconstruct public ngrok URL if running behind proxy
	forwarded_proto = frappe.get_request_header("X-Forwarded-Proto") or "https"
	forwarded_host = frappe.get_request_header("X-Forwarded-Host") or frappe.get_request_header("Host")

	if forwarded_host:
		request_path = frappe.request.path if frappe.request else "/api/method/spectrum_ps.api.whatsapp_webhook"
		url = f"{forwarded_proto}://{forwarded_host}{request_path}"

	# Exclude internal Frappe query keys like 'cmd'
	params = {k: v for k, v in form_data.items() if k != "cmd"}
	wrapped_params = FormDictWrapper(params)

	return validator.validate(url, wrapped_params, signature)


def send_whatsapp_message(to: str = None, body: str = "", to_number: str = None) -> str:
	"""Send an outbound WhatsApp message via Twilio REST API.

	Accepts either 'to' or 'to_number' to maintain backward compatibility across handlers.
	"""
	recipient = to or to_number
	if not recipient:
		raise ValueError("A valid destination phone number ('to' or 'to_number') is required.")

	account_sid = require_setting("twilio_account_sid")
	auth_token = require_setting("twilio_auth_token")
	from_number = require_setting("twilio_whatsapp_number")  # e.g., 'whatsapp:+14155238886'

	# Ensure source number starts with whatsapp:
	if not from_number.startswith("whatsapp:"):
		from_number = f"whatsapp:{from_number}"

	# Ensure destination number starts with whatsapp:
	if not recipient.startswith("whatsapp:"):
		recipient = f"whatsapp:{recipient}"

	client = Client(account_sid, auth_token)
	message = client.messages.create(
		from_=from_number,
		body=body,
		to=recipient
	)

	return message.sid
