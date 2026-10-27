from .base import *  # noqa: F403

import os
from pathlib import Path

DEBUG = False

# Dedicated SQLite database for isolated local tests.
# Never inherit PostgreSQL credentials or DATABASE_URL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Prevent accidental use of external services during tests where supported.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
