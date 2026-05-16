from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import UserProfile
from apps.billing.models import TokenWallet


class AccountsApiTests(TestCase):
    def test_register_login_me_and_profile_update(self):
        client = Client(enforce_csrf_checks=True)

        csrf_res = client.get("/api/accounts/csrf/")
        self.assertEqual(csrf_res.status_code, 200)
        csrf_token = csrf_res.json()["csrfToken"]

        register = client.post(
            "/api/accounts/register/",
            data={
                "username": "jasper-api",
                "password": "test-pass-12345",
                "password_confirm": "test-pass-12345",
                "display_name": "Jasper",
                "full_name": "LiHua",
                "english_name": "Jasper",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(register.status_code, 201)
        self.assertEqual(register.json()["user"]["profile"]["full_name"], "LiHua")
        self.assertTrue(TokenWallet.objects.filter(user__username="jasper-api").exists())

        me = client.get("/api/accounts/me/")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["authenticated"])

        csrf_token = client.get("/api/accounts/csrf/").json()["csrfToken"]
        patched = client.patch(
            "/api/accounts/me/",
            data={"full_name": "Li Hua", "english_name": "Jasper Chen", "target_band": "7.0"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(patched.status_code, 200)
        profile = UserProfile.objects.get(user__username="jasper-api")
        self.assertEqual(profile.english_name, "Jasper Chen")
        self.assertEqual(str(profile.target_band), "7.0")

        csrf_token = client.get("/api/accounts/csrf/").json()["csrfToken"]
        client.post("/api/accounts/logout/", content_type="application/json", HTTP_X_CSRFTOKEN=csrf_token)
        logged_out = client.get("/api/accounts/me/")
        self.assertEqual(logged_out.status_code, 401)

        login = client.post(
            "/api/accounts/login/",
            data={"username": "jasper-api", "password": "test-pass-12345"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["username"], "jasper-api")

    def test_register_rejects_duplicate_username(self):
        get_user_model().objects.create_user(username="duplicate", password="test-pass")
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/accounts/register/",
            data={"username": "duplicate", "password": "test-pass-12345", "password_confirm": "test-pass-12345"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("errors", response.json())
        self.assertIn("username", response.json()["errors"])

    def test_register_rejects_duplicate_legacy_user_id(self):
        get_user_model().objects.create_user(username="legacy-owner", legacy_user_id="local-default", password="test-pass")
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/accounts/register/",
            data={"username": "legacy-duplicate", "password": "test-pass-12345", "password_confirm": "test-pass-12345", "legacy_user_id": "local-default"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 409)

    def test_register_requires_password_confirmation(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/accounts/register/",
            data={"username": "user-1", "password": "test-pass-12345", "password_confirm": "different-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["message"], "Registration failed")
        self.assertIn("password_confirm", body["errors"])

    def test_register_applies_password_validation(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/accounts/register/",
            data={"username": "user-2", "password": "123", "password_confirm": "123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json()["errors"])

    def test_password_change_success_and_login_with_new_password(self):
        user = get_user_model().objects.create_user(username="pw-change-user", password="old-pass-12345")
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]

        login = client.post(
            "/api/accounts/login/",
            data={"username": user.username, "password": "old-pass-12345"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login.status_code, 200)

        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        change = client.post(
            "/api/accounts/password/change/",
            data={
                "current_password": "old-pass-12345",
                "new_password": "new-pass-12345",
                "new_password_confirm": "new-pass-12345",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(change.status_code, 200)

        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        client.post("/api/accounts/logout/", content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        old_login = client.post(
            "/api/accounts/login/",
            data={"username": user.username, "password": "old-pass-12345"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = client.post(
            "/api/accounts/login/",
            data={"username": user.username, "password": "new-pass-12345"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(new_login.status_code, 200)

    def test_password_change_requires_authentication(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/accounts/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/accounts/password/change/",
            data={
                "current_password": "old-pass-12345",
                "new_password": "new-pass-12345",
                "new_password_confirm": "new-pass-12345",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 401)

    def test_login_requires_csrf(self):
        user = get_user_model().objects.create_user(username="csrf-user", password="test-pass-12345")
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/accounts/login/",
            data={"username": user.username, "password": "test-pass-12345"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_password_reset_availability_contract(self):
        client = Client()
        response = client.get("/api/accounts/password/reset/availability/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("available", body)
        self.assertIn("message", body)
