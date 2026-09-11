import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qad.settings')

try:
    import redis
except ImportError:
    redis = None

application = get_wsgi_application()
