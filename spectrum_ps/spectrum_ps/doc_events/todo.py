import frappe
from frappe import _


def add_assigned_user(doc, method=None):
	if doc.reference_type != "Sales Order" or not doc.allocated_to:
		return

	assigned_to = doc.allocated_to
	frappe.log(f"Adding ToDo assignee `{assigned_to}` to Sales Order Raven Channel")
	if not frappe.db.exists("Raven User", assigned_to):
		frappe.log(f"Assigned user `{assigned_to}` is not a Raven User")
		frappe.throw(_("Assigned user {0} must have a Raven User before assignment.").format(assigned_to))

	user = frappe.get_cached_doc("Raven User", assigned_to)
	if not doc.reference_name or not frappe.db.exists("Sales Order", doc.reference_name):
		frappe.log(f"ToDo `{doc.name}` references missing Sales Order `{doc.reference_name}`")
		frappe.throw(_("ToDo {0} references a missing Sales Order.").format(doc.name))

	sales_order = frappe.get_cached_doc(doc.reference_type, doc.reference_name)

	if not sales_order.customer:
		frappe.log(f"Sales Order `{sales_order.name}` has no Customer linked")
		frappe.throw(_("Sales Order {0} must have a Customer linked.").format(sales_order.name))
	if not sales_order.custom_raven_channel:
		frappe.log(f"Sales Order `{sales_order.name}` has no Raven Channel linked")
		frappe.throw(_("Sales Order {0} must have a Raven Channel linked.").format(sales_order.name))

	if sales_order.custom_ticket_status == "New":
		frappe.log(f"Updating Sales Order `{sales_order.name}` ticket status to Assigned")
		sales_order.custom_ticket_status = "Assigned"
		sales_order.save(ignore_permissions=True)

	frappe.call(
		"raven.api.raven_channel_member.add_channel_members",
		channel_id=sales_order.custom_raven_channel,
		members=[assigned_to],
	)
	frappe.log(f"Added Raven User `{user.name}` to Channel `{sales_order.custom_raven_channel}`")


def remove_assigned_user(doc, method=None):
	if doc.reference_type != "Sales Order" or not doc.allocated_to:
		return

	assigned_to = doc.allocated_to
	frappe.log(f"Removing ToDo assignee `{assigned_to}` from Sales Order Raven Channel")
	if not frappe.db.exists("Raven User", assigned_to):
		frappe.log(f"Assigned user `{assigned_to}` is not a Raven User; nothing to remove")
		return

	user = frappe.get_cached_doc("Raven User", assigned_to)
	if not doc.reference_name or not frappe.db.exists("Sales Order", doc.reference_name):
		frappe.log(f"ToDo `{doc.name}` references missing Sales Order `{doc.reference_name}`")
		frappe.throw(_("ToDo {0} references a missing Sales Order.").format(doc.name))

	sales_order = frappe.get_cached_doc(doc.reference_type, doc.reference_name)

	if not sales_order.custom_raven_channel:
		frappe.log(f"Sales Order `{sales_order.name}` has no Raven Channel linked; nothing to remove")
		return

	frappe.call(
		"raven.api.raven_channel_member.remove_channel_member",
		user_id=assigned_to,
		channel_id=sales_order.custom_raven_channel,
	)
	frappe.log(f"Removed Raven User `{user.name}` from Channel `{sales_order.custom_raven_channel}`")


def remove_assigned_user_on_cancel(doc, method=None):
	if doc.status == "Cancelled":
		remove_assigned_user(doc, method)


def remove_assigned_user_on_trash(doc, method=None):
	if doc.status != "Cancelled":
		remove_assigned_user(doc, method)
