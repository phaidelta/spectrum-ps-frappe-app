import frappe
from frappe import _

from spectrum_ps.spectrum_ps.utils import as_user
from spectrum_ps.utils import get_doc_or_none

from .exceptions import NonExistentCustomerError

excluded_statuses = ["Cancelled", "Completed"]

logger = frappe.logger("spectrum_ps", allow_site=True, file_count=50)


def normalize_whatsapp_number(value: str) -> str:
	value = (value or "").strip()
	if value.startswith("whatsapp:"):
		value = value[len("whatsapp:") :]
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
		raise NonExistentCustomerError(_("Customer with mobile number {0} does not exist").format(phone))

	return frappe.get_doc("Customer", name)


def get_active_sales_order_for_customer(customer):
	"""Return the current In Progress Sales Order for a Customer."""

	logger.info("Customer `%s` Sales Order mapping search..." % customer.name)

	# Check for active ticket in customer if it exists
	active_so_name = customer.custom_active_sales_order
	if active_so_name is not None:
		logger.info("Trying to find if customer has any active Sales Orders")
		active_so = get_doc_or_none(
			"Sales Order",
			active_so_name,
			filters={"docstatus": ["<", 2], "custom_ticket_status": ["not in", excluded_statuses]},
		)
		if active_so is not None:
			return active_so
		else:
			logger.info("Didn't find any active Sales Orders")
	else:
		logger.info("Customer document doesn't have a linked Sales Order")

	# Customer has no active ticket, or no ticket has been set. So find a sales order linked to them
	orders = frappe.get_all(
		"Sales Order",
		filters={
			"customer": customer.name,
			"docstatus": ["<", 2],
			"custom_ticket_status": ["not in", excluded_statuses],
		},
		fields=["name", "customer", "custom_ticket_status", "custom_raven_channel"],
		order_by="modified desc",
		limit=2,  # HACK: To @Aswin: Why 2?
	)

	if not orders:
		return

	if len(orders) > 1:
		logger.warning(
			"Customer %s has multiple active Sales Orders: %s",
			customer.name,
			", ".join(order.name for order in orders),
		)

	# Choose one of them and save in customer
	chosen_so = orders[0]
	customer.custom_active_sales_order = chosen_so.name

	with as_user():
		customer.save(ignore_permissions=True)

	return chosen_so


def get_sales_order_by_raven_channel(channel_id: str):
	"""Resolve a Raven Channel to its active Sales Order."""
	if not channel_id:
		return None

	orders = frappe.get_all(
		"Sales Order",
		filters={
			"custom_raven_channel": channel_id,
			"custom_ticket_status": ["not in", excluded_statuses],
			"docstatus": ["<", 2],
		},
		fields=["name", "customer", "custom_ticket_status", "custom_raven_channel"],
		limit=1,
	)
	return orders[0] if orders else None
