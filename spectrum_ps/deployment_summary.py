import json
from pathlib import Path

import frappe


def write_deployment_state(output_path: str):
	"""Write installed DocTypes, required custom fields, and configured records for CI."""
	app_path = Path(frappe.get_app_path("spectrum_ps"))
	ground_truth = json.loads((app_path / "deployment_ground_truth.json").read_text())

	custom_fields = []
	for doctype, fieldnames in ground_truth.get("custom_fields", {}).items():
		for fieldname in fieldnames:
			custom_fields.append(
				{
					"doctype": doctype,
					"fieldname": fieldname,
					"installed": bool(
						frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
					),
				}
			)

	fixture_records = {}
	for doctype, names in ground_truth.get("fixture_records", {}).items():
		fixture_records[doctype] = {name: bool(frappe.db.exists(doctype, name)) for name in names}

	setup_records = {}
	for doctype, record in ground_truth.get("setup_records", {}).items():
		setup_records[doctype] = {
			record["value"]: bool(frappe.db.exists(doctype, {record["field"]: record["value"]}))
		}

	deployment_state = {
		"doctypes": frappe.get_all("DocType", pluck="name"),
		"custom_fields": custom_fields,
		"fixture_records": fixture_records,
		"setup_records": setup_records,
	}
	Path(output_path).write_text(json.dumps(deployment_state))
