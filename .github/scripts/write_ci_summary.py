import argparse
import json
import os
import re
from pathlib import Path


def read_json(path, default):
	try:
		return json.loads(path.read_text())
	except OSError, json.JSONDecodeError:
		return default


def get_test_summary(log_text, exit_code):
	ran_match = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+[\d.]+s", log_text)
	failed_match = re.search(r"FAILED\s*\(([^)]*)\)", log_text)
	skipped_match = re.search(r"skipped=(\d+)", failed_match.group(1) if failed_match else log_text)
	failure_text = failed_match.group(1) if failed_match else ""
	failures_match = re.search(r"failures=(\d+)", failure_text)
	errors_match = re.search(r"errors=(\d+)", failure_text)
	failures = int(failures_match.group(1)) if failures_match else 0
	errors = int(errors_match.group(1)) if errors_match else 0
	skipped = int(skipped_match.group(1)) if skipped_match else 0
	total = int(ran_match.group(1)) if ran_match else None
	passed = max(0, total - failures - errors - skipped) if total is not None else None

	if total is None:
		status = "NOT RUN" if exit_code in (None, 0) else "FAILED"
	else:
		status = "PASSED" if exit_code == 0 and failures == 0 and errors == 0 else "FAILED"

	failed_tests = sorted(set(re.findall(r"^(?:FAIL|ERROR):\s+([^\s(]+)", log_text, re.MULTILINE)))
	individual_results = re.findall(
		r"^(test[\w.]+)(?:\s+\([^)]*\))?\s+\.\.\.\s+(ok|FAIL|ERROR|skipped.*)$",
		log_text,
		re.MULTILINE,
	)
	return {
		"status": status,
		"total": total,
		"passed": passed,
		"failures": failures,
		"errors": errors,
		"skipped": skipped,
		"failed": failures + errors if total is not None else None,
		"failed_tests": failed_tests,
		"individual_results": individual_results,
	}


def source_doctypes(root, ground_truth):
	doctypes = set()
	doctype_dir = root / "spectrum_ps" / "spectrum_ps" / "doctype"
	for path in doctype_dir.glob("*/*.json"):
		definition = read_json(path, {})
		if definition.get("name"):
			doctypes.add(definition["name"])

	fixtures_dir = root / "spectrum_ps" / "fixtures"
	custom_fields = read_json(fixtures_dir / "custom_field.json", [])
	doctypes.update(field["dt"] for field in custom_fields if field.get("dt"))
	doctypes.update(ground_truth.get("fixture_records", {}).keys())

	source_files = [
		path for path in (root / "spectrum_ps").rglob("*.py") if not path.name.startswith("test_")
	]
	source_files.extend(fixtures_dir.glob("*.json"))
	source_files.extend(doctype_dir.glob("*/*.json"))
	source_text = "\n".join(path.read_text(errors="replace") for path in source_files)
	for doctype in ground_truth.get("integration_doctypes", []):
		if doctype in source_text:
			doctypes.add(doctype)
	return doctypes


def deployment_value(value):
	return "Yes" if value is True else "No" if value is False else "Unknown"


def deployment_count(values, total):
	if values is None:
		return f"Unknown / {total}", "Unknown"
	count = sum(values)
	percentage = count / total * 100 if total else 100
	return f"{count} / {total}", f"{percentage:.1f}%"


