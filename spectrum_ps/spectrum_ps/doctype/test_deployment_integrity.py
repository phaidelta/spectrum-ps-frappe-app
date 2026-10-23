import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from spectrum_ps import hooks


class TestDeploymentIntegrity(IntegrationTestCase):
	def test_app_doctypes_are_installed(self):
		doctype_path = Path(frappe.get_app_path("spectrum_ps")) / "spectrum_ps" / "doctype"
		doctype_definitions = [json.loads(path.read_text()) for path in doctype_path.glob("*/*.json")]
		self.assertTrue(doctype_definitions, "No Spectrum PS DocType definitions were found")

		missing = [
			definition["name"]
			for definition in doctype_definitions
			if not frappe.db.exists("DocType", definition["name"])
		]
		self.assertEqual(missing, [], f"App DocTypes are not installed: {', '.join(missing)}")

	def test_integration_doctypes_are_installed(self):
		fixtures_path = Path(frappe.get_app_path("spectrum_ps")) / "fixtures"
		custom_fields = json.loads((fixtures_path / "custom_field.json").read_text())
		required_doctypes = (
			set(hooks.doc_events)
			| {field["dt"] for field in custom_fields}
			| {
				"Raven Channel",
				"Raven Channel Member",
				"Raven Workspace",
				"Raven Workspace Member",
			}
		)

		missing = sorted(doctype for doctype in required_doctypes if not frappe.db.exists("DocType", doctype))
		self.assertEqual(missing, [], f"Integration DocTypes are not installed: {', '.join(missing)}")

	def test_custom_field_fixtures_are_installed(self):
		fixtures_path = Path(frappe.get_app_path("spectrum_ps")) / "fixtures"
		custom_fields = json.loads((fixtures_path / "custom_field.json").read_text())
		self.assertTrue(custom_fields, "No custom fields are defined in the fixture")

		missing_doctypes = sorted(
			{field["dt"] for field in custom_fields if not frappe.db.exists("DocType", field["dt"])}
		)
		self.assertEqual(
			missing_doctypes,
			[],
			f"DocTypes customized by Spectrum PS are not installed: {', '.join(missing_doctypes)}",
		)

		missing_fields = [
			f"{field['dt']}.{field['fieldname']}"
			for field in custom_fields
			if not frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]})
			or not frappe.get_meta(field["dt"]).has_field(field["fieldname"])
		]
		self.assertEqual(
			missing_fields,
			[],
			f"Custom fields are missing or not applied: {', '.join(missing_fields)}",
		)

	def test_fixture_records_are_installed(self):
		fixtures_path = Path(frappe.get_app_path("spectrum_ps")) / "fixtures"
		missing_records = []

		for fixture in hooks.fixtures:
			doctype = fixture["dt"]
			fixture_file = fixtures_path / f"{doctype.lower().replace(' ', '_')}.json"
			records = json.loads(fixture_file.read_text())
			missing_records.extend(
				f"{doctype}: {record['name']}"
				for record in records
				if not frappe.db.exists(doctype, record["name"])
			)

		self.assertEqual(
			missing_records,
			[],
			f"Fixture records are not installed: {', '.join(missing_records)}",
		)

	def test_setup_created_custom_permissions_exist(self):
		required_permissions = {
			"Sales Order",
			"Raven Channel",
			"Raven User",
			"Raven Workspace Member",
			"Customer",
		}
		missing = sorted(
			doctype
			for doctype in required_permissions
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "Technician"})
		)
		self.assertEqual(
			missing,
			[],
			f"Technician permissions are not installed for: {', '.join(missing)}",
		)

	def test_setup_created_raven_workspace_exists(self):
		self.assertTrue(
			frappe.db.exists(
				"Raven Workspace",
				{"workspace_name": "Customer communications"},
			),
			"Setup did not create the Customer communications Raven Workspace",
		)
