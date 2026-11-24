import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.database import postgres_database_config


class PostgreSQLSettingsTests(SimpleTestCase):
    def test_application_database_requires_explicit_postgresql_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(
                ImproperlyConfigured, "PostgreSQL is required"
            ):
                postgres_database_config(allow_url=False)

    def test_connection_url_rejects_non_postgresql_engines(self):
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///db.sqlite3"}, clear=True):
            with self.assertRaisesMessage(
                ImproperlyConfigured, "DATABASE_URL must use PostgreSQL"
            ):
                postgres_database_config()

    def test_unpooled_database_url_is_used_when_standard_url_is_absent(self):
        values = {
            "DATABASE_URL_UNPOOLED": (
                "postgresql://app:secret@db.example/mod_nsukka?sslmode=require"
            ),
        }
        with patch.dict(os.environ, values, clear=True):
            config = postgres_database_config()

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "mod_nsukka")
        self.assertEqual(config["HOST"], "db.example")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")

    def test_test_settings_use_dedicated_test_database_values(self):
        values = {
            "DATABASE_URL": "postgresql://production:secret@prod.example/prod",
            "TEST_DB_NAME": "test_mod_nsukka",
            "TEST_DB_USER": "mod_test",
            "TEST_DB_PASSWORD": "test-only",
            "TEST_DB_HOST": "127.0.0.1",
            "TEST_DB_PORT": "55432",
            "TEST_DB_SSLMODE": "disable",
        }
        with patch.dict(os.environ, values, clear=True):
            config = postgres_database_config(prefix="TEST_DB_", allow_url=False)

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "test_mod_nsukka")
        self.assertEqual(config["HOST"], "127.0.0.1")
        self.assertEqual(config["PORT"], "55432")
        self.assertEqual(config["PASSWORD"], "test-only")

    def test_test_database_name_must_be_isolated(self):
        values = {
            "TEST_DB_NAME": "mod_nsukka",
            "TEST_DB_USER": "mod_test",
            "TEST_DB_PASSWORD": "test-only",
            "TEST_DB_HOST": "127.0.0.1",
        }
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "TEST_DB_NAME must start with 'test_'",
            ):
                postgres_database_config(
                    prefix="TEST_DB_", allow_url=False
                )
