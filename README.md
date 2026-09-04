# Athlete Context

## AI Athlete Performance & Career Agent

An AI system for connecting athlete performance data, competition information, official results and historical analytics into one verified context.

## Current implementation

Layers 1–4 are implemented: the Pydantic foundation/domain models, historical
results, deterministic historical performance analytics, and the parsing and
translation foundation. The current scope contains validated entities, explicit
verification states, source provenance, swim-time normalization,
persistence-independent historical-result ingestion, read-only performance
analytics, and deterministic processing of existing text and structured input.

Real PDF, OCR, and HTML parsing; live translation; monitoring; context linking;
external APIs; production persistence; competition lifecycle automation; and
explanation or coaching generation are not implemented.
