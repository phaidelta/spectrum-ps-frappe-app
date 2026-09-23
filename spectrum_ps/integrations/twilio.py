import frappe
from twilio.request_validator import RequestValidator

from .config import require_setting


class FormDictWrapper(dict):
	"""Wrapper around frappe.form_dict to provide the .getall() method expected by Twilio's RequestValidator."""

	def getall(self, key):
		val = self.get(key)
		if val is None:
			return []
		return [val] if not isinstance(val, list) else val


def validate_webhook_signature(url: str, form_data: dict) -> bool:
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
