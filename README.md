# Athlete Context

## AI Athlete Performance & Career Agent

An AI system for connecting athlete performance data, competition information, official results and historical analytics into one verified context.

## Current implementation

Layers 1–3 are implemented: the Pydantic foundation/domain models, historical
results, and deterministic historical performance analytics. The current scope
contains validated entities, explicit verification states, source provenance,
swim-time normalization, persistence-independent historical-result ingestion,
and read-only PB, progression, delta, standard-gap, trend, and consistency
calculations.

Source parsing, monitoring, translation, context linking, external APIs,
production persistence, and explanation or coaching generation are not
implemented.
