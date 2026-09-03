# Domain model

Layer 1 defines the validated domain vocabulary for Athlete Context. The models
contain no API, database, monitoring, parsing, translation, or analytics logic.

## Entities

- **Athlete** identifies the person whose performance context is recorded.
- **Competition** describes a competition and its date range.
- **Event** belongs to one competition and describes a discipline/category.
- **Result** links directly to an athlete, competition, event, and primary
  source.
- **Standard** belongs to an event and can be qualified by age range, category,
  validity period, and additional textual context.
- **Source** preserves provenance: the original source, reference or URL, source
  type, capture time, original language, and verification status.
- **Message**, **Document**, **ProfessionalFeedback**, and
  **FederationUpdate** preserve source material. Their verification status
  concerns record authenticity only; their content is not automatically a
  verified fact.

## Relationships and verification

`ResultTrace` validates the complete relationship:

```text
Result -> Athlete
Result -> Competition
Result -> Event -> Competition
Result -> Source
```

Factual models require at least one source identifier and an explicit
`verification_status`: `VERIFIED`, `UNVERIFIED`, `UNKNOWN`, or `CONFLICT`.
Missing information remains `None` or an explicit `UNKNOWN` enum value; models
do not infer it.

Language fields preserve known original-language metadata for later
multilingual processing. Timestamps and structured values preserve inputs that
later analytics layers may consume, but Layer 1 performs no translation or
historical calculations.
