"""PostgreSQL-only settings for the isolated Django test database."""

from .base import *  # noqa: F403
import os
from django.core.exceptions import ImproperlyConfigured


DEBUG = False

# Keep normal settings checks on PostgreSQL's maintenance database. The test
# runner switches to the dedicated TEST_DB_NAME and owns its lifecycle.
test_database_name = DATABASES["default"]["NAME"]
maintenance_database_name = os.getenv(
    "TEST_DB_MAINTENANCE_DATABASE", "postgres"
).strip()
if not maintenance_database_name or maintenance_database_name == test_database_name:
    raise ImproperlyConfigured(
        "TEST_DB_MAINTENANCE_DATABASE must name a separate PostgreSQL database."
    )
DATABASES["default"]["NAME"] = maintenance_database_name
DATABASES["default"]["TEST"] = {
    "NAME": test_database_name,
}

# Keep test password hashing fast without changing production settings.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
