import html
import re

import frappe

from spectrum_ps.integrations.twilio import send_whatsapp_message
from spectrum_ps.messaging import get_sales_order_by_raven_channel

_TAG_RE = re.compile(r"<[^>]*>")


def _clean(value: str) -> str:
    """Raven stores message text as HTML; strip it down to plain text."""
    return html.unescape(_TAG_RE.sub("", value or "")).strip()


def _get_sender_label(doc):
    """Resolve a Raven message sender to a customer-facing display name."""

    # Try common sender identifiers, then fall back to Frappe's document owner.
    candidates = [
        doc.get("sender"),
        doc.get("sender_id"),
        doc.get("user_id"),
        doc.get("from_user"),
        doc.get("owner"),
    ]

    sender_user = next(
        (
            value
            for value in candidates
            if value and frappe.db.exists("User", value)
        ),
        None,
    )

    if not sender_user:
        return "Support"

    # Give technicians their configured name and type.
    technician = frappe.db.get_value(
        "Technician",
        {"user": sender_user},
        ["technician_name", "technician_type"],
        as_dict=True,
    )

    if technician:
        name = technician.technician_name or sender_user
        role = technician.technician_type

        if role:
            role_name = (
                frappe.db.get_value(
                    "Technician Type", role, "type_name"
                )
                or role
            )
            return f"{name} ({role_name})"

        return name

    # Resolve non-technician senders, including administrators.
    if sender_user == "Administrator":
        return "Admin"

    full_name = frappe.db.get_value(
        "User", sender_user, "full_name"
    )

    return full_name or sender_user


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
    sender_label = _get_sender_label(doc)

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
        sender_label=sender_label,
    )


def deliver_to_whatsapp(message_id, sales_order, customer, body,sender_label="Support"):
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

    try:
        formatted_body=f"{sender_label}:{body}"
        sid = send_whatsapp_message(to=mobile, body=formatted_body)
    except Exception:
        frappe.log_error(title="Raven → WhatsApp failed", message=frappe.get_traceback())
        return

    frappe.cache.set_value(key, sid, expires_in_sec=86400)
