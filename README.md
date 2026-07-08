# Market Prediction Engine

A probabilistic, self-learning market signal system, built on the architecture
pattern of CP3405 Team 1 (`sinder38/Team-1-Prac-A-Project`) with three concrete
enhancements. This is a probability-weighting engine, not a certainty machine —
see "What this is (and isn't)" below.

## What this is (and isn't)

This system produces probability-weighted directional calls with tracked
historical accuracy — it does not and cannot guarantee correct market
predictions. No system can. What it *can* do, and what makes it "self-learning"
in a real sense: it tracks which models and signals have been accurate over
time and weights future synthesis accordingly, so its aggregate judgment
should improve as more weeks of track record accumulate. Treat its output as
a structured, evolving opinion — not a signal to trade on blindly.

## Three enhancements over Team 1

**1. Trust-weighted synthesis, not simple averaging or majority vote**
Team 1 ran four LLMs and compared them in a manual "horse race," but the
comparison never fed back into the next prediction — every model was always
weighted equally going forward, win or lose. Here, each model's calibration
score (direction + range accuracy) updates a running trust weight
(`calibration/trust_weights.py`) via exponential moving average. A model that's
been consistently wrong contributes less to next week's synthesized call — but
never zero, so the ensemble stays diverse. Team 1's own data showed this
matters: in Week 23, all four of their models called direction wrong; a
trust-weighted system would already be down-weighting models with a run of
misses like that.

**2. Fully automated calibration scoring**
Team 1's calibration and learning logs were written by hand each week by a
"QA and Learning Log Lead" role. `calibration/score_predictions.py` does the
same comparison programmatically — pulls actual returns, checks each model's
call, updates trust weights — with zero manual steps.

**3. End-to-end automation, no manual trigger**
Two GitHub Actions workflows: one predicts each Monday, one scores the
previous week's prediction against actuals and updates trust weights before
the new prediction runs. Team 1's pipeline required a human role to run and
interpret each stage.

## Architecture

```
run_pipeline.py
├── agents/technical/   → trend, RSI, moving-average distance, momentum
├── agents/macro/       → risk-on/risk-off regime from DXY, yields, oil, gold, VIX
├── agents/almanac/     → seasonal bias from historical monthly returns
├── agents/llm/         → queries 4 free-tier models via OpenRouter with
│                          identical structured prompts, returns JSON calls
└── calibration/
    ├── trust_weights.py     → EMA-based trust score per model
    └── score_predictions.py → automated actual-vs-predicted scoring
```

Each ticker gets its own technical + almanac read; macro regime is computed
once and shared, since it's not ticker-specific.

## Setup

1. Add repo secret `OPENROUTER_API_KEY` (free tier at openrouter.ai covers the
   four models used here — no cost for the model calls themselves)
2. Enable GitHub Actions (on by default)
3. Manually trigger `Weekly Prediction Pipeline` once to generate the first
   prediction (Actions tab → workflow → Run workflow) — needs live internet
   access to Yahoo Finance and OpenRouter, which only the Actions runner has
4. The following Monday, `Weekly Calibration Scoring` runs automatically once
   actuals exist, updating trust weights before that day's new prediction

## Honest limitations

- Trust weights need many weeks of data before they meaningfully diverge —
  early weeks are close to an equal-weighted average by design
- Free-tier OpenRouter models may be rate-limited or occasionally unavailable;
  the pipeline skips a model on failure rather than blocking the whole run
- This is built for learning and signal-tracking purposes; it is not
  investment advice, and no calibration score, however good, changes that
