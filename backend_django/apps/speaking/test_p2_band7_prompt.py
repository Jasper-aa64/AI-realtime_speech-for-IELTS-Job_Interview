import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.speaking.coaching_services import model_answer_constraints
from apps.speaking.models import SpeakingAttempt, SpeakingTurn
from apps.speaking.services import turn_feedback_batch_with_codex


class P2Band7PromptTests(TestCase):
    def test_p2_band7_prompt_prioritizes_linked_material_for_fluency(self):
        user = get_user_model().objects.create_user(username="p2-prompt-user", password="test-pass")
        attempt = SpeakingAttempt.objects.create(
            user=user,
            attempt_id="p2-prompt-attempt",
            mode="p2",
            part="p2",
            status=SpeakingAttempt.Status.READY_TO_SCORE,
        )
        turn = SpeakingTurn.objects.create(
            user=user,
            attempt=attempt,
            turn_id="p2-turn",
            sequence=0,
            part="p2",
            question="Describe a person who encouraged you.",
            transcript_raw="I talked about my English teacher.",
            transcript_cleaned="I talked about my English teacher.",
            metadata={"status": "completed"},
        )
        payload = {
            "turns": [
                {
                    "turn_id": turn.turn_id,
                    "display_transcript": turn.transcript_cleaned,
                    "display_transcript_markdown": turn.transcript_cleaned,
                    "band7_version": "My English teacher encouraged me before a speech competition.",
                    "ai_coaching": "主线清楚。\n\n语法错误纠正：无",
                }
            ]
        }
        prepared = "My high school English teacher encouraged me before a speech competition."

        with patch(
            "apps.speaking.services.run_codex",
            return_value=(json.dumps(payload), {"input_tokens": 100}),
        ) as run_codex:
            turn_feedback_batch_with_codex(
                [turn],
                attempt,
                "7",
                None,
                "p2_prompt_contract",
                prepared_corpus_by_turn={turn.turn_id: prepared},
                ai_source="codex_cli",
            )

        prompt = run_codex.call_args.args[0]
        self.assertIn("primary scaffold", prompt)
        self.assertIn("Reuse its original wording", prompt)
        self.assertIn("retrieval load", prompt)
        self.assertIn("automatic", prompt)
        self.assertIn("fluency", prompt)
        self.assertIn("not a creative-writing exercise", prompt)
        self.assertIn("multiple competing versions", prompt)
        self.assertIn("do not replace it merely to show variety", prompt)
        self.assertIn("180-230 English words", prompt)
        self.assertIn("1.5-2 minutes", prompt)
        self.assertIn(prepared, prompt)

    def test_shared_p2_model_answer_constraint_has_spoken_length(self):
        constraints = model_answer_constraints("p2")

        self.assertIn("180-230 English words", constraints)
        self.assertIn("1.5-2 minutes", constraints)