def render_deployment_counts(root, installed):
	ground_truth = read_json(root / "spectrum_ps" / "deployment_ground_truth.json", {})

	required_doctypes = (
		set(ground_truth.get("app_doctypes", []))
		| set(ground_truth.get("integration_doctypes", []))
		| set(ground_truth.get("custom_fields", {}))
		| set(ground_truth.get("fixture_records", {}))
		| set(ground_truth.get("setup_records", {}))
	)
	source_types = source_doctypes(root, ground_truth)
	deployed_types = set(installed.get("doctypes", [])) if installed is not None else None

	custom_field_path = root / "spectrum_ps" / "fixtures" / "custom_field.json"
	source_fields = {(field.get("dt"), field.get("fieldname")) for field in read_json(custom_field_path, [])}
	deployed_fields = {
		(field.get("doctype"), field.get("fieldname")): field.get("installed")
		for field in (installed or {}).get("custom_fields", [])
	}
	required_fields = {
		(doctype, fieldname)
		for doctype, fieldnames in ground_truth.get("custom_fields", {}).items()
		for fieldname in fieldnames
	}

	fixtures_dir = root / "spectrum_ps" / "fixtures"
	fixture_source = {}
	record_presence = []
	for doctype, names in ground_truth.get("fixture_records", {}).items():
		path = fixtures_dir / f"{doctype.lower().replace(' ', '_')}.json"
		fixture_source[doctype] = {record.get("name") for record in read_json(path, []) if record.get("name")}
		for name in names:
			record_presence.append(
				(
					name in fixture_source[doctype],
					(installed or {}).get("fixture_records", {}).get(doctype, {}).get(name),
				)
			)

	source_setup = (root / "spectrum_ps" / "setup.py").read_text(errors="replace")
	for doctype, record in ground_truth.get("setup_records", {}).items():
		in_source = bool(
			re.search(
				rf"^\s*{re.escape(record['constant'])}\s*=\s*['\"]{re.escape(record['value'])}['\"]",
				source_setup,
				re.MULTILINE,
			)
		)
		deployed = (installed or {}).get("setup_records", {}).get(doctype, {}).get(record["value"])
		record_presence.append((in_source, deployed))

	deployed_field_values = (
		[deployed_fields.get(field) is True for field in required_fields] if installed is not None else None
	)
	deployed_record_values = (
		[value is True for _, value in record_presence] if installed is not None else None
	)
	rows = [
		(
			"DocType Deployment",
			deployment_count(
				[doctype in source_types for doctype in required_doctypes], len(required_doctypes)
			),
			deployment_count(
				[doctype in deployed_types for doctype in required_doctypes]
				if deployed_types is not None
				else None,
				len(required_doctypes),
			),
		),
		(
			"Custom Field Deployment",
			deployment_count([field in source_fields for field in required_fields], len(required_fields)),
			deployment_count(deployed_field_values, len(required_fields)),
		),
		(
			"Fixture and Setup Record",
			deployment_count([source for source, _ in record_presence], len(record_presence)),
			deployment_count(deployed_record_values, len(record_presence)),
		),
	]

	lines = [
		"| Deployment category | In source (count / total) | In source (%) | In deployment (count / total) | In deployment (%) |",
		"|---|---:|---:|---:|---:|",
	]
	lines.extend(
		f"| {category} | {source[0]} | {source[1]} | {deployment[0]} | {deployment[1]} |"
		for category, source, deployment in rows
	)
	return "\n".join(lines)


def render_doctype_table(root, installed):
	ground_truth = read_json(root / "spectrum_ps" / "deployment_ground_truth.json", {})
	source = source_doctypes(root, ground_truth)
	expected = (
		source
		| set(ground_truth.get("app_doctypes", []))
		| set(ground_truth.get("integration_doctypes", []))
		| set(ground_truth.get("custom_fields", {}))
		| set(ground_truth.get("fixture_records", {}))
	)
	installed_doctypes = set(installed.get("doctypes", [])) if installed else None

	lines = [
		"| DocType | In source/code | Installed in deployment | Result |",
		"|---|---|---|---|",
	]
	for doctype in sorted(expected):
		in_source = doctype in source
		in_deployment = installed_doctypes is not None and doctype in installed_doctypes
		if installed_doctypes is None:
			result = "Deployment state unavailable"
			deployment_value = "Unknown"
		elif in_source and in_deployment:
			result = "Present"
			deployment_value = "Yes"
		elif in_source:
			result = "Missing from deployment"
			deployment_value = "No"
		elif in_deployment:
			result = "Deployment only"
			deployment_value = "Yes"
		else:
			result = "Missing from source and deployment"
			deployment_value = "No"
		lines.append(f"| `{doctype}` | {'Yes' if in_source else 'No'} | {deployment_value} | {result} |")
	return "\n".join(lines)


def render_custom_field_table(root, installed):
	ground_truth = read_json(root / "spectrum_ps" / "deployment_ground_truth.json", {})
	fixture_path = root / "spectrum_ps" / "fixtures" / "custom_field.json"
	fields = read_json(fixture_path, [])
	source_fields = {(field.get("dt"), field.get("fieldname")) for field in fields}
	deployment_fields = {
		(field.get("doctype"), field.get("fieldname")): field.get("installed")
		for field in (installed or {}).get("custom_fields", [])
	}

	lines = [
		"| DocType | Custom field | In source fixture | Installed in deployment | Result |",
		"|---|---|---:|---:|---|",
	]
	for doctype, fieldnames in sorted(ground_truth.get("custom_fields", {}).items()):
		for fieldname in sorted(fieldnames):
			in_source = (doctype, fieldname) in source_fields
			deployed = deployment_fields.get((doctype, fieldname))
			if deployed is None:
				result = "Deployment state unavailable"
			elif in_source and deployed:
				result = "Present"
			elif in_source:
				result = "Missing from deployment"
			elif deployed:
				result = "Deployment only"
			else:
				result = "Missing from source and deployment"
			lines.append(
				f"| `{doctype}` | `{fieldname}` | {'Yes' if in_source else 'No'} "
				f"| {deployment_value(deployed)} | {result} |"
			)
	return "\n".join(lines)


