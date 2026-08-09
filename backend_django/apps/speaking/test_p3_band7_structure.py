from django.test import SimpleTestCase

from .coaching_services import p3_model_answer_constraints
from .text_utils import p3_plain_spoken_text


class P3Band7StructureTests(SimpleTestCase):
    def test_shared_prompt_selects_a_structure_for_question_type_and_explains_why(self):
        prompt = p3_model_answer_constraints()

        required = (
            "**Q: <question>**",
            "**题目分析：**",
            "Question-type choice",
            "Opinion / comparison",
            "Listing Group A",
            "Category Group B",
            "Parallel explanation",
            "Two-camp contrast",
            "Hourglass",
            "**1. 接题（复述/改写题目本身）**",
            "Do not announce a plan",
            "one specific detail plus one qualitative observation",
            "one small self-correction or thinking trace",
            "3-5 reusable spoken expressions",
            "retrieval",
            "Why these choices matter",
        )
        for clause in required:
            self.assertIn(clause, prompt)

    def test_tts_text_omits_study_labels_question_and_timing_footer(self):
        markdown = """**题目分析：** 这是观点题，因此采用六步骨架；它需要清晰立场和有分寸的限定。

**Q: Why do most children think education is boring?**

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

**本题新增的可复用表达**
- **mostly comes down to how it's taught**
- **That said**

*(≈165词/60-65秒)*"""

        spoken = p3_plain_spoken_text(markdown)

        self.assertNotIn("Why do most children", spoken)
        self.assertNotIn("这是观点题", spoken)
        self.assertNotIn("接题", spoken)
        self.assertNotIn("165", spoken)
        self.assertEqual(spoken.count("mostly comes down to how it's taught"), 1)
        self.assertIn("Why kids find education boring", spoken)
        self.assertIn("mostly comes down to how it's taught", spoken)
        self.assertIn("That said", spoken)
        self.assertNotIn("**", spoken)
