# Copyright (c) 2026, aswin and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

TECHNICIAN_ROLE = "Technician"


class Technician(Document):
	def autoname(self):
		self.name = self.user

	def before_validate(self):
		self.skills_list = json.dumps(
			list(map(lambda x: x.skill_name, self.skills)) if isinstance(self.skills, list) else []
		)

	def after_insert(self):
		user = frappe.get_doc("User", self.user)
		user.flags.ignore_permissions = True
		user.add_roles(TECHNICIAN_ROLE)

	def after_delete(self):
		if not frappe.db.exists("User", self.user):
			return
		user = frappe.get_doc("User", self.user)
		user.flags.ignore_permission = True
		user.remove_roles(TECHNICIAN_ROLE)
