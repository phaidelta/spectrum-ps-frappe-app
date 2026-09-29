import frappe
from frappe import _

from ..utils import ignore_permissions


def create_raven_channel(doc: "Sales Order", method=None):
	"""Create one Raven Channel per Sales Order and add the Customer Bot."""
	if not doc.customer:
		frappe.throw(
			_("Sales Order {0} must have a Customer before creating its Raven Channel.").format(doc.name)
		)

	customer = frappe.get_cached_doc("Customer", doc.customer)
	if not customer.custom_raven_bot:
		frappe.throw(
			_("Customer {0} must have a Raven Bot before creating a Sales Order.").format(customer.name)
		)

	workspace = "Customer communications"
	existing = frappe.db.exists(
		"Raven Channel",
		{"channel_name": doc.name, "workspace": workspace},
	)

	if existing:
		raven_channel = frappe.get_doc("Raven Channel", existing)
	else:
		raven_channel = frappe.get_doc({
			"doctype": "Raven Channel",
			"workspace": workspace,
			"channel_name": doc.name,
			"type": "Public",
		})
		raven_channel.insert(ignore_permissions=True)

	if doc.custom_raven_channel != raven_channel.name:
		doc.db_set("custom_raven_channel", raven_channel.name)

	bot = frappe.get_cached_doc("Raven Bot", customer.custom_raven_bot)
	with ignore_permissions():
		if not frappe.db.exists(
			"Raven Channel Member",
			{"channel_id": raven_channel.name, "user_id": bot.raven_user},
		):
			bot.add_to_channel(raven_channel.name)


def remove_raven_channel(doc: "Sales Order", method=None):
	channel_name = getattr(doc, "custom_raven_channel", None)
	if channel_name and frappe.db.exists("Raven Channel", channel_name):
		frappe.get_doc("Raven Channel", channel_name).delete(ignore_permissions=True)
