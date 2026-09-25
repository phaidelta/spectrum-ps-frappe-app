import frappe
from frappe import _


def _get_bot_id(doc):
	return f"customer - {doc.name}"


def create_customer_bot(doc, method):
	"""called when the customer is inserted or updated"""

	# If the customer is already added to Raven Bot, do nothing.
	bot_id = _get_bot_id(doc)

	if frappe.db.exists("Raven Bot", {"name": bot_id}):
		# Check if this Customer has been linked to the bot
		if doc.custom_raven_bot != bot_id:
			frappe.log("Assigning Existing bot account `%s` to customer `%s`" % (bot_id, doc.name))
			doc.custom_raven_bot = bot_id
			doc.save(ignore_permissions=True)
			sync_customer_raven_user(frappe.get_doc("Raven Bot", bot_id))
	else:
		# Raven bot does not exist.
		# Only create raven bot if it exists in the system.
		if frappe.db.exists("Customer", doc.name):
			# Create a Raven Bot record for the customer.
			raven_bot = frappe.new_doc("Raven Bot")
			raven_bot.bot_name = bot_id
			raven_bot.insert(ignore_permissions=True)
			doc.custom_raven_bot = bot_id
			doc.save(ignore_permissions=True)
			sync_customer_raven_user(raven_bot)


def sync_customer_raven_user(doc, method=None):
	"""Keep a Customer's Raven User name aligned after Raven updates its bot."""
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
		return

	raven_user = frappe.get_doc("Raven User", raven_user_name)
	if raven_user.full_name == customer.customer_name and raven_user.first_name == customer.first_name:
		return

	raven_user.full_name = customer.customer_name
	raven_user.first_name = customer.first_name
	raven_user.save(ignore_permissions=True)


def remove_customer_bot(doc, method):
	"""called when the customer is deleted"""

	bot_id = _get_bot_id(doc)

	# If the customer is deleted, then delete the Raven Bot record for the customer.
	if frappe.db.exists("Raven Bot", {"name": bot_id}):
		raven_bot = frappe.get_doc("Raven Bot", {"name": bot_id})
		raven_bot.delete(ignore_permissions=True)
