# IELTS Scoring Issues and Prompt Revision Plan

Created: 2026-05-08

## Context

The current Web IELTS scorer is useful for end-to-end testing, but its scoring
behavior is not yet reliable enough for learner-facing feedback. The main issue
is not only model quality; the product contract is unclear:

- The user may type manually, paste an OCR result, use browser dictation, or use
  future speech-to-text.
- The scorer currently treats the transcript as clean spoken English.
- The prompt sometimes gives phrase-level correction advice that may be based
  on OCR/STT artifacts rather than the candidate's actual speaking.
- The UI shows numeric IELTS-like bands, so scoring mistakes feel authoritative.

## Research Notes

Official IELTS public material describes Speaking assessment through four
criteria:

- Fluency and Coherence
- Lexical Resource
- Grammatical Range and Accuracy
- Pronunciation

Relevant official sources:

- IELTS Speaking test format page:
  https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking
- IELTS Speaking key assessment criteria PDF:
  https://ielts.org/cdn/ielts-guides/ielts-speaking-key-assessment-criteria.pdf
- IELTS news/insights page explaining the four criteria:
  https://ielts.org/news-and-insights/demystifying-the-IELTS-speaking-test

Important implication:

- IELTS Speaking does not have a separate "Task Response" criterion like
  Writing, but answer relevance and topic development affect Fluency and
  Coherence, and vocabulary appropriacy affects Lexical Resource.
- Because this app may use OCR/STT/manual transcript, the scorer must not
  overinterpret suspicious tokens as confirmed spoken errors.

## Error Log

### E1 — Feedback Over-Trusts OCR/STT Artifacts

Observed:

- User used system OCR / imperfect transcript input.
- Scorer feedback suggested accurate phrases like `"tech-savvy"`.
- The transcript likely contained noisy text such as `"text savvy"` or similar.

Why this is bad:

- The app is a speaking practice tool, not a transcript proofreading tool.
- If input came from OCR/STT, the model should avoid acting as if every token
  is a deliberate spoken phrase.
- Feedback should say "transcript contains unclear/noisy wording" rather than
  prescribe a precise phrase unless confidence is high.

### E2 — Feedback Gives Phrase Coaching Instead of Speaking Diagnosis

Observed:

- Feedback focused on a local phrase correction instead of explaining speaking
  performance.

Better behavior:

- Prioritize:
  - relevance to question
  - coherence and development
  - range and control of language
  - grammar patterns
  - pronunciation confidence limits
- Avoid "say this exact phrase" unless the user explicitly asks for correction.

### E3 — Pronunciation Is Pretend-Scored From Text

Observed:

- UI shows Pronunciation band from transcript-only input.

Why this is risky:

- Without audio, pronunciation cannot be assessed reliably.
- Current "pronunciation_estimate" must be labeled as estimate / not assessed
  unless actual speech audio analysis exists.

### E4 — Off-Topic Handling Is Bolted On

Observed:

- Earlier P2 answer was mostly off-topic but received a high band because
  language quality was strong.

Current mitigation:

- Backend now passes the cue card/question to the scorer.
- Server caps clearly off-topic answers at overall 4.5.

Remaining issue:

- The cap is heuristic and should be represented as a scoring policy in the
  prompt and UI, not hidden logic only.

### E5 — Score Confidence Is Missing

Observed:

- UI presents a single band as if it were definitive.

Needed:

- Include score confidence or input quality:
  - `clean_transcript`
  - `possible_ocr_or_stt_noise`
  - `too_short`
  - `off_topic`
  - `pronunciation_not_assessed`

### E6 — Report Is Too Flat for Real Practice

Observed:

- The current score card gives bands plus one short paragraph.
- It does not explain each IELTS dimension in a learner-friendly way.
- It does not preserve a readable version of the user's answer.
- It does not provide a realistic upgraded answer that the learner can read
  aloud.

Needed:

- Keep the simple practice-page score card for quick feedback.
- Add a detailed report view with:
  - overall summary
  - structured criterion-by-criterion diagnosis
  - cleaned transcript
  - Band 7 sample answer
  - explanation of what changed

### E7 — P1/P3 Need Exam-Like Recording Flow

Observed:

- The Web UI currently behaves more like a text scoring tool.
- P1 and P3 should feel like speaking practice: short preparation, automatic
  recording, fixed speaking window, optional early stop.

Needed:

- P1: show question, 3-second preparation countdown, then auto-start recording.
- P3: show question, 7-second preparation countdown, then auto-start recording.
- Both parts need a visible recording timer and an early stop button.
- Browser dictation/OCR/manual input can still be used as transcript sources,
  but the UI should make the source explicit.

## Desired Scoring Contract

The scorer should return structured JSON like:

