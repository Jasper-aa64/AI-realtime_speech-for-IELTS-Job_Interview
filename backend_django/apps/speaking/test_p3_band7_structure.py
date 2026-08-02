from django.test import SimpleTestCase

from .coaching_services import p3_model_answer_constraints
from .text_utils import p3_plain_spoken_text


class P3Band7StructureTests(SimpleTestCase):
    def test_shared_prompt_requires_human_conversation_structure_and_explains_why(self):
        prompt = p3_model_answer_constraints()

        required = (
            "**Q: <question>**",
            "**1. 接题（复述/改写题目本身）**",
            "**2. 观点**",
            "**3.1 原因/背景**",
            "**3.2 现实观察**",
            "**3.3 让步限定**",
            "**4. 个人评价（可选）**",
            "**5. 自然收尾**",
            "3-5 reusable spoken expressions",
            "retrieval",
            "Why this structure matters",
        )
        for clause in required:
            self.assertIn(clause, prompt)

    def test_tts_text_omits_study_labels_question_and_timing_footer(self):
        markdown = """**Q: Why do most children think education is boring?**

**1. 接题（复述/改写题目本身）**
- Why kids find education boring... that's something I think about a lot.

**2. 观点**
- I'd say it **mostly comes down to how it's taught**.

**3.1 原因/背景**
- **Let me put it this way** — repetition can make curiosity disappear.

**3.2 现实观察**
- From what I remember, practical classes stayed with me.

**3.3 让步限定**
- **That said**, teachers often work with packed curriculums.

**4. 个人评价（可选）**
- Personally, delivery matters more than the subject.

**5. 自然收尾**
- So it's less about education itself and more about how it is taught.

*(≈165词/60-65秒)*"""

        spoken = p3_plain_spoken_text(markdown)

        self.assertNotIn("Why do most children", spoken)
        self.assertNotIn("接题", spoken)
        self.assertNotIn("观点", spoken)
        self.assertNotIn("165", spoken)
        self.assertIn("Why kids find education boring", spoken)
        self.assertIn("mostly comes down to how it's taught", spoken)
        self.assertIn("That said", spoken)
        self.assertNotIn("**", spoken)
