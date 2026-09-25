import frappe


def add_assigned_user(doc, method=None):
	if doc.reference_type != "Sales Order" or not doc.allocated_to:
		return

	assigned_to = doc.allocated_to
	user = frappe.get_cached_doc("Raven User", assigned_to)
	sales_order = frappe.get_cached_doc(doc.reference_type, doc.reference_name)

	if not user or not sales_order.custom_raven_channel:
		return

	if sales_order.custom_ticket_status == "New":
		sales_order.custom_ticket_status = "Assigned"
		sales_order.save(ignore_permissions=True)

	frappe.call(
		"raven.api.raven_channel_member.add_channel_members",
		channel_id=sales_order.custom_raven_channel,
		members=[assigned_to],
	)


def remove_assigned_user(doc, method=None):
	if doc.reference_type != "Sales Order" or not doc.allocated_to:
		return

	assigned_to = doc.allocated_to
	user = frappe.get_cached_doc("Raven User", assigned_to)
	sales_order = frappe.get_cached_doc(doc.reference_type, doc.reference_name)

	if not user or not sales_order.custom_raven_channel:
		return

	frappe.call(
		"raven.api.raven_channel_member.remove_channel_member",
		user_id=assigned_to,
		channel_id=sales_order.custom_raven_channel,
	)


def remove_assigned_user_on_cancel(doc, method=None):
	if doc.status == "Cancelled":
		remove_assigned_user(doc, method)


def remove_assigned_user_on_trash(doc, method=None):
	if doc.status != "Cancelled":
		remove_assigned_user(doc, method)
