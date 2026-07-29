from django.test import SimpleTestCase

from apps.speaking.ai_config import speaking_ai_model_for_source


class SpeakingAiModelSourceTests(SimpleTestCase):
    def test_gpt_5_6_profile_sources_use_their_exact_http_models(self):
        self.assertEqual(speaking_ai_model_for_source("gpt"), "gpt-5.4-mini")
        self.assertEqual(speaking_ai_model_for_source("gpt-5.6-terra"), "gpt-5.6-terra")
        self.assertEqual(speaking_ai_model_for_source("gpt-5.6-luna"), "gpt-5.6-luna")
        self.assertEqual(speaking_ai_model_for_source("gpt-5.6-sol"), "gpt-5.6-sol")
