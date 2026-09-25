import frappe


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

	if not doc.customer:
		return

	customer = frappe.get_cached_doc("Customer", doc.customer)
	if not customer.custom_raven_bot:
		return

	bot_user = frappe.get_cached_doc("Raven Bot", customer.custom_raven_bot)
	previous_ignore_permissions = getattr(frappe.flags, "ignore_permissions", False)
	frappe.flags.ignore_permissions = True
	try:
		bot_user.add_to_channel(raven_channel.name)
	finally:
		frappe.flags.ignore_permissions = previous_ignore_permissions


def remove_raven_channel(doc: "Sales Order", method=None):
	channel_name = getattr(doc, "custom_raven_channel", None)
	if not channel_name or not frappe.db.exists("Raven Channel", channel_name):
		return

	frappe.get_doc("Raven Channel", channel_name).delete(ignore_permissions=True)