```json
{
  "fluency_coherence": 5.0,
  "lexical_resource": 5.0,
  "grammatical_range": 4.5,
  "pronunciation_estimate": null,
  "overall_band": 5.0,
  "confidence": "medium",
  "input_quality": {
    "source": "typed|ocr|stt|unknown",
    "possible_transcript_noise": true,
    "too_short": false,
    "off_topic": false
  },
  "feedback": {
    "summary": "...",
    "relevance": "...",
    "fluency": "...",
    "vocabulary": "...",
    "grammar": "...",
    "pronunciation_note": "Pronunciation was not assessed because only text was provided."
  },
  "suggestions": [
    "Develop one concrete example.",
    "Use clearer linking between contrastive ideas."
  ]
}
```

## Desired Detailed Report Contract

The practice screen should initially show only:

- numeric bands
- the same short comprehensive feedback as today
- backend/source/confidence badges
- a "View detailed report" action

The detailed report page/modal should show the full structured output:

```json
{
  "overall_comment": "Short综合评价，先说明整体水平和最重要的1-2个问题。",
  "criteria": {
    "fluency_coherence": {
      "band": 5.0,
      "strengths": ["..."],
      "problems": ["逻辑跳跃较大...", "衔接词使用单一..."],
      "suggestion": "Use Firstly/Secondly/However to make the structure clearer."
    },
    "lexical_resource": {
      "band": 5.0,
      "strengths": ["..."],
      "problems": ["technology repeated too often...", "unclear collocation..."],
      "suggestion": "Use topic-specific alternatives and avoid overcorrecting possible OCR noise."
    },
    "grammatical_range_accuracy": {
      "band": 4.5,
      "strengths": ["..."],
      "problems": ["subject mismatch...", "unfinished clause..."],
      "suggestion": "Add controlled complex sentences such as concessive and conditional structures."
    },
    "pronunciation": {
      "band": null,
      "strengths": [],
      "problems": [],
      "suggestion": "Not assessed from text-only transcript unless audio analysis is available."
    }
  },
  "cleaned_transcript": {
    "text": "Readable version of the user's answer with obvious OCR/STT artifacts cleaned.",
    "policy": "Do not change the user's ideas, order, examples, or meaning. Only fix obvious transcript artifacts, punctuation, and segmentation."
  },
  "band7_version": {
    "text": "A spoken Band 7 style version that preserves the user's core ideas while improving logic, grammar, vocabulary, and cohesion.",
    "practice_note": "Read this aloud as a model answer."
  },
  "upgrade_notes": [
    {
      "original_problem": "Topic jump from technology to personality with no bridge.",
      "band7_change": "Added a transition such as 'personality also plays a role'."
    },
    {
      "original_problem": "Repeated 'technology' many times.",
      "band7_change": "Used alternatives such as innovation, digital tools, new things, and change."
    }
  ]
}
```

### Detailed Report Layout

1. Header score summary:
   - Overall band
   - FC / LR / GRA / Pronunciation-or-Not-Assessed
   - short comprehensive comment
2. "📊 各维度评分":
   - Fluency & Coherence
   - Lexical Resource
   - Grammatical Range & Accuracy
   - Pronunciation note if no audio analysis exists
   - each section has `亮点`, `问题`, and `建议` when available
3. Two-column answer section:
   - left: cleaned transcript, labeled as "你的回答（清理转写错误后）"
   - right: "Band 7 修改版本"
4. Bottom section:
   - "🔍 升级了哪些地方"
   - table with original issue and Band 7 change

Important product rule:

- The practice view must not show every detailed module by default. It should
  remain fast and calm: score + short feedback first, details only after user
  clicks into the detail report.

## Transcript and OCR Policy

The app may use browser dictation, manual typing, OCR, or future STT. The backend
must keep separate fields instead of mixing everything into one string:

- `raw_transcript`: exactly what the browser/user supplied.
- `input_source`: `typed | ocr | browser_dictation | stt | unknown`.
- `cleaned_transcript`: readability cleanup only.
- `cleaning_notes`: short notes about likely OCR/STT artifacts.

Cleanup rules:

- Allowed:
  - punctuation
  - line breaks
  - obvious OCR/STT fragments
  - obvious homophone/transcription artifacts when context is clear
- Not allowed:
  - inventing new examples
  - changing the user's stance
  - replacing weak ideas with stronger ideas
  - silently turning a bad answer into a good answer before scoring

Scoring should use both `raw_transcript` and `cleaned_transcript`:

- `raw_transcript` protects against hiding real language problems.
- `cleaned_transcript` makes the report readable.
- If the cleanup is uncertain, the report should say the transcript may be
  noisy instead of making precise correction claims.