def render_record_table(root, installed):
	ground_truth = read_json(root / "spectrum_ps" / "deployment_ground_truth.json", {})
	fixtures_dir = root / "spectrum_ps" / "fixtures"
	fixture_source = {}
	for doctype in ground_truth.get("fixture_records", {}):
		path = fixtures_dir / f"{doctype.lower().replace(' ', '_')}.json"
		fixture_source[doctype] = {record.get("name") for record in read_json(path, []) if record.get("name")}

	source_setup = (root / "spectrum_ps" / "setup.py").read_text(errors="replace")
	setup_records = ground_truth.get("setup_records", {})
	setup_source = {
		(doctype, record["value"]): bool(
			re.search(
				rf"^\s*{re.escape(record['constant'])}\s*=\s*['\"]{re.escape(record['value'])}['\"]",
				source_setup,
				re.MULTILINE,
			)
		)
		for doctype, record in setup_records.items()
	}
	deployment_fixtures = (installed or {}).get("fixture_records", {})
	deployment_setup = (installed or {}).get("setup_records", {})

	lines = [
		"| Record type | DocType | Record | In source | Installed in deployment | Result |",
		"|---|---|---|---:|---:|---|",
	]
	records = [
		(
			"Fixture",
			doctype,
			name,
			name in fixture_source.get(doctype, set()),
			deployment_fixtures.get(doctype, {}).get(name),
		)
		for doctype, names in ground_truth.get("fixture_records", {}).items()
		for name in names
	]
	records.extend(
		(
			"Setup",
			doctype,
			record["value"],
			setup_source.get((doctype, record["value"]), False),
			deployment_setup.get(doctype, {}).get(record["value"]),
		)
		for doctype, record in setup_records.items()
	)
	for record_type, doctype, name, in_source, deployed in records:
		if deployed is None:
			result = "Deployment state unavailable"
		elif in_source and deployed:
			result = "Present"
		elif in_source:
			result = "Missing from deployment"
		elif deployed:
			result = "Deployment only"
		else:
			result = "Missing from source and deployment"
		lines.append(
			f"| {record_type} | `{doctype}` | `{name}` | {'Yes' if in_source else 'No'} "
			f"| {deployment_value(deployed)} | {result} |"
		)
	return "\n".join(lines)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--test-log", type=Path, required=True)
	parser.add_argument("--installed-doctypes", type=Path, required=True)
	parser.add_argument("--summary", type=Path, required=True)
	args = parser.parse_args()

	try:
		log_text = args.test_log.read_text(errors="replace")
	except OSError:
		log_text = ""
	exit_code_value = os.environ.get("TEST_EXIT_CODE")
	exit_code = int(exit_code_value) if exit_code_value not in (None, "") else None
	tests = get_test_summary(log_text, exit_code)
	install_outcome = os.environ.get("INSTALL_STEP_OUTCOME")
	test_outcome = os.environ.get("TEST_STEP_OUTCOME")
	if tests["total"] is None and install_outcome == "failure":
		tests["status"] = "SETUP FAILED"
	elif tests["total"] is None and test_outcome == "skipped":
		tests["status"] = "NOT RUN"
	installed_data = read_json(args.installed_doctypes, None)
	installed = installed_data if isinstance(installed_data, dict) else None
	root = Path(__file__).resolve().parents[2]
	test_row = (
		f"| `bench run-tests --app spectrum_ps` | {tests['status']} "
		f"| {tests['total'] if tests['total'] is not None else 'Unknown'} "
		f"| {tests['passed'] if tests['passed'] is not None else 'Unknown'} "
		f"| {tests['failed'] if tests['failed'] is not None else 'Unknown'} "
		f"| {tests['skipped'] if tests['total'] is not None else 'Unknown'} |"
	)

	lines = [
		"## CI Test Summary",
		"",
		"| Test suite | Status | Run | Passed | Failed | Skipped |",
		"|---|---:|---:|---:|---:|---:|",
		test_row,
	]
	if tests["failed_tests"]:
		lines.extend(["", "**Failed tests:**", ""])
		lines.extend(f"- `{name}`" for name in tests["failed_tests"])
	elif tests["status"] == "FAILED" and tests["total"] is None:
		lines.extend(["", "The test command failed before producing a test-run summary."])
	if tests["status"] == "SETUP FAILED":
		lines.extend(["", "App installation failed before the test suite could run."])
	if tests["individual_results"]:
		lines.extend(["", "**Individual test results:**", "", "| Test | Result |", "|---|---|"])
		lines.extend(f"| `{name}` | {result} |" for name, result in tests["individual_results"])

	lines.extend(
		[
			"",
			"## Deployment Coverage",
			"",
			render_deployment_counts(root, installed),
			"",
			"## DocType Deployment Status",
			"",
			render_doctype_table(root, installed),
		]
	)
	lines.extend(["", "## Custom Field Deployment Status", "", render_custom_field_table(root, installed)])
	lines.extend(["", "## Fixture and Setup Record Status", "", render_record_table(root, installed), ""])
	args.summary.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
	main()
