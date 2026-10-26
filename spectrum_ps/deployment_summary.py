import json
from pathlib import Path

import frappe


def write_installed_doctypes(output_path: str):
	"""Write installed DocType names to a JSON file for the CI summary."""
	Path(output_path).write_text(json.dumps(frappe.get_all("DocType", pluck="name")))
