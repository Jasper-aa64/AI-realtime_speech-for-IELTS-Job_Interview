# sync complete ieltsbro p1 p2 p3 question bank

## Goal

Update the read-only IELTS speaking seed question bank so the app matches the fuller IELTSBro/Shenqi 2026 May-August bank: P1 topics should include all listed questions where available, P2 should include missing current topics, and P3 follow-ups should preserve the full set instead of truncating to three. This must not overwrite or synthesize user-owned corpus entries.

## What I already know

* Current app seed data lives under `data/ielts/part1` and `data/ielts/part2`.
* Current 2026 May-August P1 JSON has 57 topics total and exactly 3 questions per topic.
* Existing local scrape under `.firecrawl/ieltsbro-api/question-pics/` contains IELTSBro topic-card images, including P1 `Clothing` with 6 questions and `Headphones` with 5 questions.
* Existing local scrape includes P2/P3 topic-card images and catalog metadata from IELTSBro, but only the image cards are known to include full question text.
* The app’s user corpus models are separate from seed question JSON; this task should update seed bank only.

## Assumptions

* If an IELTSBro card has more questions than the current seed JSON for the same topic, IELTSBro is treated as the fuller source for that topic.
* Existing user corpus rows are keyed by question IDs derived from topic+question; adding new questions is safe, but changing existing question wording may create new seed IDs. Avoid wording churn unless the current wording is materially incomplete or wrong.
* P3 follow-ups should use all follow-ups found on the topic card, not force a 3-item cap for IELTSBro bank mode.

## Requirements

* Import/merge fuller P1 question lists from IELTSBro/Shenqi for current 2026 May-August topics.
* Import/merge missing P2 topics such as `想颁布的新法律` / new law if present in the current IELTSBro bank.
* Preserve up to all P3 follow-ups on seed P2 topic cards, including 6-question sets such as `Describe a time when you got up early`.
* Keep user-owned corpus content untouched.
* Keep data source metadata clear enough to understand where the fuller bank came from.

## Acceptance Criteria

* [ ] P1 `Clothing` shows the 6 IELTSBro questions.
* [ ] P1 `Headphones` shows the 5 IELTSBro questions.
* [ ] P2/P3 `Describe a time when you got up early` has 6 P3 follow-ups.
* [ ] Missing current P2 topic `想颁布的新法律` appears if present in source data.
* [ ] Backend question-bank summary and app rendering still work.
* [ ] Existing user corpus save/delete behavior is not changed.

## Definition of Done

* Data import/update is repeatable or at least documented.
* `manage.py check` passes.
* Relevant Python/JSON validation passes.
* Frontend cache string updated only if code changes are needed.

## Out of Scope

* No changes to personal corpus models or saved user data.
* No AI generation of fake IELTS questions.
* No redesign of the P1/P2/P3 library UI unless needed to display the fuller data.

## Technical Notes

* Candidate files: `data/ielts/part1/2026_may_august_new_topics.json`, `data/ielts/part1/2026_may_august_retained_topics.json`, `data/ielts/part2/2026_may_august_topics.json`.
* Candidate source cache: `.firecrawl/ieltsbro-api/question-pics/` and `.firecrawl/ieltsbro-api/*catalog*.json`.
* Need inspect/possibly refresh source because user says P2/P3 updated at `2026-06-10 18:51:15`.
