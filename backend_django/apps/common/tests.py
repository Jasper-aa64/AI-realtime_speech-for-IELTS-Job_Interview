from django.contrib.auth import get_user_model
from django.test import Client, TestCase


class HealthEndpointTests(TestCase):
    def test_health_endpoint_returns_database_status(self):
        response = Client().get("/api/health/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "ielts-django-backend")
        self.assertIn("database", payload)


class UserModelTests(TestCase):
    def test_custom_user_model_is_active(self):
        user_model = get_user_model()

        self.assertEqual(user_model._meta.label, "accounts.CustomUser")
        user = user_model.objects.create_user(username="jasper", password="test-pass")
        user.phone_number = "13800000000"
        user.wechat_unionid = "wechat-union-test"
        user.mark_phone_verified()
        user.save()

        self.assertEqual(str(user), "jasper")
        self.assertIsNotNone(user.phone_verified_at)
