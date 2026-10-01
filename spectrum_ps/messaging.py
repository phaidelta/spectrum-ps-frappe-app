import frappe
from frappe import _


def normalize_whatsapp_number(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("whatsapp:"):
        value = value[len("whatsapp:"):]
    return value


def get_customer_by_whatsapp(mobile_number: str):
    """Resolve a WhatsApp sender to a Frappe Customer."""
    phone = normalize_whatsapp_number(mobile_number)
    variants = [phone, phone.lstrip("+")]
    if phone:
        variants.append(f"whatsapp:{phone}")

    name = frappe.db.get_value(
        "Customer",
        {"mobile_no": ["in", list(dict.fromkeys(variants))]},
        "name",
    )
    if not name:
        frappe.throw(
            _("Customer with mobile number {0} does not exist").format(phone)
        )
    return frappe.get_doc("Customer", name)


def get_active_sales_order_for_customer(customer_name: str):
    """Return the current In Progress Sales Order for a Customer."""
    orders = frappe.get_all(
        "Sales Order",
        filters={
            "customer": customer_name,
            # "custom_ticket_status": "In Progress",
            "docstatus": ["<", 2],
        },
        fields=["name", "customer", "custom_ticket_status", "custom_raven_channel"],
        order_by="modified desc",
        limit=2,
    )
    if not orders:
        return None
    if len(orders) > 1:
        frappe.logger().warning(
            "Customer %s has multiple In Progress Sales Orders: %s",
            customer_name,
            ", ".join(order.name for order in orders),
        )
    return orders[0]


def get_sales_order_by_raven_channel(channel_id: str):
    """Resolve a Raven Channel to its active Sales Order."""
    if not channel_id:
        return None
    orders = frappe.get_all(
        "Sales Order",
        filters={
            "custom_raven_channel": channel_id,
            "custom_ticket_status": "In Progress",
            "docstatus": ["<", 2],
        },
        fields=["name", "customer", "custom_ticket_status", "custom_raven_channel"],
        limit=1,
    )
    return orders[0] if orders else None
