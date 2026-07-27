# Market Prediction Engine — Claude Code Project Notes

## What this is

A probabilistic, self-learning market signal-weighting system, extracted and
enhanced from a CP3405 student project (sinder38/Team-1-Prac-A-Project — read
that repo directly if you need to compare, don't rely on any prior summary of
it). Not a "guaranteed prediction" tool. The real enhancement over the source
project is automated per-model trust weighting (EMA-based) replacing a manual
weekly human QA process — see `data/qa/` in the Team 1 repo for what that
manual process actually looked like, and `calibration/trust_weights.py` here
for the automated replacement.

## Model selection (cost matters — read before starting big tasks)

- **Default to Sonnet.** `~/.claude/settings.json` should have
  `{ "model": "sonnet" }`. Sonnet handles routine development, bug fixes,
  and frontend work in this repo fine.
- **Use Plan Mode (`Shift+Tab`) before any multi-file change.** Propose the
  plan, get it approved, then execute. Don't skip this to save a step —
  it's what prevents a small task from becoming an expensive one.
- **Only switch to Fable 5 for a single, bounded task**, in a **fresh
  session** (not mid-conversation — switching models mid-session makes the
  new model re-read the entire history, which costs more than starting
  clean). Good Fable use cases in this repo: a full end-to-end review of
  the pipeline with test-writing, or a genuinely large/ambiguous
  architecture decision. Not for routine edits.
- If Fable returns `stop_reason: "refusal"`, that's its safety classifier,
  not a bug — simplify the request rather than retrying the same thing
  harder.

## Repo structure

- `agents/technical/`, `agents/macro/`, `agents/almanac/` — signal agents,
  all confirmed working against live yfinance data as of the last verified
  run. No `agents/evidence/` yet (Team 1 has one; we don't).
- `agents/llm/multi_model_runner.py` — queries 4 free OpenRouter models
  (Nemotron, GPT-OSS, Gemma, Laguna), synthesizes via trust-weighted
  averaging. Known fragility here: free-tier rate limits (429s, Gemma and
  Laguna most weeks — a real OpenRouter free-tier ceiling, not a bug, and
  the pipeline already degrades gracefully by synthesizing from whichever
  models respond) and inconsistent JSON from some models — both have
  pacing/retry/parsing fixes already in place. **2026-07-27:** GPT-OSS was
  404ing every run because `openai/gpt-oss-120b:free` had been delisted from
  OpenRouter's free tier; swapped to `openai/gpt-oss-20b:free` and verified
  live. If a model starts consistently 404ing (not 429ing), check whether
  it's still listed on OpenRouter before assuming a code bug — free-tier
  model availability changes without notice.
- `calibration/` — trust weight EMA + automated scoring against actuals.
- `run_pipeline.py` — orchestrates a full weekly run for SPX/NDX/IWM only
  (Team 1 tracks 9 assets including macro hedges — we don't yet).
- `.github/workflows/` — weekly-pipeline.yml, weekly-scoring.yml. Both
  write their own log files to `data/logs/` on every run, success or
  failure, specifically so failures are diagnosable without needing
  GitHub's Actions log viewer.

## Debugging a failed or suspicious-looking run

1. Check `data/logs/pipeline_*.txt` (or `score_*.txt`) for the run in
   question FIRST — these are committed to the repo and contain the
   Python exit code plus a full `find data -type f` listing.
2. A workflow showing green/"success" in GitHub's UI does NOT automatically
   mean it produced output — `weekly-pipeline.yml` now has a real check for
   this (added 2026-07-27, after this exact gap masked a 404 for weeks): a
   step that counts today's prediction files and fails the run if fewer
   than 3 exist. Still cross-check log content against `data/predictions/`
   if something looks off — the check catches "zero output," not "wrong
   output."
3. **You (running locally via Claude Code) have normal internet access**
   and can use `gh run view --log` directly if you need the full raw
   Actions log — this is a real advantage over debugging through
   claude.ai's sandboxed tool environment, which cannot reach GitHub's
   log storage domain (Azure blob storage) and had to rely on the
   committed-log workaround above instead. Use `gh` directly when you
   have it.

## Standing technical rules

- Fetch the current file SHA immediately before any GitHub API PUT; never
  reuse a cached one. New files omit SHA entirely.
- Fine-grained GitHub PATs split permissions into separate buckets —
  Contents, Workflows, Actions, Secrets are each independent. A 403 on one
  doesn't mean the token is broken; check which specific permission is
  missing before assuming.
- Sandbox-test before touching anything already live/deployed.
- No automated tests exist in this repo yet (Team 1's source project has
  4 test files + CI type-checking — worth matching eventually, flagged as
  a known gap, not yet done).

## Companion site

Build progress and an honest, sourced comparison against the original
Team 1 project are tracked at:
- profdrtan.github.io/ai-playbook/build-log.html
- profdrtan.github.io/ai-playbook/team1-dissection.html

Both include a read-aloud feature (Web Speech API, matches the engine in
the main site's `index.html` — don't reinvent it if extending these pages).
If you make a real change here, update the build log's status/changelog
to match — don't let it go stale.
