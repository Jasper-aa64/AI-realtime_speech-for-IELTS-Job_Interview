# IELTS Speaking 2026 May-August Bank Review

## Scope

This review checks whether the local speaking bank covers China mainland 2026 May-August season signals well enough for practice. These public pages are unofficial preparation sources, not official IELTS publications. They are used only to improve topic coverage; local cue cards and questions are written in IELTS style rather than copied from third-party answer material.

## Sources Checked

- New Oriental: `https://mtoutiao.xdf.cn/ielts/202605/15188096.html`
- New Channel Shanghai: `https://sh.xhd.cn/ielts/ysrrbwz/966602.html`
- New Channel season timing note: `https://wap.xhd.cn/ielts/kouyu/206445.html`
- Koolearn public speaking practice pages: `https://liuxue.koolearn.com/ielts/speak-1-0-0/` and `https://liuxue.koolearn.com/ielts/speak-2-0-0`
- IELTSBro question-bank product page was checked as a product/source signal: `https://www.ieltsbro.com/question-bank/`
- Xiaohongshu/Zhihu-style public prep posts were treated as weak corroboration only. They are useful for seeing which topics candidates are preparing, but not reliable enough to be the sole source of a bank entry.

## Local Coverage Before

- Part 1 2026 May-August new bank: 63 questions across 21 topics.
- Part 1 2026 May-August retained bank: 51 questions across 17 topics.
- Part 2 2026 May-August bank: 26 cue cards.
- Region was already marked as `china_mainland`.

## Gaps Found

Part 1 was missing several repeatedly visible public-season topics:

- `study_or_work`
- `singing`
- `tidiness`
- `watches`
- `public_gardens_and_parks`
- `websites`
- `ambition_and_dreams`
- `social_media`
- `talking_to_elderly_people`
- `cinema`
- `headphones`
- `old_buildings`
- `evening_time`
- `cars`
- `shopping`
- `clothes`
- `jokes`
- `happy_things`
- `holidays`

Part 2 was missing the main 2026 May-August new-topic cluster listed publicly by New Oriental:

- medical-field career person
- successful business person
- boring place
- tall building liked/disliked
- building to visit
- travel destination
- food on a special occasion
- wild animal to know more about
- traditional object
- local news
- watching a sports match
- trying a new activity
- waiting for something special
- power outage
- traditional custom
- fixing something broken
- changing a decision

## Changes Made

- Expanded `data/ielts/part1/2026_may_august_new_topics.json` from 63 to 120 questions.
- Expanded P1 new-topic coverage from 21 to 40 topics.
- Expanded `data/ielts/part2/2026_may_august_topics.json` from 26 to 43 cue cards.
- Preserved `region: china_mainland`.
- Updated source metadata to mark the bank as cross-checked against public mainland China season lists.
- Added regression coverage in `backend_django/apps/speaking/tests.py` for:
  - minimum P1/P2 bank size
  - `china_mainland` region
  - key P1 topics: `social_media`, `study_or_work`, `public_gardens_and_parks`
  - key P2 themes: `medical_work_and_public_health`, `traditional_customs_and_modern_life`, `repairing_things_and_practical_skills`

## Verification

- `python backend_django/manage.py test apps.speaking` passed: 87 tests OK.
- `python -m unittest tests.test_ielts_web_server -q` passed: 62 tests OK.

Known noise: the Django test run still prints existing sqlite lock exceptions from background examiner TTS threads. The test suite completes successfully; this is not introduced by the bank update.

