import json

import frappe
from twilio.base.exceptions import TwilioRestException
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


def send_template_message(client: Client, from_whatsapp: str, to_number: str, template: dict):
	content_sid = template.get("content_sid")
	content_variables = template.get("content_variables")

	# Exclude 'body' when using content_sid
	fallback_message = client.messages.create(
		from_=from_whatsapp,
		to=to_number,
		content_sid=content_sid,
		content_variables=json.dumps(content_variables) if content_variables is not None else "{}",
	)

	print(f"Template message sent successfully! SID: {fallback_message.sid}")
	return fallback_message


def send_message_with_fallback(
	client: Client,
	from_whatsapp: str,
	to_number: str,
	freeform_text: str | None = None,
	template: dict | None = None,
):
	try:
		if freeform_text is not None:
			# 1. Attempt to send the free-form message
			print("Attempting to send free-form message...")
			message = client.messages.create(from_=from_whatsapp, to=to_number, body=freeform_text)
			print(f"Free-form message sent successfully! SID: {message.sid}")
			return message
		elif template is not None:
			print("Attempting to send template message %s..." % template)
			return send_template_message(client, from_whatsapp, to_number, template)
		else:
			print("Nothing is provided to send :/")
	except TwilioRestException as e:
		# Error 63016 means the 24-hour window is closed
		if e.code == 63016:
			if template is not None:
				print("24-hour window closed. Falling back to template message...")

				return send_template_message(client, from_whatsapp, to_number, template)
			else:
				print("24-hour window closed, but not fallback Template sid provided. Skipping message...")
				return
		else:
			# Raise any other Twilio exceptions (e.g., authentication, invalid numbers)
			print(f"An unexpected Twilio error occurred: {e.msg} (Code: {e.code})")
			raise e


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
		request_path = (
			frappe.request.path if frappe.request else "/api/method/spectrum_ps.api.whatsapp_webhook"
		)
		url = f"{forwarded_proto}://{forwarded_host}{request_path}"

	# Exclude internal Frappe query keys like 'cmd'
	params = {k: v for k, v in form_data.items() if k != "cmd"}
	wrapped_params = FormDictWrapper(params)

	return validator.validate(url, wrapped_params, signature)


def send_whatsapp_message(
	to: str | None = None, body: str | None = None, to_number: str | None = None, template: dict | None = None
) -> str:
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

	message = send_message_with_fallback(
		client, from_whatsapp=from_number, to_number=recipient, freeform_text=body, template=template
	)

	if message is not None:
		return message.sid


def send_whatsapp_template_message(
		to:str | None = None,
		content_sid : str = "",
		content_variables:dict | None =None,
		to_number : str | None = None,
) -> str:
	"""Send a approved WhatsApp content template via Twilio REST API."""
	recipient = to or to_number

	if not recipient:
		raise ValueError("A valid destination phone number ('to' or 'to_number') is required.")
	if not content_sid:
		raise ValueError("content_sid (Twilio Content Template SID) is required.")

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
		to=recipient,
		content_sid=content_sid,
		content_variables=json.dumps(content_variables) if content_variables is not None else "{}"
		)

	return message.sid
