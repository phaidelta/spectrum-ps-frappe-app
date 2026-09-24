app_name = "spectrum_ps"
app_title = "Spectrum PS"
app_publisher = "phAIdelta"
app_description = "Spectrum PS application integration"
app_email = "admin@phaidelta.com"
app_license = "mit"


doc_events = {
	"Raven Message": {
		"after_insert": "spectrum_ps.raven_events.on_raven_message_created",
                "on_update": "spectrum_ps.raven_events.on_raven_message_created"
	}
}
