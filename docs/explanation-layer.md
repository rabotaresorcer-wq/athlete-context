# Explanation Layer

Layer 7 turns already structured, verified, and linked Athlete Context records
into concise factual explanations. It uses deterministic Russian and English
templates and makes no LLM or external API calls.

## Input and output

`ExplanationContext` accepts typed records and derived outputs from earlier
layers: a `HistoricalResult`, Layer 3 analytics, a standard gap, Layer 5 link
context, Layer 6 competition context, source provenance, and professional
feedback. Arbitrary free text is not accepted as an authoritative fact.

`ExplanationResult` contains a plain-language summary, structured supporting
facts, a verification note, unresolved items, and detailed source references.
Each supporting fact carries source IDs and an explicit verification status.

## Verification and conflicts

Verified official results may be stated directly. Unverified records are
explicitly labelled, and unknown status remains explicit. Conflicting
verification or incompatible result/link identifiers always produces a
`CONFLICT_NOTICE`; Layer 7 never chooses between conflicting sources.

Source references retain the source ID, type, original source, external
reference or URL, capture time, language, and verification status. Professional
feedback is represented only as unverified context, even when the authenticity
of the feedback record itself is verified. Its content is not converted into a
verified performance fact.

## Numeric and language boundary

Progression and standard explanations format only the already-computed Layer 3
delta or standard-gap values. Layer 7 does not recalculate personal bests,
progression, trends, consistency, standards, or any other performance analytics.

Russian and English output use fixed templates. An unsupported requested language
returns a structured `UNAVAILABLE` result rather than a guessed translation.

## Advice boundary

Explanations are concise, neutral, and descriptive. This layer does not recommend
training changes, judge coaching, select competitions, predict future results,
diagnose medical or athletic problems, scrape sources, integrate with a
federation, persist data, provide a UI, or process real athlete personal data.
