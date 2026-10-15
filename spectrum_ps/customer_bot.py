import frappe
from frappe import _

from spectrum_ps.config.free_form_messages import TICKET_DETAILS_MESSAGE
from spectrum_ps.utils import get_cached_doc_or_none

from .exceptions import NoActiveSalesOrdersException
from .messaging import get_active_sales_order_for_customer, get_customer_by_whatsapp


def get_customer_recent_so(customer):
	try:
		return frappe.get_last_doc("Sales Order", {"customer": customer.name})
	except frappe.DoesNotExistError:
		pass


def get_raven_channel_and_sales_order(sender_phone: str):
	"""Resolve WhatsApp sender -> Customer -> active Sales Order -> Raven Channel."""
	customer = get_customer_by_whatsapp(sender_phone)

	so = get_active_sales_order_for_customer(customer)

	if not so:
		raise NoActiveSalesOrdersException(customer)
		# TODO: This should be sent as a message to Twilio, same user, as a reply
		# frappe.throw(_("Customer {0} has no active In Progress Sales Order.").format(customer.name))

	channel_id = so.custom_raven_channel
	if not channel_id:
		# TODO: Log it properly. This error gets sent to Twilio
		frappe.throw(_("Sales Order {0} has no Raven Channel.").format(so.name))

	return channel_id, so.name, customer


# Customer Bot
def handle_incoming_message(form_data, customer) -> str | None:
	if (btn_action := form_data.get("ButtonPayload")) is not None:
		match btn_action:
			case "btn_order_greet_show_more":
				# TODO: Handle this better. For now I'm just getting the most recent SO.
				# What we can actually do is get which message is the reply,
				# find it in the outbound list, and use the referenced doc of that.
				if (latest_so := get_customer_recent_so(customer)) is not None:
					address_doc = (
						get_cached_doc_or_none("Address", latest_so.customer_address)
						if latest_so.customer_address is not None
						else None
					)

					work_type = " / ".join(item.item_name for item in latest_so.items if item.item_name)

					address = (
						", ".join(
							part
							for part in (
								address_doc.address_line1,
								address_doc.city,
								address_doc.state,
								address_doc.country,
							)
							if part
						)
						if address_doc is not None
						else ""
					)

					return TICKET_DETAILS_MESSAGE.format(
						service_type=work_type,
						location=address,
					)
				else:
					# TODO: This should not happen
					return "Sorry! You currently don't have any active Tickets. If this is a mistake, please contact us."
			case "btn_order_technician_assigned_continue":
				pass
			case "btn_reach_out_continue":
				pass
