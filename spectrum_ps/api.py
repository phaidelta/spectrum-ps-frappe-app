import frappe
from frappe import _
from frappe.utils.response import Response

from .integrations.config import require_setting
from .integrations.raven import RavenClient
from .realtime import publish_message
from .integrations.twilio import validate_webhook_signature


@frappe.whitelist(allow_guest=True)
def whatsapp_webhook():
    """Receive an inbound WhatsApp message from Twilio and forward it to Raven."""
    if not validate_webhook_signature(frappe.request.url, frappe.form_dict):
        frappe.throw(_("Invalid Twilio signature"), frappe.PermissionError)

    form = frappe.form_dict
    sender = form.get("From", "")
    profile_name = form.get("ProfileName") or sender
    body = form.get("Body", "")
    message_sid = form.get("MessageSid")

    raven_text = f"WhatsApp - {profile_name}: {body}"
    raven_response = RavenClient().send_message(raven_text)

    publish_message(
        "spectrum_ps_whatsapp_message",
        direction="whatsapp_to_raven",
        message={
            "message_sid": message_sid,
            "from": sender,
            "body": body,
            "raven": raven_response,
        },
    )

    return Response(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
        content_type="application/xml",
    )
