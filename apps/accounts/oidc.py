"""OIDC single sign-on for the web UI and Bearer access for API clients.

Configuration is environment-driven; SSO is enabled as soon as issuer,
client id and client secret are set:

    OIDC_ISSUER_URL         e.g. https://auth.example.com/application/o/dispatcharr/
    OIDC_CLIENT_ID          confidential client id for the web UI
    OIDC_CLIENT_SECRET      client secret for the web UI
    OIDC_REDIRECT_URI       optional; defaults to <request origin>/api/accounts/oidc/callback/
    OIDC_SCOPES             optional; default "openid profile email"
    OIDC_ADMIN_GROUP        optional; members of this IdP group become admins (user_level 10)
    OIDC_REQUIRED_GROUP     optional; when set, only members of this group may log in
    OIDC_BUTTON_LABEL       optional; default "Sign in with SSO"
    OIDC_ACCEPTED_CLIENT_IDS  optional; comma-separated additional audiences whose
                              Bearer access tokens are accepted by the API (e.g. the
                              public client id used by TV apps via device flow)

The web login flow is the standard authorization-code flow; after the code
exchange the callback issues the same SimpleJWT token pair the password login
would, handed to the SPA via the URL fragment of /login.
"""

import json
import logging
import secrets
from urllib.parse import urlencode

import requests
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User

import os

logger = logging.getLogger(__name__)

DISCOVERY_CACHE_KEY = "oidc_discovery_document"
DISCOVERY_CACHE_SECONDS = 3600


def get_config():
    # Keep the issuer verbatim — token `iss` claims must match exactly
    # (authentik issuers end with a slash).
    issuer = os.environ.get("OIDC_ISSUER_URL", "")
    client_id = os.environ.get("OIDC_CLIENT_ID", "")
    client_secret = os.environ.get("OIDC_CLIENT_SECRET", "")
    accepted = [client_id] + [
        c.strip()
        for c in os.environ.get("OIDC_ACCEPTED_CLIENT_IDS", "").split(",")
        if c.strip()
    ]
    return {
        "enabled": bool(issuer and client_id and client_secret),
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": os.environ.get("OIDC_REDIRECT_URI", ""),
        "scopes": os.environ.get("OIDC_SCOPES", "openid profile email"),
        "admin_group": os.environ.get("OIDC_ADMIN_GROUP", ""),
        "required_group": os.environ.get("OIDC_REQUIRED_GROUP", ""),
        "button_label": os.environ.get("OIDC_BUTTON_LABEL", "Sign in with SSO"),
        "device_client_id": os.environ.get("OIDC_DEVICE_CLIENT_ID", ""),
        # authentik issues per-provider issuers; the device-flow client's
        # tokens carry its own iss (e.g. .../application/o/castarr/).
        "accepted_issuers": [issuer] + (
            [os.environ["OIDC_DEVICE_ISSUER_URL"]]
            if os.environ.get("OIDC_DEVICE_ISSUER_URL")
            else []
        ),
        "accepted_audiences": accepted + (
            [os.environ["OIDC_DEVICE_CLIENT_ID"]]
            if os.environ.get("OIDC_DEVICE_CLIENT_ID")
            else []
        ),
    }


def discovery():
    cfg = get_config()
    if not cfg["enabled"]:
        return None
    doc = cache.get(DISCOVERY_CACHE_KEY)
    if doc:
        return doc
    url = cfg["issuer"].rstrip("/") + "/.well-known/openid-configuration"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    doc = response.json()
    cache.set(DISCOVERY_CACHE_KEY, doc, DISCOVERY_CACHE_SECONDS)
    return doc


