import os


# Tests must never export telemetry, even when a developer enables tracing in .env.
os.environ["TRACING_ENABLED"] = "false"
os.environ["SENTRY_ENABLED"] = "false"
