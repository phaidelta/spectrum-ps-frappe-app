import frappe
from frappe import _

from spectrum_ps.config.action_users import SYSTEM_MANAGER_USER
from spectrum_ps.context_managers import as_user


def _get_bot_id(doc):
	return f"{doc.name} (Customer)"


def create_customer_bot(doc, method):
	"""called when the customer is inserted or updated"""

	bot_id = _get_bot_id(doc)
	frappe.log(f"Ensuring Raven Bot `{bot_id}` exists for Customer `{doc.name}`")

	with as_user(SYSTEM_MANAGER_USER):
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
				frappe.throw(
					_("Customer {0} must exist before its Raven Bot can be created.").format(doc.name)
				)


def sync_customer_raven_user(doc, method=None):
	"""Keep a Customer's Raven User name aligned after Raven updates its bot."""

	with as_user(SYSTEM_MANAGER_USER):
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

	bot_id = doc.custom_raven_bot

	with as_user(SYSTEM_MANAGER_USER):
		if frappe.db.exists("Raven Bot", {"name": bot_id}):
			frappe.log(f"Removing Raven Bot `{bot_id}` for deleted Customer `{doc.name}`")
			raven_bot = frappe.get_doc("Raven Bot", {"name": bot_id})
			raven_bot.delete(ignore_permissions=True)
			doc.custom_raven_bot = None
			doc.save(ignore_permissions=True)
		else:
			frappe.log(f"No Raven Bot found to remove for deleted Customer `{doc.name}`")


def notify_active_sales_order_changed(doc, method=None):
	before = doc.get_doc_before_save()
	previous_sales_order = before.get("custom_active_sales_order") if before else None
	new_sales_order = doc.get("custom_active_sales_order")

	if (
		not isinstance(previous_sales_order, str)
		or not previous_sales_order
		or not isinstance(new_sales_order, str)
		or not new_sales_order
		or previous_sales_order == new_sales_order
	):
		return

	frappe.enqueue(
		"spectrum_ps.spectrum_ps.doc_events.customer.send_active_sales_order_changed_messages",
		queue="short",
		enqueue_after_commit=True,
		customer=doc.name,
		previous_sales_order=previous_sales_order,
		new_sales_order=new_sales_order,
	)


def send_active_sales_order_changed_messages(customer, previous_sales_order, new_sales_order):
	with as_user(SYSTEM_MANAGER_USER):
		customer_doc = frappe.get_doc("Customer", customer)
		previous_order_doc = frappe.get_doc("Sales Order", previous_sales_order)
		new_order_doc = frappe.get_doc("Sales Order", new_sales_order)
		customer_name = customer_doc.customer_name or customer_doc.name

		previous_channel = previous_order_doc.get("custom_raven_channel")
		new_channel = new_order_doc.get("custom_raven_channel")
		if not previous_channel or not new_channel:
			frappe.log_error(
				title="Active Sales Order channel change: missing Raven channel",
				message=(
					f"Customer: {customer}\n"
					f"Previous Sales Order: {previous_sales_order} (channel: {previous_channel})\n"
					f"New Sales Order: {new_sales_order} (channel: {new_channel})"
				),
			)
			return

		message_data = {
			"event": "custom_active_channel_changed",
			"customer": customer,
			"previous_sales_order": previous_sales_order,
			"new_sales_order": new_sales_order,
		}
		for channel, text in (
			(
				previous_channel,
				f"This is no longer the active channel for customer {customer_name}. "
				f"Switch to {new_sales_order}.",
			),
			(new_channel, f"This is now the active channel for customer {customer_name}."),
		):
			frappe.get_doc(
				{
					"doctype": "Raven Message",
					"channel_id": channel,
					"message_type": "System",
					"text": text,
					"json": frappe.as_json(message_data),
				}
			).insert(ignore_permissions=True)