def resolve_user(claims):
    """Map OIDC claims to a local user, creating or updating it. Returns the
    user, or None when a required group is missing."""
    cfg = get_config()
    username = claims.get("preferred_username") or claims.get("sub")
    if not username:
        return None
    groups = claims.get("groups") or []

    is_admin = bool(cfg["admin_group"]) and cfg["admin_group"] in groups
    if cfg["required_group"] and cfg["required_group"] not in groups and not is_admin:
        return None

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": claims.get("email", ""),
            "user_level": 10 if is_admin else 1,
        },
    )
    changed = False
    # Group mapping only ever raises privileges of existing users — it must
    # not demote accounts that were made admin locally (that once locked the
    # instance back into the setup dialog).
    if is_admin and user.user_level < 10:
        user.user_level = 10
        changed = True
    if claims.get("email") and user.email != claims["email"]:
        user.email = claims["email"]
        changed = True
    custom = user.custom_properties or {}
    oidc_info = {"iss": cfg["issuer"], "sub": claims.get("sub", "")}
    if custom.get("oidc") != oidc_info:
        custom["oidc"] = oidc_info
        user.custom_properties = custom
        changed = True
    if created:
        user.set_unusable_password()
        changed = True
    if changed:
        user.save()
    return user


def _redirect_uri(request):
    cfg = get_config()
    if cfg["redirect_uri"]:
        return cfg["redirect_uri"]
    # Trust the reverse proxy's forwarded proto when present.
    proto = request.META.get("HTTP_X_FORWARDED_PROTO", request.scheme)
    return f"{proto}://{request.get_host()}/api/accounts/oidc/callback/"


@api_view(["GET"])
@permission_classes([AllowAny])
def oidc_status(request):
    cfg = get_config()
    return JsonResponse(
        {
            "enabled": cfg["enabled"],
            "label": cfg["button_label"],
            # Public info for TV clients doing the OIDC device flow:
            "issuer": cfg["issuer"],
            "device_client_id": cfg["device_client_id"],
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def oidc_login(request):
    cfg = get_config()
    if not cfg["enabled"]:
        return JsonResponse({"error": "SSO is not configured"}, status=404)
    try:
        doc = discovery()
    except requests.RequestException:
        logger.exception("OIDC discovery failed")
        return JsonResponse({"error": "identity provider unreachable"}, status=502)

    state = secrets.token_urlsafe(24)
    request.session["oidc_state"] = state
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": _redirect_uri(request),
        "scope": cfg["scopes"],
        "state": state,
    }
    return HttpResponseRedirect(doc["authorization_endpoint"] + "?" + urlencode(params))


@api_view(["GET"])
@permission_classes([AllowAny])
def oidc_callback(request):
    cfg = get_config()
    if not cfg["enabled"]:
        return JsonResponse({"error": "SSO is not configured"}, status=404)

    error = request.GET.get("error")
    if error:
        return HttpResponseRedirect(f"/login#sso_error={error}")

    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    if not code or not state or state != request.session.pop("oidc_state", None):
        return HttpResponseRedirect("/login#sso_error=state_mismatch")

    try:
        doc = discovery()
        token_response = requests.post(
            doc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
            timeout=10,
        )
        token_response.raise_for_status()
        tokens = token_response.json()
        userinfo_response = requests.get(
            doc["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10,
        )
        userinfo_response.raise_for_status()
        claims = userinfo_response.json()
    except requests.RequestException:
        logger.exception("OIDC code exchange failed")
        return HttpResponseRedirect("/login#sso_error=exchange_failed")

    user = resolve_user(claims)
    if user is None:
        return HttpResponseRedirect("/login#sso_error=not_authorized")
    if not user.is_active:
        return HttpResponseRedirect("/login#sso_error=inactive")

    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    # Hand the SPA its tokens exactly like a password login would end up in
    # localStorage, then boot the app fresh — no URL-fragment/SPA timing.
    page = (
        "<!doctype html><meta charset='utf-8'><script>"
        f"localStorage.setItem('accessToken', {json.dumps(str(access))});"
        f"localStorage.setItem('refreshToken', {json.dumps(str(refresh))});"
        f"localStorage.setItem('tokenExpiration', {json.dumps(str(access['exp']))});"
        "location.replace('/');"
        "</script>Anmeldung erfolgreich – einen Moment …"
    )
    response = HttpResponse(page)
    response["Cache-Control"] = "no-store"
    return response
