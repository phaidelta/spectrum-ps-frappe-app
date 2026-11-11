import frappe
from frappe import _

from spectrum_ps.config.free_form_messages import TICKET_DETAILS_MESSAGE
from spectrum_ps.utils import get_cached_doc_or_none

from .exceptions import NoActiveSalesOrdersException
from .messaging import get_active_sales_order_for_customer, get_customer_by_whatsapp


def get_sales_order_by_twilio_sid(message_sid: str, customer):
	"""Return the Sales Order associated with the original outbound WhatsApp message."""

	if not message_sid:
		return None

	sales_order_name = frappe.db.get_value(
		"Customer Message Outbound Queue",
		{"twilio_message_sid": message_sid},
		"sales_order",
	)

	if not sales_order_name:
		return None

	sales_order = get_cached_doc_or_none("Sales Order", sales_order_name)

	# Do not disclose a Sales Order belonging to another customer.
	if not sales_order or sales_order.customer != customer.name:
		return None

	return sales_order


def get_raven_channel_and_sales_order(sender_phone: str):
	"""Resolve WhatsApp sender -> Customer -> active Sales Order -> Raven Channel."""
	customer = get_customer_by_whatsapp(sender_phone)

	so = get_active_sales_order_for_customer(customer)

	if not so:
		raise NoActiveSalesOrdersException(customer)

	channel_id = so.custom_raven_channel
	if not channel_id:
		frappe.throw(_("Sales Order {0} has no Raven Channel.").format(so.name))

	return channel_id, so.name, customer


def handle_incoming_message(form_data, customer) -> str | None:
	"""Handle supported WhatsApp button replies."""

	if (btn_action := form_data.get("ButtonPayload")) is None:
		return None

	match btn_action:
		case "btn_order_greet_show_more":
			# Twilio supplies the SID of the outbound message being replied to.
			original_message_sid = form_data.get("OriginalRepliedMessageSid")

			sales_order = get_sales_order_by_twilio_sid(
				original_message_sid,
				customer,
			)

			if not sales_order:
				return (
					"Sorry! We couldn't identify the original ticket. "
					"Please contact us if you need assistance."
				)

			address_doc = (
				get_cached_doc_or_none("Address", sales_order.customer_address)
				if sales_order.customer_address
				else None
			)

			work_type = " / ".join(item.item_name for item in sales_order.items if item.item_name)

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
				if address_doc
				else ""
			)

			return TICKET_DETAILS_MESSAGE.format(
				service_type=work_type,
				location=address,
			)

		case "btn_order_technician_assigned_continue":
			return None

		case "btn_reach_out_continue":
			return None

	return None
