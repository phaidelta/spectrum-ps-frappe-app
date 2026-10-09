import frappe
from frappe.utils import strip_html

from ..utils import get_cached_doc_or_none


def _as_chat_ticket(so_doc, address_doc, todo_doc):
	work_type = "/".join(item.item_code for item in so_doc.items if item.item_code)
	address = ", ".join(
		part for part in (address_doc.address_line1, address_doc.city) if part
	) if address_doc is not None else ""
	title = " - ".join(part for part in (work_type, so_doc.customer_name, address) if part)

	return {
		"id": so_doc.name,
		"title": title,
		"customerName": so_doc.customer,
		"customerAddress": {
			"address_title": address_doc.address_title,
			"address_type": address_doc.address_type,
			"address_line1": address_doc.address_line1,
			"address_line2": address_doc.address_line2,
			"city": address_doc.city,
			"state": address_doc.state,
			"country": address_doc.country,
			"pincode": address_doc.pincode,
		} if address_doc is not None else None,
		"customerAddressBrief": strip_html(so_doc.address_display) if so_doc.address_display is not None else None,
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
		address = get_cached_doc_or_none("Address", doc.customer_address) if doc.customer_address is not None else None
		todo = get_cached_doc_or_none("ToDo", {"reference_type": "Sales Order", "reference_name": so_doc})
		tickets.append(_as_chat_ticket(doc, address, todo))

	return tickets


@frappe.whitelist(methods=["GET"])
def ticket(ticket_id: str):
	doc = frappe.get_cached_doc("Sales Order", ticket_id)
	address = get_cached_doc_or_none("Address", doc.customer_address) if doc.customer_address is not None else None
	todo = get_cached_doc_or_none("ToDo", {"reference_type": "Sales Order", "reference_name": ticket_id})

	return _as_chat_ticket(doc, address, todo)
