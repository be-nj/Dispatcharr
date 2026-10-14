from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

CONFIGURED = {
    "OIDC_ISSUER_URL": "https://idp.example/",
    "OIDC_CLIENT_ID": "dispatcharr",
    "OIDC_CLIENT_SECRET": "secret",
}


class OidcStatusAutoLoginTests(TestCase):
    def status(self, env):
        with mock.patch.dict("os.environ", env, clear=False):
            return APIClient().get("/api/accounts/oidc/status/").json()

    def test_auto_login_off_by_default(self):
        self.assertFalse(self.status({**CONFIGURED, "OIDC_AUTO_LOGIN": ""})["auto_login"])

    def test_auto_login_on_when_set(self):
        self.assertTrue(self.status({**CONFIGURED, "OIDC_AUTO_LOGIN": "true"})["auto_login"])

    def test_no_auto_login_without_sso(self):
        env = {**CONFIGURED, "OIDC_CLIENT_SECRET": "", "OIDC_AUTO_LOGIN": "true"}
        self.assertFalse(self.status(env)["auto_login"])
