from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from config.settings import csrf_origin_for_host


class HealthEndpointTests(TestCase):
    def test_csrf_origin_for_host_trusts_public_https_hosts(self):
        self.assertEqual(
            csrf_origin_for_host("fiscal-mechanics-vintage-alternative.trycloudflare.com"),
            "https://fiscal-mechanics-vintage-alternative.trycloudflare.com",
        )
        self.assertEqual(csrf_origin_for_host("127.0.0.1"), "")
        self.assertEqual(csrf_origin_for_host("localhost"), "")

    def test_health_endpoint_returns_database_status(self):
        response = Client().get("/api/health/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "ielts-django-backend")
        self.assertIn("database", payload)

    def test_frontend_asset_route_serves_task1_chart_images(self):
        response = Client().get("/assets/writing/task1/line_transport.svg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/svg+xml")

    def test_frontend_asset_route_rejects_path_traversal(self):
        response = Client().get("/assets/../app.js")

        self.assertEqual(response.status_code, 404)

    def test_frontend_wasm_asset_route_serves_generated_wasm(self):
        response = Client().get("/wasm/audio_core_wasm.wasm")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/wasm")

    def test_frontend_wasm_asset_route_rejects_path_traversal(self):
        response = Client().get("/wasm/../app.js")

        self.assertEqual(response.status_code, 404)

    def test_frontend_vendor_asset_route_serves_howler(self):
        response = Client().get("/vendor/howler.min.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/javascript; charset=utf-8")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_frontend_vendor_asset_route_rejects_path_traversal(self):
        response = Client().get("/vendor/../app.js")

        self.assertEqual(response.status_code, 404)


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
