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

这是口语辅导，不是写作批改。你评价的是“这个人说得怎么样”，不是“转写文本写得对不对”。
- 严禁点评大小写、标点、拼写、换行或任何书面格式；例如不要说“University 应该小写”或某句缺标点。原因：真实口语考试里没有大小写和标点，这些只是语音转文字留下的痕迹，和考生口语水平无关；点评它们只会浪费学习者注意力。
- 评价只基于 display_transcript，也就是已经修正明显机器听错后的版本；被当作 ASR 听错修正掉的词，不要再当成考生的语法/用词错误批评。

正文要求：
- 先用 1-2 句话说清楚这次回答最大的问题。
- 然后用分点方式给出立即改进点；每一点内部直接说明问题和改法，不要套用固定模板。
- 不要使用“→ 改法：”这类固定结构。
- 立即改进点可以包含逻辑连贯、连接词、内容展开、表达自然度等问题，由你根据回答自行决定数量和顺序。

**语法 & 表达纠正：**
分点列出；每点按内容自然表达，不限制固定格式。
只纠正影响口语表达的语法、搭配、用词；不要纠正大小写、标点或书面格式。
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
这是口语辅导，不是写作批改：严禁点评大小写、标点、拼写、ASR 噪声或转写显示格式。原因：真实口语考试不存在这些书面元素，它们只是语音转文字的痕迹，与口语水平无关，点评它们既跑题又显得外行。被当作 ASR 听错、已在 display_transcript 修正掉的词，也不要再当成考生错误来纠正。"""
    return """请用中文给这一次回答做简短 IELTS Speaking 口语反馈，只输出正文，不要标题。
先判断真实考试里最影响分数的问题，只讲最值得改的 1-2 点，具体、短、能马上照着改。
最后保留「语法 & 表达纠正」部分；如无错误，写：无。"""


DISPLAY_TRANSCRIPT_ASR_RULES = """display_transcript is what the candidate actually said, lightly cleaned for display and scoring. Treat it as a faithful record of their speech, not a rewrite.
Why this matters: the learner reads "Your recording" to verify what they said, and ALL coaching and the Band score are based on it. If you silently change their real words, the feedback no longer matches their answer and the learner stops trusting it.
- Only fix words that are clearly ASR (speech-to-text) mis-recognitions: a token that is meaningless or impossible in this exact question context, where a phonetically similar word is obviously what they meant.
- Confident ASR fixes (do apply): for a science question "Songs plays a vital role" -> "Science plays a vital role"; "sync my teeth into" -> "sink my teeth into"; "I'm a big fellows long holidays" -> "I'm a big fan of long holidays"; "Do the future" -> "In the future"; a stray name-like junk token such as "a very Morgan isolated way" -> "a very isolated way" (drop ONLY the junk token).
- Never drop or alter a real content word the candidate genuinely said, even if it looks redundant. Example: keep "a very modern, isolated way of living" exactly as is — do NOT shorten it to "a very isolated way of living". Deleting a real word changes their meaning and is worse than leaving slightly odd phrasing.
- Keep the candidate's genuine learner errors (grammar, collocation, word choice) so coaching can address them, e.g. keep "I'm a university student major in software engineering" unchanged.
- If you are unsure whether a word is an ASR error or something they really said, keep it. When in doubt, preserve.
- Do not add ideas, upgrade vocabulary, fix grammar, or turn display_transcript into a Band 7 answer — that belongs in band7_version, not here.
- Anything you corrected as ASR noise must NOT then be criticised in ai_coaching; only coach the real learner errors that remain.
This is spoken-English coaching, so ignore writing-only artifacts entirely:
- Do not comment on capitalization, punctuation, spelling, or written formatting.
- Never comment on capitalization, punctuation, spelling, or written formatting (e.g. do not say "University" should be lowercase, or that a sentence needs a period). Why: a real speaking test has no capitals or punctuation — these are only artifacts of turning speech into text and say nothing about how the candidate actually spoke; commenting on them wastes the learner's attention and looks amateurish."""

DISPLAY_TRANSCRIPT_MARKDOWN_RULES = """Also produce display_transcript_markdown:
- It must contain the same ASR-corrected wording as display_transcript.
- Split it into short spoken sentences, one sentence per paragraph, separated by blank lines.
- Do not add bullets, labels, quotes, or Markdown headings."""


def display_transcript_markdown_from_payload(value: Any, display_transcript: str, part: str = "") -> str:
    markdown = clean_markdown_text(str(value or ""))
    if markdown:
        return markdown
    return spoken_markdown(display_transcript, part)
