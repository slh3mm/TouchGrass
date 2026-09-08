from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import JsonResponse

from .middleware import UATExternalIntegrationGuardMiddleware


class UATExternalIntegrationGuardMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = UATExternalIntegrationGuardMiddleware(
            lambda request: JsonResponse({"ok": True})
        )

    @override_settings(UAT_MODE=False, UAT_ALLOW_EXTERNAL_INTEGRATIONS=False)
    def test_development_requests_are_unchanged(self):
        response = self.middleware(self.factory.post("/api/skylight/sync/"))
        self.assertEqual(response.status_code, 200)

    @override_settings(UAT_MODE=True, UAT_ALLOW_EXTERNAL_INTEGRATIONS=False)
    def test_uat_blocks_external_skylight_sync(self):
        response = self.middleware(self.factory.post("/api/skylight/sync/"))
        self.assertEqual(response.status_code, 409)
        self.assertJSONEqual(
            response.content,
            {
                "error": "Live integrations are disabled in the UAT environment.",
                "code": "uat.external_integrations_disabled",
            },
        )

    @override_settings(UAT_MODE=True, UAT_ALLOW_EXTERNAL_INTEGRATIONS=False)
    def test_uat_allows_local_suggestion_decisions(self):
        response = self.middleware(
            self.factory.post("/api/skylight/suggestions/example/accept/")
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(UAT_MODE=True, UAT_ALLOW_EXTERNAL_INTEGRATIONS=False)
    def test_uat_blocks_remote_integration_validation(self):
        response = self.middleware(self.factory.post("/api/integrations/immich/"))
        self.assertEqual(response.status_code, 409)

    @override_settings(UAT_MODE=True, UAT_ALLOW_EXTERNAL_INTEGRATIONS=True)
    def test_controlled_live_pass_can_be_explicitly_enabled(self):
        response = self.middleware(self.factory.post("/api/skylight/sync/"))
        self.assertEqual(response.status_code, 200)
