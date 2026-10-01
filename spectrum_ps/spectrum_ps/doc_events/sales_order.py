import frappe
from frappe import _


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


def create_raven_channel(doc: "Sales Order", method=None):
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

	frappe.log(f"Linking raven channel {raven_channel.name} to Sales Order {doc.name}")
	doc.custom_raven_channel = raven_channel.name
	doc.save()

	# Add administrator to the channel
	# TODO: Add from a preset list or using some heuristic
	ADMIN_USER = "Administrator"
	if not frappe.db.exists("Raven Channel Member", {"channel_id": raven_channel.name, "user_id": ADMIN_USER}):
		frappe.call(
			"raven.api.raven_channel_member.add_channel_members",
			channel_id=raven_channel.name,
			members=[ADMIN_USER],
		)

	# admins = frappe.conf.get("spectrum_ps_raven_admins") or [doc.owner]
	# members = [u for u in admins if frappe.db.exists("Raven User", u)]
	# if members:
	# 	frappe.call(
	# 		"raven.api.raven_channel_member.add_channel_members",
	# 		channel_id=raven_channel.name,
	# 		members=members,
	# 	)

	if not doc.customer:
		frappe.log(f"Sales Order `{doc.name}` has no Customer linked")
		frappe.throw(
			_("Sales Order {0} must have a Customer before creating its Raven Channel.").format(doc.name)
		)

	frappe.log(f"Looking up Customer `{doc.customer}` for Sales Order `{doc.name}`")
	customer = frappe.get_cached_doc("Customer", doc.customer)
	if not customer.custom_raven_bot:
		frappe.log(f"Customer `{customer.name}` has no linked Raven Bot")
		frappe.throw(
			_("Customer {0} must have a Raven Bot before creating a Sales Order.").format(customer.name)
		)

	if not frappe.db.exists("Raven Bot", customer.custom_raven_bot):
		frappe.log(
			f"Linked Raven Bot `{customer.custom_raven_bot}` does not exist for Customer `{customer.name}`"
		)
		frappe.throw(
			_("Raven Bot {0} linked to Customer {1} does not exist.").format(
				customer.custom_raven_bot, customer.name
			)
		)

	frappe.log(f"Adding Raven Bot `{customer.custom_raven_bot}` to Channel `{raven_channel.name}`")
	bot_user = frappe.get_cached_doc("Raven Bot", customer.custom_raven_bot)

	bot_add_to_channel(bot_user, raven_channel.name)
	frappe.log(f"Added Raven Bot `{bot_user.name}` to Channel `{raven_channel.name}`")

	# TODO: Add Realtor's bot


def remove_raven_channel(doc: "Sales Order", method=None):
	channel_name = getattr(doc, "custom_raven_channel", None)
	if not channel_name:
		frappe.log(f"Sales Order `{doc.name}` has no Raven Channel to remove")
		return

	if not frappe.db.exists("Raven Channel", channel_name):
		frappe.log(f"Raven Channel `{channel_name}` for Sales Order `{doc.name}` was already removed")
		return

	frappe.log(f"Removing Raven Channel `{channel_name}` for Sales Order `{doc.name}`")
	frappe.get_doc("Raven Channel", channel_name).delete(ignore_permissions=True)
