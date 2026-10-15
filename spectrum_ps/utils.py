import frappe


def get_doc_or_none(*args, **kwargs):
	try:
		return frappe.get_doc(*args, **kwargs)
	except frappe.DoesNotExistError:
		pass

def get_cached_doc_or_none(*args, **kwargs):
	try:
		return frappe.get_cached_doc(*args, **kwargs)
	except frappe.DoesNotExistError:
		pass


def enqueue_outbound_sales_order_whatsapp_template(sales_order_name, customer_name, message_id, template_id, content_variables):
	"""
	Small helper method to create an outbound message using Twilio template specifically for Sales Order messages
	"""

	frappe.enqueue(
		"spectrum_ps.spectrum_ps.doc_events.raven_message.deliver_template_message_to_whatsapp",
		queue="short",
		enqueue_after_commit=True,
		# Parameters
		message_id=message_id,
		sales_order=sales_order_name,
		customer=customer_name,
		template_id=template_id,
		content_variables=content_variables,
	)
