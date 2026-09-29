app_name = "spectrum_ps"
app_title = "Spectrum PS"
app_publisher = "phAIdelta"
app_description = "Spectrum PS application integration"
app_email = "admin@phaidelta.com"
app_license = "mit"


# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "spectrum_ps",
# 		"logo": "/assets/spectrum_ps/logo.png",
# 		"title": "Spectrum PS",
# 		"route": "/spectrum_ps",
# 		"has_permission": "spectrum_ps.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/spectrum_ps/css/spectrum_ps.css"
# app_include_js = "/assets/spectrum_ps/js/spectrum_ps.js"

# include js, css files in header of web template
# web_include_css = "/assets/spectrum_ps/css/spectrum_ps.css"
# web_include_js = "/assets/spectrum_ps/js/spectrum_ps.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "spectrum_ps/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "spectrum_ps/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "spectrum_ps.utils.jinja_methods",
# 	"filters": "spectrum_ps.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "spectrum_ps.install.before_install"
# after_install = "spectrum_ps.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "spectrum_ps.uninstall.before_uninstall"
# after_uninstall = "spectrum_ps.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "spectrum_ps.utils.before_app_install"
# after_app_install = "spectrum_ps.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "spectrum_ps.utils.before_app_uninstall"
# after_app_uninstall = "spectrum_ps.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "spectrum_ps.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "spectrum_ps.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["spectrum_ps.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Customer": {
		"after_insert": "spectrum_ps.spectrum_ps.doc_events.customer.create_customer_bot",
		"on_trash": "spectrum_ps.spectrum_ps.doc_events.customer.remove_customer_bot",
	},
	"Raven Bot": {
		"on_update": "spectrum_ps.spectrum_ps.doc_events.customer.sync_customer_raven_user",
	},
	"Sales Order": {
		"after_insert": "spectrum_ps.spectrum_ps.doc_events.sales_order.create_raven_channel",
		"on_trash": "spectrum_ps.spectrum_ps.doc_events.sales_order.remove_raven_channel",
	},
	"ToDo": {
		"after_insert": "spectrum_ps.spectrum_ps.doc_events.todo.add_assigned_user",
		"before_save": "spectrum_ps.spectrum_ps.doc_events.todo.remove_assigned_user_on_cancel",
		"on_trash": "spectrum_ps.spectrum_ps.doc_events.todo.remove_assigned_user_on_trash",
	},
        "Raven Message": {
                         "after_insert": "spectrum_ps.api.send_outbound_whatsapp"
        },
}


fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"dt",
				"in",
				[
					"Customer",
					"Item",
					"Address",
					"Sales Order",
					"Sales Order Item",
				],
			]
		],
	}
]


# Scheduled Tasks
# ---------------

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            [
                "dt",
                "in",
                [
                    "Customer",
                    "Item",
                    "Address",
                    "Sales Order",
                    "Sales Order Item",
                ],
            ]
        ],
    }
]

