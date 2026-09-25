import frappe

from ..utils import ignore_permissions


def create_raven_channel(doc: "Sales Order", method=None):
	workspace = "Customer communications"
	channel_name = doc.name
	existing_channel_name = frappe.db.exists(
		"Raven Channel",
		{"channel_name": channel_name, "workspace": workspace},
	)

	if existing_channel_name:
		raven_channel = frappe.get_doc("Raven Channel", existing_channel_name)
	else:
		raven_channel = frappe.get_doc(
			{
				"doctype": "Raven Channel",
				"workspace": workspace,
				"channel_name": channel_name,
				"type": "Public",
			}
		)
		raven_channel.insert(ignore_permissions=True)

	doc.custom_raven_channel = raven_channel.name

	# <Owner>, i.e. creator of this doc automatically gets added to channel when created
	# https://github.com/frappe/raven/blob/fac2b927982cd2fb84c032715ebd6e4aafc9ea3f/raven/raven_channel_management/doctype/raven_channel/raven_channel.py#L150
	# TODO: Find all administrator accounts, add them all, or add a config to choose

	if not doc.customer:
		return

	# Add customer's bot to the channel (if present)
	customer = frappe.get_cached_doc("Customer", doc.customer)
	if not customer.custom_raven_bot:
		return

	bot_user = frappe.get_cached_doc("Raven Bot", customer.custom_raven_bot)

	with ignore_permissions():
		bot_user.add_to_channel(raven_channel.name)

	# TODO: Add Realtor's bot


def remove_raven_channel(doc: "Sales Order", method=None):
	channel_name = getattr(doc, "custom_raven_channel", None)
	if not channel_name or not frappe.db.exists("Raven Channel", channel_name):
		return

	frappe.get_doc("Raven Channel", channel_name).delete(ignore_permissions=True)
