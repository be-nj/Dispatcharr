from rest_framework import authentication
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from .models import User


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "rest_framework_simplejwt.authentication.JWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT Bearer authentication.\n\n"
                "Obtain a token pair via `POST /api/accounts/token/` using your username and password, "
                "then paste the **access token** here — Swagger adds the `Bearer ` prefix automatically.\n\n"
                "Access tokens expire after 30 minutes. Refresh using `POST /api/accounts/token/refresh/`."
            ),
        }


class ApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.ApiKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": (
                "API key authentication.\n\n"
                "Pass your personal API key in the `X-API-Key` request header. "
                "Keys can be generated via `POST /api/accounts/api-keys/generate/` "
                "and revoked via `POST /api/accounts/api-keys/revoke/`."
            ),
        }


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """
    Accepts header `Authorization: ApiKey <key>` or `X-API-Key: <key>`.
    """

    keyword = "ApiKey"

    def authenticate(self, request):
        # Check X-API-Key header first
        raw_key = request.META.get("HTTP_X_API_KEY")

        if not raw_key:
            auth = authentication.get_authorization_header(request).split()
            if not auth:
                return None

            if len(auth) != 2:
                return None

            scheme = auth[0].decode().lower()
            if scheme != self.keyword.lower():
                return None

            raw_key = auth[1].decode()

        if not raw_key:
            return None

        if not raw_key:
            return None

        try:
            user = User.objects.get(api_key=raw_key)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid API key")

        if not user.is_active:
            raise exceptions.AuthenticationFailed("User inactive")

        return (user, None)

    def authenticate_header(self, request):
        return self.keyword


class QueryParamJWTAuthentication(JWTAuthentication):
    """Reads a JWT from the `token` query parameter. Used for media endpoints
    where the browser cannot set Authorization headers (e.g. <video src>)."""

    def authenticate(self, request):
        params = getattr(request, "query_params", request.GET)
        raw_token = params.get("token")
        if not raw_token:
            return None
        try:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except (InvalidToken, TokenError):
            return None


class OIDCBearerAuthentication(authentication.BaseAuthentication):
    """
    Accepts `Authorization: Bearer <token>` where the token is an access token
    issued by the configured OIDC identity provider (see apps.accounts.oidc).

    Placed before SimpleJWT in DEFAULT_AUTHENTICATION_CLASSES: tokens whose
    unverified issuer claim does not match the configured issuer are passed on
    (return None), so locally issued SimpleJWT tokens keep working unchanged.
    Signatures are verified against the provider's JWKS; accepted audiences
    are the web client id plus OIDC_ACCEPTED_CLIENT_IDS (e.g. a TV app's
    public device-flow client).
    """

    _jwks_clients = {}

    def authenticate(self, request):
        from . import oidc as oidc_module
        import jwt as pyjwt

        cfg = oidc_module.get_config()
        if not cfg["enabled"]:
            return None

        header = authentication.get_authorization_header(request).split()
        if len(header) != 2 or header[0].lower() != b"bearer":
            return None
        raw_token = header[1].decode()

        try:
            unverified = pyjwt.decode(raw_token, options={"verify_signature": False})
        except pyjwt.PyJWTError:
            return None
        if unverified.get("iss") != cfg["issuer"]:
            return None

        try:
            doc = oidc_module.discovery()
            jwks_uri = doc["jwks_uri"]
            client = self._jwks_clients.get(jwks_uri)
            if client is None:
                client = pyjwt.PyJWKClient(jwks_uri, cache_keys=True)
                self._jwks_clients[jwks_uri] = client
            signing_key = client.get_signing_key_from_jwt(raw_token)
            claims = pyjwt.decode(
                raw_token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=cfg["accepted_audiences"],
                issuer=cfg["issuer"],
            )
        except Exception as exc:
            raise exceptions.AuthenticationFailed(f"Invalid OIDC token: {exc.__class__.__name__}")

        user = oidc_module.resolve_user(claims)
        if user is None:
            raise exceptions.AuthenticationFailed("User not authorized for this service")
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User inactive")
        return (user, None)

    def authenticate_header(self, request):
        return "Bearer"
