import frappe
from frappe import _


def _get_bot_id(doc):
	return f"customer - {doc.name}"


def create_customer_bot(doc, method):
	"""called when the customer is inserted or updated"""

	bot_id = _get_bot_id(doc)
	frappe.log(f"Ensuring Raven Bot `{bot_id}` exists for Customer `{doc.name}`")

	if frappe.db.exists("Raven Bot", {"name": bot_id}):
		if doc.custom_raven_bot != bot_id:
			frappe.log(f"Linking existing Raven Bot `{bot_id}` to Customer `{doc.name}`")
			doc.custom_raven_bot = bot_id
			doc.save(ignore_permissions=True)
			sync_customer_raven_user(frappe.get_doc("Raven Bot", bot_id))
		else:
			frappe.log(f"Customer `{doc.name}` is already linked to Raven Bot `{bot_id}`")
	else:
		if frappe.db.exists("Customer", doc.name):
			frappe.log(f"Creating Raven Bot `{bot_id}` for Customer `{doc.name}`")
			raven_bot = frappe.new_doc("Raven Bot")
			raven_bot.bot_name = bot_id
			raven_bot.insert(ignore_permissions=True)
			doc.custom_raven_bot = bot_id
			doc.save(ignore_permissions=True)
			sync_customer_raven_user(raven_bot)
		else:
			frappe.log(f"Customer `{doc.name}` does not exist while creating its Raven Bot")
			frappe.throw(_("Customer {0} must exist before its Raven Bot can be created.").format(doc.name))


def sync_customer_raven_user(doc, method=None):
	"""Keep a Customer's Raven User name aligned after Raven updates its bot."""
	customer = frappe.db.get_value(
		"Customer",
		{"custom_raven_bot": doc.name},
		["customer_name", "first_name"],
		as_dict=True,
	)
	if not customer:
		frappe.log(f"Raven Bot `{doc.name}` is not linked to a Customer")
		return

	raven_user_name = frappe.db.get_value("Raven Bot", doc.name, "raven_user")
	if not raven_user_name:
		frappe.log(f"Raven Bot `{doc.name}` has no linked Raven User")
		frappe.throw(_("Raven Bot {0} must have a linked Raven User.").format(doc.name))

	frappe.log(f"Synchronizing Raven User `{raven_user_name}` for Customer `{customer.customer_name}`")
	raven_user = frappe.get_doc("Raven User", raven_user_name)
	if raven_user.full_name == customer.customer_name and raven_user.first_name == customer.first_name:
		return

	raven_user.full_name = customer.customer_name
	raven_user.first_name = customer.first_name
	raven_user.save(ignore_permissions=True)
	frappe.log(f"Updated Raven User `{raven_user.name}` for Customer `{customer.customer_name}`")


def remove_customer_bot(doc, method):
	"""called when the customer is deleted"""

	bot_id = _get_bot_id(doc)

	if frappe.db.exists("Raven Bot", {"name": bot_id}):
		frappe.log(f"Removing Raven Bot `{bot_id}` for deleted Customer `{doc.name}`")
		raven_bot = frappe.get_doc("Raven Bot", {"name": bot_id})
		raven_bot.delete(ignore_permissions=True)
	else:
		frappe.log(f"No Raven Bot found to remove for deleted Customer `{doc.name}`")
