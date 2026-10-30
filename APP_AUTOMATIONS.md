# Spectrum PS Automations

This document describes the app's current automatic behavior: Frappe document
events registered in `spectrum_ps/hooks.py`, app install/migrate setup, and the
most important effects those handlers have on linked records and integrations.
When behavior changes, update this document alongside the implementation and
tests. The hook registry and handler code remain authoritative.

## User

Registered on `on_update` by
`spectrum_ps.spectrum_ps.doc_events.user.check_and_add_role`.

- If the user has the `Spectrum PS User` role but not the `Raven User` role,
  add `Raven User` and show an alert. The handler does not remove roles.
- If the user has the `Technician` role and no `Technician` DocType record is
  linked to that user, create one with `user` set to the User document and
  `technician_name` set to the user's full name (or the user ID if no full name
  is available). Other Technician fields keep their DocType defaults.
- Technician creation is checked by the linked `user`, so subsequent User
  updates do not create a duplicate Technician.

## Customer and Raven Bot

`Customer.after_insert` calls
`spectrum_ps.spectrum_ps.doc_events.customer.create_customer_bot`.

- Ensure a Raven Bot named `<Customer ID> (Customer)` exists and link it to the
  Customer's `custom_raven_bot` field. Existing matching bots are reused.
- The Customer and Raven Bot changes are performed as the configured system
  manager. Creating/relinking the bot also synchronizes its Raven User.
- If a Customer does not exist when its bot must be created, the handler raises
  a validation error.

`Raven Bot.on_update` calls
`spectrum_ps.spectrum_ps.doc_events.customer.sync_customer_raven_user`.

- Find the Customer linked to that bot and update its Raven User's `full_name`
  and `first_name` to match the Customer.
- If there is no linked Customer, synchronization is skipped. If the bot has no
  linked Raven User, the handler raises an error.

`Customer.on_trash` calls
`spectrum_ps.spectrum_ps.doc_events.customer.remove_customer_bot`.

- Delete the Raven Bot referenced by the Customer's `custom_raven_bot` field
  when it exists. If it does not exist, log and leave the deletion alone.

## Sales Order and Ticket

`Sales Order.before_validate` calls
`spectrum_ps.spectrum_ps.doc_events.sales_order.before_validate`.

- Populate `custom_ticket_type` with a JSON-encoded list of each row's
  `item_name`. If `items` is not a list, the field is set to an empty JSON
  array. This runs before validation on inserts and saves.

`Sales Order.after_insert` calls
`spectrum_ps.spectrum_ps.doc_events.sales_order.handle_sales_order_create`.

- Create or reuse a Raven Channel in the `Customer communications` workspace
  named after the Sales Order, then link it to `custom_raven_channel`.
- Add users configured in the single `Spectrum PS Ticket Settings` document to
  the channel. If `add_all_administrators` is enabled, also include users with
  the `Administrator` role. User IDs are de-duplicated and existing channel
  members are skipped. Only candidates with a matching `Raven User` record are
  passed to Raven; successfully added users are logged, and candidates without
  a Raven User record are logged as warnings and skipped.
- Require a Customer. If the Customer has no active Sales Order, link this one.
  If another active order is linked, replace it only when that order is missing,
  cancelled (`docstatus == 2`), or has ticket status `Paid` or `Cancelled`;
  otherwise keep the existing active order.
- Ensure the Customer has a Raven Bot, creating/linking one if necessary, and
  add that bot to the Sales Order channel.
- Queue the customer welcome WhatsApp template after the transaction commits.

`Sales Order.on_update` calls
`spectrum_ps.spectrum_ps.doc_events.sales_order.update_sales_order`.

- Compare the ticket status before save with the new status. If it has not
  changed, skip status-transition notifications and cleanup.
- On transition to `Completed`, queue the completion WhatsApp template.
- On transition to `Assigned`, create an in-app alert for the assigned
  technician. The handler uses `doc.flags.assigned_to` when set, otherwise the
  first user in the Sales Order's `_assign` value. If no assignee is found, it
  logs and skips the alert.
- On transition to `Accepted`, queue the customer/technician assignment
  WhatsApp template if the Sales Order has an assignee; otherwise log and skip.
- On transition into `Cancelled`, `Completed`, or `Paid`, attempt to remove
  assigned technicians from the Sales Order's Raven Channel. Only active ToDo
  assignments for users with both a Technician record and Raven User record
  are eligible. Missing channels/members are skipped; individual removal errors
  are logged.

`Sales Order.on_trash` calls
`spectrum_ps.spectrum_ps.doc_events.sales_order.handle_sales_order_remove`.

