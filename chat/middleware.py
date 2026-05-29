from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model


@database_sync_to_async
def get_user_from_token(token_str):
    User = get_user_model()
    try:
        token = AccessToken(token_str)
        user_id = token['user_id']
        return User.objects.get(id=user_id)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Reads JWT from:
      1. Authorization header  → "Bearer <token>"
      2. Query string          → ?token=<token>
    """
    async def __call__(self, scope, receive, send):
        token_str = None

        # 1. Check Authorization header
        headers = dict(scope.get('headers', []))
        auth_header = headers.get(b'authorization', b'').decode()
        if auth_header.startswith('Bearer '):
            token_str = auth_header.split(' ', 1)[1].strip()

        # 2. Fallback: query string ?token=...
        if not token_str:
            from urllib.parse import parse_qs
            query_string = scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token_list = params.get('token', [])
            if token_list:
                token_str = token_list[0]

        scope['user'] = await get_user_from_token(token_str) if token_str else AnonymousUser()
        return await super().__call__(scope, receive, send)