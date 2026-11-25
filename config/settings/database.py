"""Strict PostgreSQL configuration shared by Django settings modules."""

import os
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def _postgres_settings_from_url(url, *, variable_name):
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(f"{variable_name} must use PostgreSQL.")
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ImproperlyConfigured(
            f"{variable_name} must include a PostgreSQL host and database name."
        )

    query = parse_qs(parsed.query)
    settings = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {"sslmode": query.get("sslmode", [os.getenv("DB_SSLMODE", "prefer")])[0]},
    }
    return settings


def postgres_database_config(*, prefix="DB_", url_variable="DATABASE_URL", allow_url=True):
    """Return a PostgreSQL connection or fail with the missing variable names."""
    if allow_url and url_variable:
        # Vercel database integrations expose either DATABASE_URL* or
        # POSTGRES_URL* names. Prefer direct/unpooled URLs for migrations and
        # short-lived serverless connections, then use pooled standard URLs.
        url_variables = tuple(dict.fromkeys((
            "DATABASE_URL_UNPOOLED",
            "POSTGRES_URL_NON_POOLING",
            url_variable,
            "POSTGRES_URL",
        )))
        for variable_name in url_variables:
            url = os.getenv(variable_name, "").strip()
            if url:
                return _postgres_settings_from_url(url, variable_name=variable_name)

    names = ("NAME", "USER", "PASSWORD", "HOST")
    missing = [f"{prefix}{name}" for name in names if f"{prefix}{name}" not in os.environ]
    missing.extend(
        f"{prefix}{name}" for name in ("NAME", "USER", "HOST")
        if not os.getenv(f"{prefix}{name}", "").strip()
    )
    if missing:
        formatted = ", ".join(dict.fromkeys(missing))
        raise ImproperlyConfigured(
            "PostgreSQL is required. Set DATABASE_URL_UNPOOLED, "
            "POSTGRES_URL_NON_POOLING, DATABASE_URL, or POSTGRES_URL, "
            "or configure " + formatted + "."
        )

    database_name = os.environ[f"{prefix}NAME"].strip()
    if prefix == "TEST_DB_" and not database_name.startswith("test_"):
        raise ImproperlyConfigured(
            "TEST_DB_NAME must start with 'test_' to isolate the test database."
        )

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": os.environ[f"{prefix}USER"].strip(),
        "PASSWORD": os.environ[f"{prefix}PASSWORD"],
        "HOST": os.environ[f"{prefix}HOST"].strip(),
        "PORT": os.getenv(f"{prefix}PORT", "5432").strip() or "5432",
        "CONN_MAX_AGE": 0 if prefix == "TEST_DB_" else int(
            os.getenv("DB_CONN_MAX_AGE", "60")
        ),
        "OPTIONS": {
            "sslmode": os.getenv(
                f"{prefix}SSLMODE",
                "prefer" if prefix == "TEST_DB_" else os.getenv("DB_SSLMODE", "prefer"),
            ).strip()
        },
    }
