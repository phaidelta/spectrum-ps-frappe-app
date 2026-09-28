import re

import frappe

from .integrations.raven import RavenClient
from .integrations.twilio import send_whatsapp_message
from .integrations.config import require_setting


def get_channel_id():
    return require_setting("raven_channel_id")


def get_bot_user():
    return (
        frappe.conf.get("raven_bot_user")
        or "bot@phaidelta.com"
    )


def get_whatsapp_customer_number():
    return require_setting("whatsapp_customer_number")


def clean_raven_message(message):
    content = (
        message.get("content")
        or message.get("text")
        or ""
    )

    if not content:
        return ""

    content = re.sub(
        r"<[^>]+>",
        "",
        str(content),
    )

    return content.strip()


def get_message_timestamp(message):
    return message.get("creation") or ""


def get_message_id(message):
    return message.get("name") or ""


def is_message_from_bot(message):
    bot_user = get_bot_user()

    owner = (
        message.get("owner")
        or ""
    ).strip()

    return owner.lower() == bot_user.lower()


def get_new_messages(messages):
    last_timestamp = frappe.cache().get_value(
        "spectrum_ps:raven:last_message_timestamp"
    )

    last_message_id = frappe.cache().get_value(
        "spectrum_ps:raven:last_message_id"
    )

    new_messages = []

    for message in messages:
        creation = get_message_timestamp(message)
        message_id = get_message_id(message)

        if not creation:
            continue

        if not last_timestamp:
            continue

        if creation > last_timestamp:
            new_messages.append(message)
            continue

        if (
            creation == last_timestamp
            and message_id
            and message_id != last_message_id
        ):
            new_messages.append(message)

    return new_messages


def update_cursor(message):
    creation = get_message_timestamp(message)
    message_id = get_message_id(message)

    if creation:
        frappe.cache().set_value(
            "spectrum_ps:raven:last_message_timestamp",
            creation,
        )

    if message_id:
        frappe.cache().set_value(
            "spectrum_ps:raven:last_message_id",
            message_id,
        )


def initialize_cursor(messages):
    if not messages:
        return

    sorted_messages = sorted(
        messages,
        key=lambda message: (
            get_message_timestamp(message),
            get_message_id(message),
        ),
    )

    latest = sorted_messages[-1]

    update_cursor(latest)

    frappe.logger().info(
        "Raven listener initialized at message %s",
        get_message_id(latest),
    )


def poll_raven_messages():

    frappe.log_error(
        title="RAVEN POLLING TEST",
        message="poll_raven_messages() was executed by scheduler"
    )

    frappe.logger().info(
        "===== RAVEN POLLING JOB STARTED ====="
    )

    channel_id = get_channel_id()

    raven = RavenClient()

    try:
        response = raven.get_messages(
            channel=channel_id
        )
    except Exception:
        frappe.log_error(
            title="Raven Polling Failed",
            message=frappe.get_traceback(),
        )
        return

    messages = (
        response.get("message", {})
        .get("messages", [])
    )

    if not messages:
        return

    last_timestamp = frappe.cache().get_value(
        "spectrum_ps:raven:last_message_timestamp"
    )

    if not last_timestamp:
        initialize_cursor(messages)
        return

    new_messages = get_new_messages(messages)

    if not new_messages:
        return

    new_messages = sorted(
        new_messages,
        key=lambda message: (
            get_message_timestamp(message),
            get_message_id(message),
        ),
    )

    customer_number = get_whatsapp_customer_number()

    for message in new_messages:
        message_id = get_message_id(message)

        if is_message_from_bot(message):
            update_cursor(message)

            frappe.logger().info(
                "Skipping Raven bot message: %s",
                message_id,
            )

            continue

        text = clean_raven_message(message)

        if not text:
            update_cursor(message)
            continue

        try:
            sid = send_whatsapp_message(
                to=customer_number,
                body=text,
            )

            frappe.logger().info(
                "Raven -> WhatsApp successful: "
                "message=%s sid=%s",
                message_id,
                sid,
            )

            update_cursor(message)

        except Exception:
            frappe.log_error(
                title="Raven to WhatsApp Failed",
                message=(
                    f"Raven Message: {message_id}\n"
                    f"Text: {text}\n"
                    f"Customer: {customer_number}\n\n"
                    f"{frappe.get_traceback()}"
                ),
            )
            return
