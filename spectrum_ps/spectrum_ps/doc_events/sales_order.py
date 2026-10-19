import frappe
from frappe import _
from raven.api.raven_channel_member import remove_channel_member

from spectrum_ps.config import (
	TEMPLAET_ORDER_COMPLETE,
	TEMPLATE_ORDER_GREETINGS,
	TEMPLATE_TECHNICIAN_ASSIGNMENT_ACCEPTED,
)
from spectrum_ps.config.logic_config import TECHNICIAN_INACTIVE_TICKET_STATES
from spectrum_ps.context_managers import as_user
from spectrum_ps.spectrum_ps.doc_events.customer import create_customer_bot
from spectrum_ps.utils import enqueue_outbound_sales_order_whatsapp_template
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification


def _get_customer_name(doc):
	return frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer


def handle_completed(doc):
	frappe.log(f"Sending Completion message to customer for {doc.name}..")

	enqueue_outbound_sales_order_whatsapp_template(
		doc,
		doc.customer,
		template_id=TEMPLAET_ORDER_COMPLETE,
		message_id=f"{doc.name}-Sale-Order-Completion-Message",
		content_variables={
			"customer_name": _get_customer_name(doc),
			"order_id": doc.name,
		},
	)

def handle_assignment(doc):
	frappe.log(f"Sending Notification to send assigned Technician")
	technician = doc.flags.get("assigned_to")

	if not technician:
		assignees = frappe.parse_json(frappe.db.get_value("Sales Order", doc.name, "_assign") or "[]")
		technician = assignees[0] if assignees else None

	if not technician:
		frappe.log(f"Sales Order `{doc.name}` is Assigned but has no Assignee")
		return

	priority = doc.get("custom_priority") or "Medium"
	msg = f"Ticket {doc.name} has been assigned to you. Priority - {priority}"
	frappe.log(f"Sending Assignment notification for {doc.name} to {technician}")

	enqueue_create_notification(
		[technician],
		{
			"type":"Alert",
			"subject":msg,
			"document_type":"Sales Order",
			"document_name":doc.name,
			"from_user":frappe.session.user,
		},
		)



def handle_accepted(doc):
	assigness = frappe.parse_json(frappe.db.get_value("Sales Order", doc.name, "_assign") or "[]")
	if not assigness:
		frappe.log(f"Sales Order `{doc.name}` accepted but has no assignee; skipping customer message")
		return

	technician = assigness[0]
	technician_name = frappe.db.get_value("User", technician, "full_name") or technician

	frappe.log(f"Sending Technician-assigned message to customer for {doc.name}..")

	enqueue_outbound_sales_order_whatsapp_template(
		doc,
		doc.customer,
		template_id=TEMPLATE_TECHNICIAN_ASSIGNMENT_ACCEPTED,
		message_id=f"{doc.name}-Sale-Order-Assignment-Message",
		content_variables={
			"customer_name": _get_customer_name(doc),
			"technician_name": technician_name,
			"order_id": doc.name,
		},
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


def handle_sales_order_create(doc, method=None):
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
	enqueue_outbound_sales_order_whatsapp_template(
		doc.name,
		doc.customer,
		message_id=f"{doc.name}-welcome-message",
		template_id=TEMPLATE_ORDER_GREETINGS,
		content_variables=template_params,
	)


def handle_sales_order_remove(doc, method=None):
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


def remove_technicians_on_complete(doc, method=None):
	if doc.get("custom_ticket_status") not in TECHNICIAN_INACTIVE_TICKET_STATES:
		return

	channel_id = doc.get("custom_raven_channel")

	if not channel_id or not frappe.db.exists("Raven Channel", channel_id):
		return

	assignments = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Sales Order",
			"reference_name": doc.name,
			"allocated_to": ["is", "set"],
			"status": ["!=", "Cancelled"],
		},
		fields=["allocated_to"],
	)

	# Only remove users explicitly registered as technicians.
	for assignment in assignments:
		user_id = assignment.get("allocated_to")

		if not user_id:
			continue

		is_technician = frappe.db.exists("Technician", {"user": user_id})

		if not is_technician:
			continue

		if not frappe.db.exists("Raven User", user_id):
			continue

		if not frappe.db.exists(
			"Raven Channel Member",
			{"channel_id": channel_id, "user_id": user_id},
		):
			continue

		try:
			from raven.api.raven_channel_member import remove_channel_member

			with as_user():
				remove_channel_member(
					user_id=user_id,
					channel_id=channel_id,
				)

			frappe.logger("spectrum_ps").info(
				"Removed technician %s from inactive Sales Order channel %s",
				user_id,
				channel_id,
			)

		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Failed removing technician {user_id} from channel {channel_id}",
			)


def update_sales_order(doc, method=None):
	"""Sales Order saved: Compare with the previous saved state and route to the right handler."""

	before = doc.get_doc_before_save()

	old_status = before.get("custom_ticket_status") if before else None
	new_status = doc.get("custom_ticket_status")

	# Remove channel membership on transition into an inactive state.
	if new_status in TECHNICIAN_INACTIVE_TICKET_STATES and old_status != new_status:
		remove_technicians_on_complete(doc, method)

	# Preserve existing workflow notification behavior.
	if old_status == new_status:
		return

	if new_status == "Completed":
		handle_completed(doc)
	if new_status == "Assigned":
		handle_assignment(doc)

	elif new_status == "Accepted":
		handle_accepted(doc)
