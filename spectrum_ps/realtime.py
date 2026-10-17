import frappe


def publish_message(event: str, *, direction: str, message: dict, user: str | None = None) -> None:
    """Publish a message to Frappe realtime subscribers."""
    frappe.publish_realtime(event, message={"direction": direction, **message}, user=user)
