import frappe
from frappe.utils import strip_html

from ..utils import get_cached_doc_or_none


def _as_chat_ticket(so_doc, todo_doc):
	return {
		"id": so_doc.name,
		"title": so_doc.custom_notes,
		"customerName": so_doc.customer,
		"customerAddress": strip_html(so_doc.address_display) if so_doc.address_display is not None else None,
		"customerAddressFull": {},
		"creation": so_doc.creation,
		"conversationId": so_doc.custom_raven_channel,
		"status": so_doc.custom_ticket_status,
		"assignedTo": todo_doc.allocated_to if todo_doc is not None else None,
		"assignedTimestamp": todo_doc.creation if todo_doc is not None else None,
	}



@frappe.whitelist(methods=["GET"])
def assigned_tickets():
	current_user = frappe.session.user
	tickets = []

	for so_doc in frappe.get_all(
		"Sales Order",
		filters=[["_assign", "like", "%{}%".format(current_user)], ["custom_raven_channel", "is", "set"]],
		order_by="creation desc",
		pluck="name",
	):
		doc = frappe.get_cached_doc("Sales Order", so_doc)
		todo = get_cached_doc_or_none("ToDo", {"reference_type": "Sales Order", "reference_name": so_doc})
		tickets.append(_as_chat_ticket(doc, todo))

	return tickets


@frappe.whitelist(methods=["GET"])
def ticket(ticket_id: str):
	doc = frappe.get_cached_doc("Sales Order", ticket_id)
	todo = get_cached_doc_or_none("ToDo", {"reference_type": "Sales Order", "reference_name": ticket_id})

	return _as_chat_ticket(doc, todo)
