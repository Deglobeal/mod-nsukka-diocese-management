import os
from django.core.wsgi import get_wsgi_application

if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
application = get_wsgi_application()
