from .base import *  # noqa: F403

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"
