from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import UserProfile
from apps.billing.models import TokenWallet


class AccountsApiTests(TestCase):
    def test_register_login_me_and_profile_update(self):
        client = Client()
        register = client.post(
            "/api/accounts/register/",
            data={
                "username": "jasper-api",
                "password": "test-pass-123",
                "display_name": "Jasper",
                "full_name": "LiHua",
                "english_name": "Jasper",
            },
            content_type="application/json",
        )
        self.assertEqual(register.status_code, 201)
        self.assertEqual(register.json()["user"]["profile"]["full_name"], "LiHua")
        self.assertTrue(TokenWallet.objects.filter(user__username="jasper-api").exists())

        me = client.get("/api/accounts/me/")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["authenticated"])

        patched = client.patch(
            "/api/accounts/me/",
            data={"full_name": "Li Hua", "english_name": "Jasper Chen", "target_band": "7.0"},
            content_type="application/json",
        )
        self.assertEqual(patched.status_code, 200)
        profile = UserProfile.objects.get(user__username="jasper-api")
        self.assertEqual(profile.english_name, "Jasper Chen")
        self.assertEqual(str(profile.target_band), "7.0")

        client.post("/api/accounts/logout/", content_type="application/json")
        logged_out = client.get("/api/accounts/me/")
        self.assertEqual(logged_out.status_code, 401)

        login = client.post(
            "/api/accounts/login/",
            data={"username": "jasper-api", "password": "test-pass-123"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["username"], "jasper-api")

    def test_register_rejects_duplicate_username(self):
        get_user_model().objects.create_user(username="duplicate", password="test-pass")
        response = Client().post(
            "/api/accounts/register/",
            data={"username": "duplicate", "password": "test-pass"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_register_rejects_duplicate_legacy_user_id(self):
        get_user_model().objects.create_user(username="legacy-owner", legacy_user_id="local-default", password="test-pass")
        response = Client().post(
            "/api/accounts/register/",
            data={"username": "legacy-duplicate", "password": "test-pass", "legacy_user_id": "local-default"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
