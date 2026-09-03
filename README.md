# Athlete Context

## AI Athlete Performance & Career Agent

An AI system for connecting athlete performance data, competition information, official results and historical analytics into one verified context.

## Current implementation

Layer 1 foundation/domain models and the Layer 2 historical results layer are
implemented with Pydantic. The current scope contains validated entities,
explicit verification states, source provenance, deterministic swim-time
normalization, and persistence-independent historical-result ingestion.

Historical analytics, source parsing, monitoring, translation, external APIs,
production persistence, and explanation generation are not implemented.
