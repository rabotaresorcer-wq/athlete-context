# End-to-End MVP Demo

The demo uses only fictional, deterministic data to show how the implemented
Layers 1–7 work together. It does not contact federation systems, translation
services, or any other external API.

The scenario starts with a Turkish message about a synthetic athlete's 50 m
freestyle result in a long-course pool. Input processing keeps the original
Turkish text unchanged, detects its language, and stores a deterministic Russian
translation as derivative content. Context linking then resolves explicit
athlete, competition, and event identifiers without interpreting free text or
guessing entities.

Four structured results are ingested from fictional official-style sources.
Three long-course results form the comparable history; a faster short-course
result is retained but deliberately excluded from the main comparison. The
analytics layer reports the personal best, change from the previous comparable
result, progression, trend, and consistency without mixing pool lengths.

The same fictional competition is explicitly approved before its monitoring
plan is created. A scoped, pre-supplied federation-style update is recorded and
handed off to the existing verified historical result, allowing the competition
lifecycle to close. No live monitoring, crawling, or external access occurs.

The final Russian explanation is generated from the verified result, preserved
provenance, linked context, and precomputed analytics. Translation and linking
alone never promote the source message to a verified fact.

Run the demo from the repository root after installing the project dependencies:

```bash
.venv/bin/python examples/demo_end_to_end.py
```
