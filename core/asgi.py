import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from chat.middleware import JWTAuthMiddleware
import chat.routing

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(chat.routing.websocket_urlpatterns)
        )
    ),
})