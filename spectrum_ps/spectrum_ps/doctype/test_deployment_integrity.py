import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from spectrum_ps import hooks, setup


class TestDeploymentIntegrity(IntegrationTestCase):
	def test_ground_truth_requirements_exist_in_source(self):
		app_path = Path(frappe.get_app_path("spectrum_ps"))
		ground_truth = json.loads((app_path / "deployment_ground_truth.json").read_text())
		doctype_path = app_path / "spectrum_ps" / "doctype"
		source_doctypes = {json.loads(path.read_text())["name"] for path in doctype_path.glob("*/*.json")}

		missing_doctypes = sorted(set(ground_truth["app_doctypes"]) - source_doctypes)
		self.assertEqual(
			missing_doctypes,
			[],
			f"Required app DocTypes are missing from spectrum_ps/doctype: {', '.join(missing_doctypes)}",
		)

		fixtures_path = app_path / "fixtures"
		custom_fields = json.loads((fixtures_path / "custom_field.json").read_text())
		source_custom_fields = {(field["dt"], field["fieldname"]) for field in custom_fields}
		missing_custom_fields = sorted(
			f"{doctype}.{fieldname}"
			for doctype, fieldnames in ground_truth["custom_fields"].items()
			for fieldname in fieldnames
			if (doctype, fieldname) not in source_custom_fields
		)
		self.assertEqual(
			missing_custom_fields,
			[],
			f"Required custom fields are missing from fixtures/custom_field.json: {', '.join(missing_custom_fields)}",
		)

		missing_records = []
		for doctype, names in ground_truth["fixture_records"].items():
			fixture_path = fixtures_path / f"{doctype.lower().replace(' ', '_')}.json"
			records = json.loads(fixture_path.read_text()) if fixture_path.exists() else []
			source_names = {record["name"] for record in records}
			missing_records.extend(f"{doctype}: {name}" for name in names if name not in source_names)
		self.assertEqual(
			missing_records,
			[],
			f"Required fixture records are missing from source: {', '.join(missing_records)}",
		)

		workflow_records = json.loads((fixtures_path / "workflow.json").read_text())
		for workflow_name, requirement in ground_truth.get("workflows", {}).items():
			workflow = next((row for row in workflow_records if row["name"] == workflow_name), None)
			self.assertIsNotNone(workflow, f"Workflow fixture is missing: {workflow_name}")
			for fieldname in ("document_type", "is_active", "workflow_state_field"):
				self.assertEqual(workflow[fieldname], requirement[fieldname])

			actual_states = {
				(row["state"], int(row["doc_status"]), row["allow_edit"]) for row in workflow["states"]
			}
			expected_states = {
				(row["state"], row["doc_status"], row["allow_edit"]) for row in requirement["states"]
			}
			self.assertEqual(
				actual_states,
				expected_states,
				f"Workflow states differ from ground truth for {workflow_name}",
			)

			transition_fields = ("state", "action", "next_state", "allowed")
			actual_transitions = {
				tuple(row[fieldname] for fieldname in transition_fields) for row in workflow["transitions"]
			}
			expected_transitions = {
				tuple(row[fieldname] for fieldname in transition_fields) for row in requirement["transitions"]
			}
			self.assertEqual(
				actual_transitions,
				expected_transitions,
				f"Workflow transitions differ from ground truth for {workflow_name}",
			)

		for doctype, requirement in ground_truth["setup_records"].items():
			self.assertEqual(
				getattr(setup, requirement["constant"], None),
				requirement["value"],
				f"Required setup record {doctype} {requirement['value']} is missing from setup.py",
			)

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
		ground_truth = json.loads(
			(Path(frappe.get_app_path("spectrum_ps")) / "deployment_ground_truth.json").read_text()
		)
		custom_fields = json.loads((fixtures_path / "custom_field.json").read_text())
		required_doctypes = (
			set(hooks.doc_events)
			| set(ground_truth["integration_doctypes"])
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

	def test_workflow_fixtures_are_installed_with_all_states_and_transitions(self):
		app_path = Path(frappe.get_app_path("spectrum_ps"))
		ground_truth = json.loads((app_path / "deployment_ground_truth.json").read_text())
		for workflow_name, requirement in ground_truth.get("workflows", {}).items():
			workflow = frappe.get_doc("Workflow", workflow_name)
			self.assertEqual(workflow.document_type, requirement["document_type"])
			self.assertEqual(int(workflow.is_active), requirement["is_active"])
			self.assertEqual(workflow.workflow_state_field, requirement["workflow_state_field"])

			actual_states = {(row.state, int(row.doc_status), row.allow_edit) for row in workflow.states}
			expected_states = {
				(row["state"], row["doc_status"], row["allow_edit"]) for row in requirement["states"]
			}
			self.assertEqual(
				actual_states,
				expected_states,
				f"Installed workflow states differ from ground truth for {workflow_name}",
			)

			transition_fields = ("state", "action", "next_state", "allowed")
			actual_transitions = {
				(row.state, row.action, row.next_state, row.allowed) for row in workflow.transitions
			}
			expected_transitions = {
				tuple(row[fieldname] for fieldname in transition_fields) for row in requirement["transitions"]
			}
			self.assertEqual(
				actual_transitions,
				expected_transitions,
				f"Installed workflow transitions differ from ground truth for {workflow_name}",
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
