import frappe
from twilio.request_validator import RequestValidator

from .config import require_setting


def validate_webhook_signature(url: str, form_data: dict) -> bool:
    signature = frappe.get_request_header("X-Twilio-Signature")
    if not signature:
        return False
    validator = RequestValidator(require_setting("twilio_auth_token"))
    return validator.validate(url, form_data, signature)
