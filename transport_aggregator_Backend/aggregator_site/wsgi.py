"""WSGI entry point for production servers."""
import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aggregator_site.settings")
application = get_wsgi_application()
