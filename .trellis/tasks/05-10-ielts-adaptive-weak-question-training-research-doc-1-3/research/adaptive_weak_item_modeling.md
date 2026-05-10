# Adaptive weak-item modeling research notes

## Why this is not a toy problem

The feature is not just “show low-score questions more often.” The system must solve three different problems:

1. Estimate the learner's latent ability over time.
2. Estimate each item's difficulty / discrimination and whether the learner is repeatedly misunderstanding it.
3. Decide when to replay an item without overexposing the same weak question.

That suggests a statistical pipeline instead of a hard-coded score threshold.

## Candidate modeling stack

### 1) IRT / graded response model for score calibration

Use item response theory to model the probability that a learner reaches or exceeds a score threshold for a given question and rubric dimension.

Example form:

`P(Y_{uqd} >= k) = sigmoid(a_{qd} * (theta_{ud} - b_{qdk}))`

Where:

* `u` = learner
* `q` = question
* `d` = rubric dimension or relevance dimension
* `k` = ordinal score threshold
* `theta` = learner ability
* `a` = discrimination
* `b` = threshold / difficulty

This is better than a raw weighted average because IELTS bands are ordinal, not interval truth values.

### 2) Bayesian knowledge tracing / hierarchical mastery tracking

Track mastery state over time for each learner-topic pair or learner-skill pair.

Useful state variables:

* `p_mastery(u, skill)`
* `p_forget(u, skill)`
* `p_misread(u, topic)`

This is useful for recurring practice because the system can distinguish “one bad attempt” from “still weak.”

### 3) Spaced repetition / forgetting curve for replay timing

Replay frequency should decay with mastery and increase after failure.

Example:

`next_due(q,u) = now + base_interval(q) * exp(-gamma * mastery(u,q))`

or

`priority(q,u,t) = failure_prob(q,u) * exp(-lambda * days_since_last_seen(q,u))`

Spacing effect evidence supports distributed review rather than massed repetition.

### 4) Bandit-style selection for candidate replay

From the pool of weak items, select the next item by balancing exploitation and exploration.

Example:

`score_select(q) = alpha * failure_prob(q) + beta * uncertainty(q) + delta * information_gain(q) - eta * exposure_penalty(q)`

Then sample with Thompson sampling or softmax over that score.

This avoids collapsing into a deterministic “always show the worst item first” loop.

## Weak-item definition

Do not define weakness as a single score threshold.

Use a composite weak-item posterior:

`W(u,q) = w1 * P(low_band | data) + w2 * P(off_topic | data) + w3 * uncertainty + w4 * recency_decay + w5 * repetition_penalty`

Practical rule:

* mark `weak_candidate` when `W(u,q) > tau_1`
* promote to `weak_item` when `P(W(u,q) > tau_1 | data) > 0.8`
* demote only after repeated successful recoveries

This gives shrinkage against false positives.

## What to store

Each answer record should persist:

* attempt_id / turn_id / question_id
* transcript and audio pointer
* band scores per dimension
* relevance / off-topic label
* model confidence or fallback reason
* error tags: short answer, repeat-heavy, grammar-heavy, off-topic, pronunciation-unreliable
* model version and timestamp

That lets the system do longitudinal analysis later.

## Current repo implication

The repo already has:

* scored attempts
* turn-level reports
* history
* question bank JSON files

Missing pieces:

* item-level stats table
* weak-item labels and counts
* replay scheduler
* confidence calibration
* off-topic classifier or relevance posterior

## Evaluation metrics

A non-toy design needs offline metrics, not just “looks useful”:

* score calibration error
* AUC / F1 for weak-item detection
* expected information gain per replay
* exposure entropy across the bank
* learning gain after replay
* false-positive rate for weak-item marking

## Implementation guidance

Best first version:

1. Start with hierarchical Bayesian scoring of item weakness.
2. Add relevance/off-topic detection as a separate signal.
3. Use Thompson sampling or information gain to choose replay items.
4. Enforce exposure caps and cooldown windows.
5. Only promote a question to weak status after repeated posterior evidence.
