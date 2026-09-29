import re
import requests
import frappe
import socketio

from .integrations.twilio import send_whatsapp_message
from .messaging import get_sales_order_by_raven_channel
from urllib.parse import urlparse


RAVEN_NAMESPACE = "/site1.local"
FRAPPE_SITE = None


def _clean_html(value: str) -> str:
    value = value or ""
    value = re.sub(r"<[^>]*>", "", str(value))
    return value.strip()


def _is_bot_message(message_details: dict) -> bool:
    return message_details.get("is_bot_message") in (1, True, "1", "true", "True")


def _connect_frappe(site: str):
    frappe.init(site=site)
    frappe.connect()


sio = socketio.Client(logger=True, engineio_logger=False, reconnection=True)


@sio.event(namespace=RAVEN_NAMESPACE)
def connect():
    print("CONNECTED TO RAVEN SOCKET.IO")
    print("Namespace:", RAVEN_NAMESPACE)

    # Subscribe to the Raven Channel doctype. The listener receives events for
    # channels; Frappe resolves channel_id -> Sales Order dynamically.
    sio.emit(
        "doctype_subscribe",
        ["Raven Channel"],
        namespace=RAVEN_NAMESPACE,
    )
    print("Raven Channel subscription sent.")


@sio.event(namespace=RAVEN_NAMESPACE)
def disconnect():
    print("DISCONNECTED FROM RAVEN SOCKET.IO")


@sio.on("message_created", namespace=RAVEN_NAMESPACE)
def message_created(data):
    """Forward a technician/admin Raven message to the Customer's WhatsApp."""
    site = FRAPPE_SITE or frappe.local.site
    if not site:
        raise RuntimeError("Frappe site is not configured for the Raven socket listener")
    _connect_frappe(site)

    try:
        channel_id = data.get("channel_id")
        message_id = data.get("message_id")
        sender = data.get("sender")
        details = data.get("message_details") or {}
        content = _clean_html(details.get("content"))

        print(
            "RAVEN MESSAGE:",
            {
                "channel_id": channel_id,
                "message_id": message_id,
                "sender": sender,
                "content": content,
                "is_bot_message": details.get("is_bot_message"),
            },
        )

        # Customer WhatsApp -> Raven is authored by the customer's Raven Bot.
        # Never echo that bot message back to WhatsApp.
        if _is_bot_message(details):
            print("Ignoring Raven Bot message to prevent loop.")
            return

        if not channel_id or not message_id or not content:
            return

        # Idempotency guard using Redis. This is safe across reconnects and
        # multiple listener instances.
        processed_key = f"spectrum_ps:raven_socket:processed:{message_id}"
        if frappe.cache().get_value(processed_key):
            print("Ignoring duplicate Raven message:", message_id)
            return

        sales_order = get_sales_order_by_raven_channel(channel_id)
        if not sales_order:
            print("No active Sales Order found for Raven channel:", channel_id)
            return

        customer = frappe.get_cached_doc("Customer", sales_order.customer)
        mobile_number = (customer.mobile_no or "").strip()
        if not mobile_number:
            frappe.log_error(
                title="Raven Socket WhatsApp Skip",
                message=(
                    f"Customer {customer.name} has no mobile_no. "
                    f"Sales Order: {sales_order.name}; Raven Channel: {channel_id}"
                ),
            )
            return

        sid = send_whatsapp_message(to=mobile_number, body=content)

        # Mark only after Twilio accepts the message. If Twilio fails, a later
        # reconnect can retry it instead of losing the message.
        frappe.cache().set_value(processed_key, sid, expires_in_sec=86400)

        frappe.publish_realtime(
            "spectrum_ps_raven_message",
            message={
                "direction": "raven_to_whatsapp",
                "message_id": message_id,
                "channel_id": channel_id,
                "sales_order": sales_order.name,
                "customer": customer.name,
                "mobile_number": mobile_number,
                "sender": sender,
                "body": content,
                "twilio_sid": sid,
            },
        )

        print(
            f"Raven -> WhatsApp successful: {sales_order.name} -> {mobile_number} -> {sid}"
        )
    except Exception:
        frappe.log_error(
            title="Raven Socket Message Forwarding Failed",
            message=frappe.get_traceback(),
        )
    finally:
        frappe.destroy()


def _subscribe_to_active_channels():
    """Subscribe Socket.IO to every currently active Raven channel."""
    channels = frappe.get_all(
        "Sales Order",
        filters={
            "custom_ticket_status": "In Progress",
            "docstatus": ["<", 2],
        },
        fields=["custom_raven_channel"],
    )
    seen = set()
    for row in channels:
        channel_id = row.custom_raven_channel
        if not channel_id or channel_id in seen:
            continue
        seen.add(channel_id)
        sio.emit(
            "doc_subscribe",
            ["Raven Channel", channel_id],
            namespace=RAVEN_NAMESPACE,
        )
        sio.emit(
            "doc_open",
            ["Raven Channel", channel_id],
            namespace=RAVEN_NAMESPACE,
        )
        print("Subscribed to Raven Channel:", channel_id)


import frappe
from urllib.parse import urlencode

import frappe
import socketio

sio = socketio.Client()

@sio.event(namespace="/")
def connect():
    print("Connected to Socket.IO! Joining room:", FRAPPE_SITE)
    # Join the site room so Frappe routes events to this client
    sio.emit("subscribe_site", FRAPPE_SITE, namespace="/")

@sio.on("*", namespace="/")
def catch_all(event, data):
    """Catch-all handler to debug all incoming socket events."""
    print(f"Received Event: {event} -> {data}")

# Specific handler for your Raven outbound event
@sio.on("raven_message", namespace="/")  # Replace 'raven_message' with your exact event name
def handle_outbound_message(data):
    print("Captured Outbound Message:", data)
    # Trigger your Meta/WhatsApp API request here

def start_socket_listener(site: str | None = None):
    global FRAPPE_SITE
    FRAPPE_SITE = site or frappe.local.site or "site1.local"

    user = frappe.get_doc("User", "Administrator")
    api_key = user.api_key or frappe.generate_hash(length=15)
    if not user.api_key:
        user.api_key = api_key
        user.save(ignore_permissions=True)

    api_secret = user.get_password("api_secret") or frappe.generate_hash(length=15)
    if not user.get_password("api_secret"):
        user.api_secret = api_secret
        frappe.db.set_value("User", "Administrator", "api_secret", api_secret)
    frappe.db.commit()

    socketio_port = frappe.conf.get("socketio_port") or 9000
    socket_url = f"http://127.0.0.1:{socketio_port}"

    sio.connect(
        socket_url,
        namespaces=["/"],
        transports=["websocket"],
        headers={
            "Authorization": f"token {api_key}:{api_secret}",
            "Origin": f"http://{FRAPPE_SITE}:8000",
            "Host": FRAPPE_SITE,
            "X-Frappe-Site-Name": FRAPPE_SITE,
        },
    )
    sio.wait()

