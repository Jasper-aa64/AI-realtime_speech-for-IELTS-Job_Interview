# Seed sync summary

## Counts

- P1 new topics: 46
- P1 new questions: 189
- P1 retained topics: 22
- P1 retained questions: 150
- P2 topics: 82
- P2/P3 follow-ups: 315
- Low-confidence archive: 9 legacy topic buckets / 60 questions, outside the app loader path

## Source decisions

- Current/new P1 was expanded from the local IELTSBro/Shenqi card cache and the tracked PDF text layer.
- Retained P1 now comes from `data/ielts/sources/2026_may_august_ielts_speaking_bank_0604.pdf`, which contains `Part 1 老题沿用（17 道+5 道万年老题）`.
- Low-confidence or older P1 material is kept in `data/ielts/archive/old_topics.json`; it is deliberately outside `data/ielts/part1` so it does not enter the current app bank.
- Laokaoya is recorded in `data/ielts/SOURCES.md` as a public spot-check only, not the main structured source.
- No AI-generated IELTS questions were added.

## Comparison rows

| topic | alias/source label | count | layer | action |
|---|---|---:|---|---|
| clothes | Clothing | 6 | A/current | expanded |
| headphones | Headphones | 5 | A/current | expanded |
| watches | Watch | 4 | A/current | expanded |
| cinema | Films/cinemas | 7 | A/current | expanded |
| ambition_and_dreams | Dream and ambition | 4 | A/current | expanded |
| outer_space_and_stars | Outer space and stars | 4 | A/current | expanded |
| social_media | Social media | 5 | A/current | expanded |
| public_gardens_and_parks | Public gardens and parks | 8 | A/current | expanded |
| websites | Websites | 7 | A/current | expanded |
| food | PDF retained | 4 | A/retained | imported |
| pets_and_animals | PDF retained | 8 | A/retained | imported |
| sports_team | PDF retained | 4 | A/retained | imported |
| hobby | PDF retained | 4 | A/retained | imported |
| morning_time | PDF retained | 5 | A/retained | imported |
| gifts | PDF retained | 5 | A/retained | imported |
| reading | PDF retained | 4 | A/retained | imported |
| walking | PDF retained | 5 | A/retained | imported |
| typing | PDF retained | 4 | A/retained | imported |
| scenery | PDF retained | 4 | A/retained | imported |
| building | PDF retained | 4 | A/retained | imported |
| childhood_activities | PDF retained | 4 | A/retained | imported |
| views | PDF retained | 4 | A/retained | imported |
| life_stages | PDF retained | 6 | A/retained | imported |
| free_time | Spare time | 3 | A/retained | imported |
| memory | PDF retained | 4 | A/retained | imported |
| crowded_places | Crowded place | 5 | A/retained | imported |
| study_or_work | evergreen PDF retained | 22 | A/retained | imported |
| home_and_accommodation | evergreen PDF retained | 17 | A/retained | imported |
| hometown | evergreen PDF retained | 15 | A/retained | imported |
| the_area_you_live_in | evergreen PDF retained | 7 | A/retained | imported |
| the_city_you_live_in | evergreen PDF retained | 11 | A/retained | imported |
| legacy_* | low-confidence older public lists | 60 | B/archive | moved outside loader |

## Validation

- `./.venv-django/bin/python scripts/validate_ieltsbro_seed_sync.py`
- `./.venv-django/bin/python backend_django/manage.py check`
- JSON parse checks for current P1/P2 and archive files
