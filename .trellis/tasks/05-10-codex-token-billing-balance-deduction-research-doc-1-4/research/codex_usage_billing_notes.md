# Codex token usage and billing research notes

## Local observation

Running:

```bash
codex exec --json
```

returns a JSON event stream that includes:

* `turn.completed`
* `usage.input_tokens`
* `usage.cached_input_tokens`
* `usage.output_tokens`
* `usage.reasoning_output_tokens`

It does **not** emit a direct RMB cost in the observed output.

## Implication

The application cannot rely on Codex to hand back a final RMB amount. It must compute wallet charges from:

1. captured usage tokens
2. a versioned pricing snapshot
3. an explicit currency conversion / business price table

## Billing rule

* Treat `input_tokens` as gross input usage.
* Subtract `cached_input_tokens` into a cheaper cached-input bucket.
* Treat `output_tokens` as the billable output total.
* Do not add `reasoning_output_tokens` again if the provider already includes reasoning inside `output_tokens`; use it for diagnostics and reserve sizing.

## Risk

If billing is based only on the visible prompt or only on the user's text, the app will undercharge because Codex / hook injection / system context all contribute to billable input.

