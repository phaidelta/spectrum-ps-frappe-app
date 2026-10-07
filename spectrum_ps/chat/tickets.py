import frappe

from ..utils import get_doc_or_none


@frappe.whitelist(methods=["GET"])
def assigned_tickets():
	current_user = frappe.session.user
	tickets = []

	for so_doc in frappe.get_all(
		"Sales Order",
		filters=[["_assign", "like", "%{}%".format(current_user)], ["custom_raven_channel", "is", "set"]],
		pluck="name",
	):
		doc = frappe.get_doc("Sales Order", so_doc)
		todo = get_doc_or_none("ToDo", {"reference_type": "Sales Order", "reference_name": so_doc})
		tickets.append(
			{
				"id": doc.name,
				"title": doc.custom_notes,
				"customerName": doc.customer,
				"creation": doc.creation,
				"conversationId": doc.custom_raven_channel,
				"status": doc.custom_ticket_status,
				"todo": todo.as_dict() if todo is not None else None,
			}
		)

	return tickets
