# Context Linking

Layer 5 connects `NormalizedInput` records to known Athlete Context entities by
exact identifiers and explicit repository references. It returns a derived link
result and does not create or modify domain records.

## Linking flow

1. Determine the record type from an explicit `record_type` value. Message and
   document-text inputs map to `MESSAGE` and `DOCUMENT` when no structured record
   type is supplied.
2. Read only structured `athlete_id`, `competition_id`, and `event_id` values or
   their `athlete_reference`, `competition_reference`, and `event_reference`
   equivalents.
3. Resolve each value through the supplied in-memory repository using exact
   equality.
4. Return matched identifiers, unresolved references, provenance, original and
   translated text, and an explicit link status.

Free text is never mined for identifiers or names. There is no fuzzy matching,
embedding search, vector database, machine learning, or inferred identity.

## Link outcomes

- `LINKED`: every required or explicitly supplied reference resolved exactly.
- `PARTIALLY_LINKED`: at least one reference resolved while another required or
  supplied reference remains unresolved.
- `UNRESOLVED`: nothing resolved, or the record type is unknown.
- `CONFLICT`: an exact reference has multiple candidates, explicit references
  identify different entities, or an event belongs to a different explicitly
  matched competition.

`RESULT` requires explicit athlete, competition, and event references.
`STANDARD` requires an event, and `PROFESSIONAL_FEEDBACK` requires an athlete.
Missing required references remain visible in `unresolved_references`; the
service does not derive a missing competition from an event.

## Provenance and verification

The result preserves the input ID, source ID, capture timestamp, content type,
original and translated text, languages, translation status, and a copy of the
structured payload. Linking never overwrites a `NormalizedInput` or modifies a
`HistoricalResult`.

An exact link establishes identity correspondence only. It does not verify the
input's factual claims. Linked results, including messages and documents, remain
`UNVERIFIED`; incompatible links use `CONFLICT`. The service never produces
`VERIFIED` information.

## Layer boundary

Layer 5 does not parse source files, call external APIs, persist data, monitor
federations, automate competition lifecycles, generate explanations or coaching,
or process real athlete data. Layer 6 and later may consume these explicit link
results, but those workflows are outside Context Linking and are not implemented
here.
