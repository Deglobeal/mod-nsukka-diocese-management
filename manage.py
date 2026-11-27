#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    if sys.argv[1:2] == ["test"] and not any(
        argument == "--settings" or argument.startswith("--settings=")
        for argument in sys.argv[2:]
    ):
        # Route the standard test command through dedicated TEST_DB_* settings
        # even if a deployment has DJANGO_SETTINGS_MODULE configured globally.
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    elif os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        # Use production security and database settings for Vercel commands,
        # even if the deployment environment still names development settings.
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django could not be imported. Install dependencies with: pip install -r requirements/development.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
