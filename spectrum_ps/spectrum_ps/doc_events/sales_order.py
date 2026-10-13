import frappe
from frappe import _

from spectrum_ps.spectrum_ps.doc_events.customer import create_customer_bot
from spectrum_ps.spectrum_ps.utils import as_user

CUSTOMER_WELCOME_MESSAGE = (
	"""Hello {customer_name}, your ticket {order_id} has been received by {company_name}."""
)

TEMPLATE_ORDER_GREETINGS = "HXf7b41ed33a0f6bf280b8aab4b9862b5c"

def _send_template(doc, template_id, message_id, content_variables):
	frappe.enqueue(
		"spectrum_ps.spectrum_ps.doc_events.raven_message.deliver_template_message_to_whatsapp",
		queue="short",
		enqueue_after_commit=True,
		message_id=message_id,
		sales_order=doc.name,
		customer=doc.customer,
		template_id = template_id,
		content_variables = content_variables
	)

def _get_customer_name(doc):
	return frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer


def handle_completed(doc):

	frappe.log(f"Sending Completion message to customer for {doc.name}..")
	_send_template(
		doc,
		template_id="HXc532e54549e0a4655f65fd379988a9f6",
		message_id=f"{doc.name}-Sale-Order-Completion-Message",
		content_variables={
		"customer_name": _get_customer_name(doc),
		"order_id": doc.name
	}
		)


def handle_accepted(doc):
	assigness = frappe.parse_json(frappe.db.get_value("Sales Order", doc.name, "_assign") or "[]")
	if not assigness:
		frappe.log(f"Sales Order `{doc.name}` accepted but has no assignee; skipping customer message")
		return

	technician = assigness[0]
	technician_name = frappe.db.get_value("User", technician, "full_name") or technician

	frappe.log(f"Sending Technician-assigned message to customer for {doc.name}..")
	_send_template(
		doc,
		template_id="HXdf7ccb428ee2161ee3c3e804c6a0c41e",
		message_id=f"{doc.name}-Sale-Order-Assignment-Message",
		content_variables={
		"customer_name": _get_customer_name(doc),
		"technician_name":technician_name,
		"order_id": doc.name
	}

		)


def bot_add_to_channel(bot, channel_id: str) -> str:
	"""
	Add the bot to a channel as a member

	If the bot is already a member of the channel, this function does nothing

	Returns the member_id of the bot in the channel
	"""

	existing_member = bot.is_member(channel_id)

	if not existing_member:
		raven_channel_member = frappe.get_doc(
			doctype="Raven Channel Member", user_id=bot.raven_user, channel_id=channel_id
		)
		raven_channel_member.insert(ignore_permissions=True)
		return raven_channel_member.name
	else:
		return existing_member


def ensure_customer_has_bot(customer):
	if not customer.custom_raven_bot:
		frappe.log(f"Customer `{customer.name}` has no linked Raven Bot. Creating...")
		create_customer_bot(customer, None)
		# frappe.throw(
		# 	_("Customer {0} must have a Raven Bot before creating a Sales Order.").format(customer.name)
		# )

	elif not frappe.db.exists("Raven Bot", customer.custom_raven_bot):
		frappe.log(
			f"Linked Raven Bot `{customer.custom_raven_bot}` does not exist for Customer `{customer.name}`. Creating..."
		)
		create_customer_bot(customer, None)
		# frappe.throw(
		# 	_("Raven Bot {0} linked to Customer {1} does not exist.").format(
		# 		customer.custom_raven_bot, customer.name
		# 	)
		# )

	return customer.custom_raven_bot


