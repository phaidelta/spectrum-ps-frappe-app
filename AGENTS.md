# AGENTS.md

## Project Overview

Spectrum PS is a custom Frappe Framework application for managing service tickets and customer communications. It integrates with ERPNext Sales Orders and Raven chat, and includes technician management, customer inquiries, message queues, ticket settings, permissions, and deployment fixtures.

The app is named `spectrum_ps` and targets Frappe/ERPNext 16. The project requires Python 3.14 or newer. Frappe itself is installed and managed by `bench`; it is intentionally not a normal project dependency in `pyproject.toml`.

## Repository Layout

- `spectrum_ps/` — installable Frappe app package.
- `spectrum_ps/spectrum_ps/doctype/` — app-owned DocType definitions, controllers, client scripts, and tests.
- `spectrum_ps/spectrum_ps/doc_events/` — handlers registered for Frappe document lifecycle events.
- `spectrum_ps/fixtures/` — custom fields and records exported/imported with the app.
- `spectrum_ps/config/` — application behavior and integration configuration.
- `spectrum_ps/integrations/` — external service integrations, including Twilio.
- `spectrum_ps/deployment_ground_truth.json` — human-editable deployment requirements used by deployment-integrity checks and CI reporting.
- `spectrum_ps/deployment_summary.py` — collects installed-site state for CI.
- `.github/workflows/ci.yml` — boots a Frappe site with ERPNext and Raven, installs this app, runs its tests, and writes a deployment summary.
- `.github/workflows/linter.yml` — runs pre-commit hooks, Frappe Semgrep rules, and pip-audit.
- `.github/scripts/write_ci_summary.py` — renders test and deployment coverage into the GitHub Actions step summary.
- `APP_AUTOMATIONS.md` — describes document-event side effects, role-driven behavior, Raven/WhatsApp integrations, and install/migrate setup.

## Development Environment

Use a Frappe bench environment with compatible Frappe 16, ERPNext 16, and Raven checkouts to install the app and run integration tests. A typical bench setup installs this repository as `spectrum_ps` and then installs the app on a site:

```bash
bench get-app <repository-url> --branch version-16
bench --site <site-name> install-app spectrum_ps
```

In this repository, the CI workflow is the authoritative example of the complete dependency and site setup. It installs ERPNext from `version-16` and Raven from its `develop` branch before installing this app.

Do not try to install Frappe as an ordinary local package to resolve missing imports. Bench owns the Frappe runtime and its dependencies. Without a bench environment, Frappe-dependent tests and runtime checks cannot run; static lint may also report unresolved Frappe imports or types. Report that limitation clearly and still run applicable formatting, syntax, JSON, and other available checks.

## Coding Conventions

Follow the repository's root configuration files: `.editorconfig`, `pyproject.toml`, `.eslintrc`, and `.pre-commit-config.yaml`.

- Python: use Ruff for linting, import sorting, and formatting. Ruff targets Python 3.14, uses a 110-character configured line length, double quotes, and tabs for indentation. `.editorconfig` sets a 99-character editor hint; keep changes consistent with nearby code and let the configured checks decide validity.
- JavaScript and other supported front-end files: use ESLint and Prettier through pre-commit. ESLint recognizes standard Frappe browser globals; avoid introducing unnecessary console output.
- General files: preserve UTF-8, LF line endings, final newlines, and no trailing whitespace. JSON DocType files use the repository's existing compact/one-space style and may intentionally omit the final newline.
- Pre-commit also checks Python AST syntax, JSON, TOML, YAML, merge-conflict markers, debug statements, and trailing whitespace. Its Ruff import hook may apply fixes.
- Do not broaden changes to unrelated existing lint warnings. Fix warnings introduced by the change and identify environment-related failures separately.

## Frappe and Application Practices

- Use Frappe document APIs, hooks, metadata, permission patterns, and query helpers consistently with the surrounding app.
- Keep document event handlers registered in `spectrum_ps/hooks.py`; verify the correct lifecycle event for behavior that must validate or act before/after persistence.
- Installation and migration setup is centralized in `spectrum_ps/setup.py` through `after_install` and `after_migrate`. Keep setup operations safe to run repeatedly.
- ERPNext doctypes such as Customer, Sales Order, Sales Order Item, Sales Invoice, Item, and Address, and Raven doctypes are integration dependencies rather than app-owned doctypes.
- Do not assume a standalone Frappe installation contains ERPNext or Raven. The integration CI installs all three applications.
- Read `APP_AUTOMATIONS.md` before changing event hooks or integration behavior, and update it when app automations change.

## Fixtures and Deployment Integrity

Keep source-controlled deployment requirements synchronized:

- Define app-owned doctypes under `spectrum_ps/spectrum_ps/doctype/`.
- Keep custom fields and exported records in `spectrum_ps/fixtures/`, and register fixture doctypes and filters in `spectrum_ps/hooks.py`.
- Update `spectrum_ps/deployment_ground_truth.json` whenever required doctypes, custom fields, fixture records, setup-created records, or workflow configuration change. This is the editable source of expected deployment assets, not a substitute for adding those assets to fixtures or setup code.
- Workflow fixture changes must keep the linked Workflow State and Workflow Action Master fixtures and the workflow's states/transitions in sync with ground truth.
- Deployment-integrity tests check both source assets and installed-site records. CI's deployment summary reports DocType, custom-field, and fixture/setup-record coverage.

## Testing and Validation

Run the narrowest relevant checks first. From a configured bench, run app tests with:

```bash
bench --site <site-name> run-tests --app spectrum_ps
```

Run repository lint and formatting checks with pre-commit, or use the configured tools directly:

```bash
pre-commit run --all-files
ruff check .
ruff format --check .
```

For changes to front-end files, run the applicable ESLint and Prettier hooks. For fixture or ground-truth changes, validate JSON and run the deployment-integrity tests in the full bench CI environment. The GitHub CI workflow runs on pushes to `main` and `version-16`, and on pull requests; the linter workflow runs on pull requests.

When a local check is blocked because Frappe/bench is unavailable, state which check could not run and rely on the configured CI integration tests rather than masking or weakening the test.
