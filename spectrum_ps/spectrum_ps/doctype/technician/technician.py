# Copyright (c) 2026, aswin and contributors
# For license information, please see license.txt

import json

from frappe.model.document import Document


class Technician(Document):
	def autoname(self):
		self.name = self.user

	def before_validate(self):
		self.skills_list = json.dumps(
			list(map(lambda x: x.skill_name, self.skills)) if isinstance(self.skills, list) else []
		)
