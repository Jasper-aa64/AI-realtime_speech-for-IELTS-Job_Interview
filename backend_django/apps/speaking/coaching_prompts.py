"""Coaching/transcript prompt fragments and the display-transcript markdown helper.

Extracted from ``services.py``. These are the reusable prompt-text building
blocks shared by the turn-feedback prompt builders (single and batch): the
per-part coaching constraints, the ASR-correction and markdown rules embedded in
those prompts, and the helper that resolves a display_transcript_markdown value
from a model payload (falling back to spoken markdown).
"""

from __future__ import annotations

from typing import Any

from .text_utils import clean_markdown_text, spoken_markdown


def coaching_prompt_constraints(part: str) -> str:
    if part == "p1":
        return """你是 IELTS Speaking 真人教练。
请用中文给这一次回答做简短口语反馈，只输出正文，不要标题。

正文要求：
- 先用 1-2 句话说清楚这次回答最大的问题。
- 然后用分点方式给出立即改进点；每一点内部直接说明问题和改法，不要套用固定模板。
- 不要使用“→ 改法：”这类固定结构。
- 立即改进点可以包含逻辑连贯、连接词、内容展开、表达自然度等问题，由你根据回答自行决定数量和顺序。

**语法 & 表达纠正：**
分点列出；每点按内容自然表达，不限制固定格式。
如无错误，写：无。

**亮点**（如有）：简短肯定 1 句用得好的地方

不要输出【】占位符；不要为了凑格式拆成“问题/改法”两行；根据这次回答决定立即改进点和语法表达纠正的数量。"""
    if part == "p3":
        return """你是 IELTS Speaking Part 3 真人教练。
请用中文给这一次回答做简短但有帮助的口语反馈，只输出正文，不要标题。

重点判断这次回答在 P3 真实考试里最影响分数的 discussion 问题：
- 有没有直接表达观点
- 有没有解释原因和影响
- 有没有对比、让步或反方角度
- 有没有从个人经历上升到更 general / social / abstract 的讨论
- 追问是否直接回应了新角度，而不是重复主问题

反馈可以自由分点，不要套固定模板，也不要限制点数。每一点都要具体指出这次回答缺了哪个讨论动作，并给一个可以马上照着说的改法或句型。
最后保留「语法 & 表达纠正」部分；如无错误，写：无。
不要点评大小写、标点、ASR 噪声或转写显示格式。"""
    return """请用中文给这一次回答做简短 IELTS Speaking 口语反馈，只输出正文，不要标题。
先判断真实考试里最影响分数的问题，只讲最值得改的 1-2 点，具体、短、能马上照着改。
最后保留「语法 & 表达纠正」部分；如无错误，写：无。"""


DISPLAY_TRANSCRIPT_ASR_RULES = """display_transcript is an ASR-corrected transcript for display and scoring:
- Fix confident ASR mis-recognition only when the ASR word is semantically unnatural in this exact question context and a phonetically similar correction is clearly natural.
- Examples of confident ASR fixes: for a science question, "Songs plays a vital role" -> "Science plays a vital role"; "sync my teeth into" -> "sink my teeth into"; "I'm a big fellows long holidays" -> "I'm a big fan of long holidays"; "Do the future" -> "In the future".
- Do not fix learner errors that the candidate probably really said. Keep grammar/collocation mistakes such as "I'm a university student major in software engineering" unchanged for coaching to correct.
- If uncertain, keep the ASR word. Do not guess content, add ideas, upgrade vocabulary, improve grammar, or turn display_transcript into a Band 7 answer.
- ASR-corrected words must not appear in ai_coaching as grammar/expression mistakes. ai_coaching must only correct learner errors that remain in display_transcript.
- Do not mention or correct words that are absent from display_transcript, and do not bring removed ASR noise back into coaching.
- Do not comment on capitalization, punctuation, written formatting, display formatting, ASR noise, or browser transcription artifacts."""

DISPLAY_TRANSCRIPT_MARKDOWN_RULES = """Also produce display_transcript_markdown:
- It must contain the same ASR-corrected wording as display_transcript.
- Split it into short spoken sentences, one sentence per paragraph, separated by blank lines.
- Do not add bullets, labels, quotes, or Markdown headings."""


def display_transcript_markdown_from_payload(value: Any, display_transcript: str, part: str = "") -> str:
    markdown = clean_markdown_text(str(value or ""))
    if markdown:
        return markdown
    return spoken_markdown(display_transcript, part)
