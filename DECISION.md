# Decision Log

## Why trust-weighted synthesis instead of majority vote or simple average

Team 1's four-model comparison is genuinely useful data — it exists in their
`llm_horserace_WXX.md` files. But it's read-only: this week's horse race
result doesn't change how much weight next week's prediction gives to each
model. An exponential moving average was chosen over a hard cutoff (e.g.
"drop any model below 50% accuracy") because markets are noisy — a model
having one bad week doesn't mean it's structurally worse, and a hard cutoff
would overreact to small samples. EMA lets trust shift gradually, weighted
toward recent performance without discarding history entirely.

## Why a minimum weight floor

Without `MIN_WEIGHT`, a model on a losing streak could be weighted to
effectively zero, which defeats the purpose of an ensemble — you'd end up
trusting one model completely based on a small number of observations, which
is exactly the overconfidence this project exists to avoid.

## Why automate calibration scoring instead of keeping Team 1's QA role

Team 1's manual QA process produces genuinely thoughtful learning logs — the
writing itself is valuable pedagogically. For a hands-off production system,
though, the actual scoring math (was direction correct, was the range hit)
is mechanical and better handled by code that runs reliably every week
without depending on someone remembering to do it.

## Why macro regime is computed once, not per-ticker

DXY, yields, oil, gold, and VIX describe the broader macro environment, not
any single ticker's specific move. Computing it once and sharing it across
all three tracked indices avoids redundant API calls and reflects that the
regime classification is genuinely ticker-independent.

## Why OpenRouter instead of direct provider APIs

Matches Team 1's four-model comparison approach (multiple providers, not
just one) while using free-tier models, keeping the recurring cost close to
zero — consistent with treating this as a low-cost, hands-off system rather
than one requiring ongoing paid API budgets across four separate providers.