## Prompt Revision Principles

### P1 — Treat Transcript as Evidence, Not Ground Truth

Prompt must say:

- The transcript may contain OCR/STT/manual typing errors.
- Do not over-penalize isolated suspicious tokens if the intended meaning is
  inferable.
- If a phrase looks like OCR/STT noise, mark it as possible transcript noise
  instead of presenting it as a definite speaking mistake.

### P2 — Do Not Provide Exact Phrase Prescription by Default

Prompt must avoid:

- "Use accurate phrases like X" unless asked for phrase correction.

Prompt should prefer:

- "Your vocabulary choice was sometimes unclear around technology users."
- "Use one precise noun phrase to define the group you mean."

### P3 — Separate Relevance From Language Quality

Prompt must:

- Evaluate whether the answer addresses the current question/cue card.
- If not, lower FC and cap overall.
- Still acknowledge language quality separately.

### P4 — Pronunciation Requires Audio

Prompt must:

- If input is transcript-only, set pronunciation as `null` or clearly label it
  as an estimate.
- UI should not present it as a real pronunciation band without audio.

### P5 — Feedback Should Be Learner-Useful

Feedback should be:

- short
- actionable
- criterion-aware
- not overly confident about noisy transcript tokens
- focused on next attempt behavior

## Implementation Plan

### Phase 1 — Add Input Source and Confidence to Web UI/API

- Add source selector near transcript:
  - Typed
  - OCR
  - Browser dictation/STT
  - Unknown
- Send `input_source` with `/api/score`.
- Show scoring caveat in UI:
  - "Pronunciation is not assessed from text-only input."
  - "OCR/STT noise may affect feedback."

### Phase 2 — Redesign Scorer Prompt

- Rewrite `data/ielts/prompts/scorer_system.md`.
- Add explicit transcript-noise handling.
- Add relevance policy.
- Add feedback style constraints:
  - no exact phrase prescriptions by default
  - no false certainty about OCR/STT artifacts
  - no pronunciation certainty from text only

### Phase 3 — Change Score JSON Schema

- Update backend parser to accept the new structured feedback fields.
- Preserve backward compatibility with current flat JSON while testing.
- Update frontend renderer to show:
  - overall / FC / LR / GRA
  - pronunciation note
  - input quality badges
  - feedback sections

### Phase 4 — Add Regression Test Cases

Add scorer contract tests or saved prompt fixtures for:

1. Clean relevant answer.
2. Off-topic but fluent answer.
3. OCR-noisy answer with suspicious phrase.
4. Very short answer.
5. Non-English answer.
6. Transcript-only answer where pronunciation should not be treated as real.

### Phase 5 — Calibrate Bands

- Run 10-20 sample answers manually through Codex.
- Compare output against expected ranges.
- Adjust prompt and server-side caps.
- Document known limitations.

### Phase 6 — Build Detailed Report UX

- Add a detailed report route or modal.
- Practice pages show only compact score + summary.
- The detail action opens the full report layout described above.
- Store the current part/question/cue card with the score so P2 results cannot
  appear as generic score cards on unrelated pages.

### Phase 7 — Add P1/P3 Timed Speaking Flow

- P1:
  - select/load question
  - 3-second preparation countdown
  - auto-start recording/dictation window
  - fixed max answer duration
  - early stop button
- P3:
  - generate/show discussion question
  - 7-second preparation countdown
  - auto-start recording/dictation window
  - fixed max answer duration
  - early stop button
- Persist transcript source with each answer.
- If browser dictation is unavailable, keep manual transcript fallback but label
  it clearly.

## Open Questions for Discussion

1. Should the UI keep showing a numeric Pronunciation score for text-only input,
   or replace it with "Not assessed"?
2. Should the default scoring mode be strict exam-style, or coaching-style with
   more explanation?
3. Should OCR/STT cleanup happen before scoring, or should the scorer receive
   the raw transcript plus `input_source`?
4. Should phrase correction be a separate button, e.g. "Improve my answer",
   instead of being mixed into IELTS scoring feedback?
5. What should the default recording duration be for P1 and P3?
   - Tentative: P1 30-45 seconds per answer, P3 60-90 seconds per answer.
6. Should the Band 7 rewrite target exactly Band 7, or allow "Band 7+ model"
   when the user's idea quality supports it?

## Current Recommendation

Do not keep patching the current prompt one sentence at a time. The next proper
change should be a scorer contract revision:

- add `input_source`
- make pronunciation text-only limitations explicit
- add structured feedback
- add compact score vs detailed report separation
- add cleaned transcript and Band 7 rewrite fields
- add P1/P3 timed recording flow
- add regression fixtures for noisy OCR/STT
- keep exact phrase correction out of default IELTS scoring
