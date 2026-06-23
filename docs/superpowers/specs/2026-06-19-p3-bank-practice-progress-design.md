# P3 Fixed-Bank Practice Progress Design

Fixed P3 follow-ups are split into stable rounds owned by the backend. Three or four questions form one round; five form `[1,2,3]` and `[4,5,3]`; six form `[1,2,3]` and `[4,5,6]`. The repeated third question in the five-question case acts as a bridge and avoids a two-question session.

Each started bank attempt records its cue ID, round index/count, and selected follow-up IDs in `SpeakingAttempt.metadata`. Progress is derived only from attempts that are scored and have a persisted report. No new model is required.

The P3 card picker receives `practice_round_count`, `practice_completed_rounds`, `practice_completed_round_indexes`, and `practice_is_complete`. It displays partial progress, dims fully completed cards, and keeps every card clickable. Once all rounds have been completed, subsequent practice selects the least-practised round so repetition remains balanced.

This behavior applies only to fixed-bank P3 practice. AI-generated P3 from reports and custom themes remains unchanged.

