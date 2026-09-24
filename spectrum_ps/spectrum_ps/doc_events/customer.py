import frappe
from frappe import _


def _get_bot_id(doc: "Customer"):
	return f"customer - {doc.name}"


def create_customer_bot(doc: "Customer", method):
	"""called when the customer is inserted or updated"""

	# If the customer is already added to Raven Bot, do nothing.
	bot_id = _get_bot_id(doc)

	if frappe.db.exists("Raven Bot", {"name": bot_id}):
		# Check if this Customer has been linked to the bot
		if doc.custom_raven_bot != bot_id:
			frappe.log("Assigning Existing bot account `%s` to customer `%s`" % (bot_id, doc.name))
			doc.custom_raven_bot = bot_id
			doc.save(ignore_permissions=True)
	else:
		# Raven bot does not exist.
		# Only create raven bot if it exists in the system.
		if frappe.db.exists("Customer", doc.name):
			# Create a Raven Bot record for the customer.
			raven_bot = frappe.new_doc("Raven Bot")
			raven_bot.bot_name = bot_id
			raven_bot.insert(ignore_permissions=True)
			doc.custom_raven_bot = bot_id
			# TODO: Rename raven_bot's raven_user full name to be doc.customer_name
			doc.save(ignore_permissions=True)


def remove_customer_bot(doc: "Customer", method):
	"""called when the customer is deleted"""

	bot_id = _get_bot_id(doc)

	# If the customer is deleted, then delete the Raven Bot record for the customer.
	if frappe.db.exists("Raven Bot", {"name": bot_id}):
		raven_bot = frappe.get_doc("Raven Bot", {"name": bot_id})
		raven_bot.delete(ignore_permissions=True)
