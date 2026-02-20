__version__ = "1.3.0"

try:
    import sentry_sdk

    sentry_sdk.init(
        dsn="https://abc2a6d826b9fbb892612a13d7315ca5@o4510916592795648.ingest.de.sentry.io/4510916601774160",
        traces_sample_rate=0.1,
        send_default_pii=True,
        default_integrations=False,
    )
except Exception:
    pass
