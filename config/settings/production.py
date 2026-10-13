from .base import *  # noqa: F403

DEBUG = False

# Serve collected static assets through WhiteNoise in production.
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
# Enable these only after HTTPS is configured at the production host.
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "False").lower() == "true"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "False").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "False").lower() == "true"


# Allow the permanent Vercel domain and deployment-specific hostname.
VERCEL_URL = os.getenv("VERCEL_URL", "").strip()

PRODUCTION_HOSTS = ["modnsukkadiocese.vercel.app"]

ALLOWED_HOSTS = list(dict.fromkeys([
    *ALLOWED_HOSTS,
    *PRODUCTION_HOSTS,
    *([VERCEL_URL] if VERCEL_URL else []),
]))
# Use the managed PostgreSQL database when DATABASE_URL is configured.
# Local development continues to use the database settings in base.py.
from urllib.parse import parse_qs, unquote, urlsplit

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    parsed_database_url = urlsplit(DATABASE_URL)

    if parsed_database_url.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL must use PostgreSQL.")

    if not parsed_database_url.hostname or not parsed_database_url.path.strip("/"):
        raise ValueError("DATABASE_URL must include a database host and name.")

    database_query = parse_qs(parsed_database_url.query)

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed_database_url.path.lstrip("/")),
            "USER": unquote(parsed_database_url.username or ""),
            "PASSWORD": unquote(parsed_database_url.password or ""),
            "HOST": parsed_database_url.hostname,
            "PORT": parsed_database_url.port or 5432,
            "CONN_MAX_AGE": 0,
            "OPTIONS": {
                "sslmode": database_query.get("sslmode", ["require"])[0],
            },
        }
    }
