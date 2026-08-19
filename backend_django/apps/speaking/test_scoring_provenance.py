from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.speaking.models import SpeakingAttempt, SpeakingReport
from apps.speaking.report_services import report_payload
from apps.speaking.services import _speaking_score_provenance


class SpeakingScoringProvenanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="speaking-provenance-user", password="test-pass")

    def test_provenance_derivation(self):
        provider, model = _speaking_score_provenance({"model": "claude-sonnet-4-6", "backend": "http_api"})
        self.assertEqual((provider, model), ("claude", "claude-sonnet-4-6"))

        provider, model = _speaking_score_provenance({"model": "gpt-5.6-terra", "backend": "http_api"})
        self.assertEqual((provider, model), ("gpt", "gpt-5.6-terra"))

        provider, model = _speaking_score_provenance({"model": "", "generation_backend": "fallback"})
        self.assertEqual((provider, model), ("fallback", ""))

    def test_report_payload_surfaces_stored_scoring_keys(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="provenance-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.SCORED,
        )
        SpeakingReport.objects.create(
            user=self.user,
            attempt=attempt,
            overall_band=6.0,
            fluency_coherence=6.0,
            lexical_resource=6.0,
            grammar_range_accuracy=6.0,
            feedback_summary="ok",
            report_payload={
                "ielts_score": {
                    "overall_band": 6.0,
                    "fluency_coherence": 6.0,
                    "lexical_resource": 6.0,
                    "grammatical_range": 6.0,
                    "feedback": "ok",
                    "model": "claude-sonnet-4-6",
                    "scoring_provider": "claude",
                    "scoring_model": "claude-sonnet-4-6",
                },
                "scoring_provider": "claude",
                "scoring_model": "claude-sonnet-4-6",
            },
        )
        payload = report_payload(attempt)
        self.assertEqual(payload["scoring_provider"], "claude")
        self.assertEqual(payload["scoring_model"], "claude-sonnet-4-6")
        self.assertEqual(payload["ielts_score"]["scoring_model"], "claude-sonnet-4-6")

    def test_legacy_report_without_provenance_does_not_invent_a_model(self):
        attempt = SpeakingAttempt.objects.create(
            user=self.user,
            attempt_id="legacy-attempt",
            mode="p1",
            part="p1",
            status=SpeakingAttempt.Status.SCORED,
        )
        SpeakingReport.objects.create(
            user=self.user,
            attempt=attempt,
            overall_band=6.0,
            fluency_coherence=6.0,
            lexical_resource=6.0,
            grammar_range_accuracy=6.0,
            feedback_summary="ok",
            report_payload={},
        )
        payload = report_payload(attempt)
        self.assertEqual(payload.get("scoring_model", ""), "")
        self.assertEqual(payload.get("scoring_provider", ""), "")
