import frappe
from frappe import _


def _get_bot_id(doc):
	return f"customer - {doc.name}"


def create_customer_bot(doc, method=None):
	"""Ensure every Customer has exactly one Raven Bot."""
	bot_id = _get_bot_id(doc)

	if not frappe.db.exists("Raven Bot", bot_id):
		raven_bot = frappe.new_doc("Raven Bot")
		raven_bot.bot_name = bot_id
		raven_bot.insert(ignore_permissions=True)

	if doc.custom_raven_bot != bot_id:
		doc.db_set("custom_raven_bot", bot_id)

	# Raven Bot may populate raven_user after its own save/update.
	if frappe.db.exists("Raven Bot", bot_id):
		sync_customer_raven_user(frappe.get_doc("Raven Bot", bot_id))


def sync_customer_raven_user(doc, method=None):
	"""Keep the linked Raven User's display name aligned with the Customer."""
	customer = frappe.db.get_value(
		"Customer",
		{"custom_raven_bot": doc.name},
		["customer_name", "first_name"],
		as_dict=True,
	)
	if not customer:
		return

	raven_user_name = frappe.db.get_value("Raven Bot", doc.name, "raven_user")
	if not raven_user_name:
		# Do not fail Customer creation if Raven has not populated the user yet.
		frappe.logger().warning(
			"Raven Bot %s has no linked Raven User yet", doc.name
		)
		return

	raven_user = frappe.get_doc("Raven User", raven_user_name)
	changed = False
	if raven_user.full_name != customer.customer_name:
		raven_user.full_name = customer.customer_name
		changed = True
	if raven_user.first_name != customer.first_name:
		raven_user.first_name = customer.first_name
		changed = True
	if changed:
		raven_user.save(ignore_permissions=True)


def remove_customer_bot(doc, method=None):
	bot_id = _get_bot_id(doc)
	if frappe.db.exists("Raven Bot", bot_id):
		frappe.get_doc("Raven Bot", bot_id).delete(ignore_permissions=True)