- Delete the linked Raven Channel if it exists. Missing channel links or
  already-deleted channels are logged and skipped.

## ToDo Assignments

`ToDo.after_insert` calls
`spectrum_ps.spectrum_ps.doc_events.todo.add_assigned_user`.

- Only process ToDos referencing a Sales Order and having an assignee.
- Require the assignee to have a Raven User, and require the Sales Order to
  exist and have both a Customer and Raven Channel. Missing prerequisites raise
  an error, preventing the assignment from completing.
- If the ticket status is `New` or `Reopened`, change it to `Assigned`.
- Add the assignee to the Sales Order's Raven Channel.
- The handler currently contains a TODO to prevent multiple people from being
  assigned to one Sales Order; do not assume it enforces a single assignee.

`ToDo.before_save` calls
`remove_assigned_user_on_cancel`. If a ToDo's status is `Cancelled`, remove its
assignee from the linked Sales Order Raven Channel.

`ToDo.on_trash` calls `remove_assigned_user_on_trash`. If the ToDo is not
already `Cancelled`, remove its assignee from the linked channel before
deletion. Removal is skipped if the assignee is not a Raven User or the Sales
Order has no channel.

## Raven Messages and WhatsApp

`Raven Message.before_insert` calls
`spectrum_ps.spectrum_ps.doc_events.raven_message.validate_outbound_whatsapp`.

- Ignore inbound WhatsApp webhook messages, bot messages, non-text messages,
  messages without a channel, and empty text.
- For eligible messages in a Sales Order channel, reject the message if the
  Customer has a different `custom_active_sales_order`. A message in a
  non-Sales-Order channel is not subject to this Sales Order check.

`Raven Message.after_insert` calls
`send_outbound_whatsapp`.

- Apply the same webhook, bot, message-type, channel, and empty-text exclusions.
- For an eligible Sales Order channel message, set the Customer's active order
  to this order if no active order is set, then queue delivery to the
  Customer's WhatsApp number after commit. Text is stripped from Raven's HTML
  representation and the sender's first name is prepended.
- Delivery is performed asynchronously. Missing phone numbers and Twilio
  failures are recorded in the error log; a cache key prevents duplicate
  delivery of the same Raven message.
- A message is rejected before insertion when the Customer already has a
  different active Sales Order, so the after-insert delivery does not override
  an existing different active order.

`Sales Invoice.on_submit` calls
`spectrum_ps.spectrum_ps.doc_events.sales_invoice.on_sales_invoice_submit`.

- Skip return invoices. Otherwise, find the first invoice item linked to a
  Sales Order and queue a WhatsApp invoice template with a signed PDF download
  link. If no item references a Sales Order, log and skip.
- Errors while preparing/queuing the message are caught and written to the
  error log; they do not prevent invoice submission.

`Raven User.after_insert` and `Raven User.on_trash` manage membership in the
`Customer communications` Raven Workspace via
`spectrum_ps.spectrum_ps.doc_events.raven_user`.

- On creation, skip bots, disabled users, and non-System Users when linked to a
  Frappe User. Skip if the workspace is absent or membership already exists;
  otherwise create a non-admin workspace member.
- On deletion, delete matching workspace-member rows.
- These handlers catch and log errors rather than raising them to the Raven
  User operation.

## Installation and Migration

Both `after_install` and `after_migrate` call `spectrum_ps.setup.run_setup`.
This setup is intended to be repeatable:

- Ensure the app's `Technician` and `Spectrum PS User` roles exist.
- Upsert Technician custom permissions on Sales Order, Raven Channel, Raven
  User, Raven Workspace Member, and Customer.
- Create the public Raven Workspace `Customer communications` if the Raven
  DocType is installed and the workspace does not already exist. If Raven is
  not installed yet, workspace creation is skipped for a later migration.

The `setup_sales_order_naming` helper exists in `spectrum_ps/setup.py` but is
not called by `run_setup` or registered as a hook; it does not currently change
the Sales Order naming series automatically.

## Related Behavior Outside Document Hooks

- `spectrum_ps/messaging.py` selects active Sales Orders for customer messages,
  excluding ticket status `Cancelled`. If no valid active order remains, it
  clears the Customer's stale active-order link.
- Ticket statuses used by assignment and technician cleanup are centralized in
  `spectrum_ps/config/logic_config.py`. Consult those constants when changing
  what counts as an inactive or assignable ticket.
- Deployment fixtures and the editable expected-deployment list are maintained
  in `spectrum_ps/fixtures/` and `spectrum_ps/deployment_ground_truth.json`.
