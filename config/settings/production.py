import os

from .base import *  # noqa: F403

DEBUG = False

# Registration email outbox entries are sent automatically after the database
# transaction commits. Delivery still requires valid Gmail OAuth credentials.
GMAIL_API_ENABLED = os.getenv("GMAIL_API_ENABLED", "True").strip().lower() in {
    "1", "true", "yes", "on"
}

# Vercel's deployed filesystem is read-only; sensitive uploads use a private,
# project-connected Blob store with access limited to authenticated app views.
PRIVATE_MEDIA_BACKEND = os.getenv("PRIVATE_MEDIA_BACKEND", "vercel_blob").strip()

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
# Serverless deployment environments should use short-lived connections.
DATABASES["default"]["CONN_MAX_AGE"] = int(
    os.getenv("DB_CONN_MAX_AGE", "0")
)
