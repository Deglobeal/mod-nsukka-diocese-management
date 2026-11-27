"""Shared settings. Environment-specific settings import from this module."""
import os
from pathlib import Path
from dotenv import load_dotenv
from .database import postgres_database_config

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-this-secret")
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Email is configured through environment variables and remains opt-in for
# appointment activation so deployments do not start sending automatically.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
).strip()
EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in {
    "1", "true", "yes", "on"
}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").strip().lower() in {
    "1", "true", "yes", "on"
}
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "15"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "").strip()
CHAIRMAN_ACTIVATION_EMAIL_ENABLED = os.getenv(
    "CHAIRMAN_ACTIVATION_EMAIL_ENABLED", "False"
).strip().lower() in {"1", "true", "yes", "on"}

# Gmail API is separate from Django's configured email backend. The worker
# requires both this explicit switch and an explicit --send option.
GMAIL_API_ENABLED = os.getenv("GMAIL_API_ENABLED", "False").strip().lower() in {
    "1", "true", "yes", "on"
}
GMAIL_API_SENDER = os.getenv("GMAIL_API_SENDER", "deglobeal@gmail.com").strip()
GMAIL_OAUTH_CREDENTIALS_FILE = os.getenv(
    "GMAIL_OAUTH_CREDENTIALS_FILE",
    "~/.config/mod-nsukka/credentials.json",
).strip()
GMAIL_OAUTH_TOKEN_FILE = os.getenv(
    "GMAIL_OAUTH_TOKEN_FILE",
    "~/.config/mod-nsukka/token.json",
).strip()

# Sendar SMS gateway
SENDAR_API_KEY = os.getenv("SENDAR_API_KEY", "").strip()
SENDAR_API_BASE_URL = os.getenv(
    "SENDAR_API_BASE_URL", "https://api.sendar.io"
).strip().rstrip("/")
SENDAR_SENDER_ID = os.getenv("SENDAR_SENDER_ID", "").strip()
SENDAR_ROUTE = os.getenv("SENDAR_ROUTE", "transactional").strip()
SENDAR_TIMEOUT_SECONDS = int(os.getenv("SENDAR_TIMEOUT_SECONDS", "15"))
SENDAR_ENVIRONMENT = os.getenv("SENDAR_ENVIRONMENT", "sandbox").strip().lower()
SENDAR_ENABLED = os.getenv("SENDAR_ENABLED", "False").strip().lower() in {
    "1", "true", "yes", "on"
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core.apps.CoreConfig",
    "apps.organizations.apps.OrganizationsConfig",
    "apps.members.apps.MembersConfig",
    "apps.verification.apps.VerificationConfig",
    "apps.identity_cards.apps.IdentityCardsConfig",
    "apps.medical.apps.MedicalConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.chairman.apps.ChairmanConfig",
    "apps.complaints.apps.ComplaintsConfig",
    "apps.recognition.apps.RecognitionConfig",
    "apps.transfers.apps.TransfersConfig",
    "apps.audit.apps.AuditConfig",
    "apps.notifications.apps.NotificationsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "apps.core.context_processors.admin_navigation",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

_database_prefix = (
    "TEST_DB_"
    if os.getenv("DJANGO_SETTINGS_MODULE") == "config.settings.test"
    else "DB_"
)
DATABASES = {
    "default": postgres_database_config(
        prefix=_database_prefix,
        allow_url=_database_prefix != "TEST_DB_",
    )
}

LANGUAGE_CODE = "en-ng"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
    # Vercel publishes this directory at /static/ and copies the manifest into
    # the function bundle for ManifestStaticFilesStorage URL resolution.
    STATIC_ROOT = BASE_DIR / ".vercel" / "output" / "static" / "static"
else:
    STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "identity_cards_web:dashboard"
LOGOUT_REDIRECT_URL = "public_home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "public_membership_verification": "30/min",
    },
}
