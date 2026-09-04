# Athlete Context

## AI Athlete Performance & Career Agent

An AI system for connecting athlete performance data, competition information, official results and historical analytics into one verified context.

## Current implementation

Layers 1–7 are implemented: the Pydantic foundation/domain models, historical
results, deterministic historical performance analytics, the parsing and
translation foundation, Context Linking, and the approved-competition lifecycle
and federation-monitoring foundation. The deterministic Explanation Layer now
formats verified and linked context into traceable, neutral Russian or English
summaries without generating advice.

Autonomous competition selection, real PDF/OCR/HTML parsing, live translation,
continuous federation crawling, TYF integration, external APIs, production
persistence, background scheduling, coaching recommendations, and production
deployment are not implemented.

## Demo

A deterministic, synthetic end-to-end demo connects the implemented Layers 1–7
without external services or real athlete data. Run it from the repository root:

```bash
.venv/bin/python examples/demo_end_to_end.py
```

The scenario is documented in [docs/demo-scenario.md](docs/demo-scenario.md).
