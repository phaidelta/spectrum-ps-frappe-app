import json

import frappe

from .integrations.raven import RavenClient
from .integrations.twilio import send_whatsapp_message
from .realtime import publish_message

_SEEN_KEY = "spectrum_ps:raven_seen_message_ids"
_MAX_SEEN = 2000


def _normalize(raw_message: dict) -> dict:
    return {
        "id": raw_message.get("name") or raw_message.get("id") or raw_message.get("message_id"),
        "content": raw_message.get("text") or raw_message.get("content"),
        "sender": raw_message.get("sender") or raw_message.get("owner") or raw_message.get("sent_by"),
        "is_bot_message": raw_message.get("is_bot_message", 0),
        "raw": raw_message,
    }


def _seen_ids() -> list[str]:
    raw = frappe.cache().get_value(_SEEN_KEY) or "[]"
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        value = []
    return value if isinstance(value, list) else []


def _remember(message_id: str) -> None:
    seen = _seen_ids()
    if message_id not in seen:
        seen.append(message_id)
    frappe.cache().set_value(_SEEN_KEY, json.dumps(seen[-_MAX_SEEN:]))


def poll_raven_messages() -> None:
    """Poll the configured Raven channel and forward new messages to WhatsApp."""
    client = RavenClient()
    messages = [_normalize(item) for item in client.get_messages()]
    if not messages:
        return

    seen = set(_seen_ids())

    for message in messages:
        message_id = message.get("id")
        if not message_id:
            continue

        if message_id in seen:
            continue

        if message.get("is_bot_message") in (1, True, "1", "true", "True"):
            _remember(message_id)
            continue

        content = message.get("content")
        if not content:
            _remember(message_id)
            continue

        recipient = frappe.conf.get("whatsapp_customer_number") or frappe.get_env("WHATSAPP_CUSTOMER_NUMBER")
        if not recipient:
            frappe.log_error(
                "No WhatsApp customer number configured for Raven -> WhatsApp delivery.",
                "Raven to WhatsApp",
            )
            _remember(message_id)
            continue

        try:
            response = send_whatsapp_message(recipient, content)
        except Exception as exc:
            frappe.log_error(f"Raven message forwarding failed: {exc}", "Raven to WhatsApp")
            _remember(message_id)
            continue

        publish_message(
            "spectrum_ps_raven_message",
            direction="raven_to_whatsapp",
            message={
                "message_id": message_id,
                "sender": message.get("sender"),
                "body": content,
                "twilio": response,
            },
        )
        _remember(message_id)
