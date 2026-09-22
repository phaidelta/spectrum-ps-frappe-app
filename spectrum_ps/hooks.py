app_name = "spectrum_ps"
app_title = "Spectrum PS"
app_publisher = "phAIdelta"
app_description = "Spectrum PS application integration"
app_email = "admin@phaidelta.com"
app_license = "mit"

scheduler_events = {
    "cron": {
        "* * * * *": [
            "spectrum_ps.raven_listener.poll_raven_messages",
        ],
    },
}