def create_raven_channel(doc, method=None):
	frappe.log(f"Creating or updating Raven channel for Sales Order `{doc.name}`")
	workspace = "Customer communications"
	channel_name = doc.name
	existing_channel_name = frappe.db.exists(
		"Raven Channel",
		{"channel_name": channel_name, "workspace": workspace},
	)

	if existing_channel_name:
		frappe.log(f"Using existing Raven Channel `{existing_channel_name}` for Sales Order `{doc.name}`")
		raven_channel = frappe.get_doc("Raven Channel", existing_channel_name)
	else:
		# TODO: Get the system manager user from config. This defaults to Administrator
		with as_user():
			frappe.log(f"Creating Raven Channel `{channel_name}` for Sales Order `{doc.name}`")
			raven_channel = frappe.get_doc(
				{
					"doctype": "Raven Channel",
					"workspace": workspace,
					"channel_name": channel_name,
					"type": "Public",
				}
			)
			raven_channel.insert(ignore_permissions=True)

	# TODO: Get the system manager user from config. This defaults to Administrator
	with as_user():
		frappe.log(f"Linking raven channel {raven_channel.name} to Sales Order {doc.name}")
		doc.custom_raven_channel = raven_channel.name
		doc.save(ignore_permissions=True)

	# Add administrator to the channel
	# TODO: Add from a preset list or using some heuristic
	ADMIN_USER = "Administrator"
	if not frappe.db.exists(
		"Raven Channel Member", {"channel_id": raven_channel.name, "user_id": ADMIN_USER}
	):
		frappe.log(
			f"Adding user `{ADMIN_USER}` for Sales Order `{doc.name}` to raven channel `{raven_channel.name}`"
		)

		# TODO: Get the system manager user from config. This defaults to Administrator
		with as_user():
			frappe.call(
				"raven.api.raven_channel_member.add_channel_members",
				channel_id=raven_channel.name,
				members=[ADMIN_USER],
			)

	# admins = frappe.conf.get("spectrum_ps_raven_admins") or [doc.owner]
	# members = [u for u in admins if frappe.db.exists("Raven User", u)]
	# if members:
	# 	# TODO: Get the system manager user from config. This defaults to Administrator
	# 	with as_user():
	# 		frappe.call(
	# 			"raven.api.raven_channel_member.add_channel_members",
	# 			channel_id=raven_channel.name,
	# 			members=members,
	# 		)

	if not doc.customer:
		frappe.log(f"Sales Order `{doc.name}` has no Customer linked")
		frappe.throw(
			_("Sales Order {0} must have a Customer before creating its Raven Channel.").format(doc.name)
		)

	frappe.log(f"Looking up Customer `{doc.customer}` for Sales Order `{doc.name}`")
	customer = frappe.get_cached_doc("Customer", doc.customer)

	# Get Raven Bot associated with the customer
	# TODO: Get the system manager user from config. This defaults to Administrator
	with as_user():
		bot = ensure_customer_has_bot(customer)

	frappe.log(f"Adding Raven Bot `{bot}` to Channel `{raven_channel.name}`")
	bot_user = frappe.get_cached_doc("Raven Bot", bot)
	# TODO: Get the system manager user from config. This defaults to Administrator
	with as_user():
		bot_add_to_channel(bot_user, raven_channel.name)

	frappe.log(f"Added Raven Bot `{bot_user.name}` to Channel `{raven_channel.name}`")

	# TODO: Add Realtor's bot

	# Send WhatsApp message to the customer for onboarding
	template_params = {
		"customer_name": customer.customer_name,
		"order_id": doc.name,
		"company_name": "Spectrum PS",
	}

	frappe.log("Sending welcome message to customer...")
	frappe.enqueue(
		"spectrum_ps.spectrum_ps.doc_events.raven_message.deliver_template_message_to_whatsapp",
		queue="short",
		enqueue_after_commit=True,
		# Parameters
		message_id=f"{doc.name}-welcome-message",
		sales_order=doc.name,
		customer=doc.customer,
		template_id=TEMPLATE_ORDER_GREETINGS,
		content_variables=template_params,
	)


def remove_raven_channel(doc, method=None):
	channel_name = getattr(doc, "custom_raven_channel", None)
	if not channel_name:
		frappe.log(f"Sales Order `{doc.name}` has no Raven Channel to remove")
		return

	if not frappe.db.exists("Raven Channel", channel_name):
		frappe.log(f"Raven Channel `{channel_name}` for Sales Order `{doc.name}` was already removed")
		return

	frappe.log(f"Removing Raven Channel `{channel_name}` for Sales Order `{doc.name}`")
	# TODO: Get the system manager user from config. This defaults to Administrator
	with as_user():
		frappe.get_doc("Raven Channel", channel_name).delete(ignore_permissions=True)

def update_sales_order(doc, method=None):
	"""Sales Order saved: Compare with the previous saved state and route to the right handler."""

	before = doc.get_doc_before_save()

	old_status = before.get("custom_ticket_status") if before else None

	new_status = doc.get("custom_ticket_status")

	if old_status == new_status:
		return

	if new_status == "Completed":
		handle_completed(doc)
	elif new_status == "Accepted":
		handle_accepted(doc)



