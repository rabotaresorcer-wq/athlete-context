# Input Processing

Layer 4 provides deterministic normalization for content that is already
available as text or JSON-like structured data. Every normalized record retains
its input identifier, source identifier, capture timestamp, and original content.

## Supported input types

- `MESSAGE` for plain message text
- `DOCUMENT_TEXT` for text extracted before it reaches this layer
- `STRUCTURED_DATA` for an existing dictionary/JSON-like payload
- `UNKNOWN` when the caller cannot classify the input safely

An unclassified input containing only structured data is identified as
`STRUCTURED_DATA`. Text is not guessed to be a message or document when the caller
has not supplied that distinction. Structured data passes through without being
interpreted as an athlete, competition, event, or historical result.

## Language detection

The lightweight detector recognizes clear Russian Cyrillic, Turkish-specific
characters or a small fixed set of Turkish markers, and predominantly English
Latin text. Ambiguous, very short, unsupported-script, or mixed-script input is
`UNKNOWN`. These deterministic heuristics are intended for normalization and
tests, not general-purpose language identification.

If the source supplies a known language code, it is preserved rather than
re-detected. Supported codes are `RU`, `TR`, `EN`, and `UNKNOWN`.

## Translation boundary

The default target language is Russian. Translation is performed only through
the `Translator` protocol supplied to the processing service; Layer 4 has no live
translation integration. The included mapping-backed translator is a deterministic
stub. Missing translators or mappings produce `UNAVAILABLE`, and translator
errors produce `FAILED`. Text already in the target language is `NOT_REQUIRED`.

Original text is never overwritten. Translated text is stored separately as a
derivative value and is not a source of truth. A failed or unavailable translation
still returns the intact source text and structured payload.

## Layer boundary

Layer 4 does not read binary PDFs or images, perform OCR, scrape HTML, crawl the
web, call external APIs, link context to domain entities, monitor federations,
manage competition lifecycles, generate explanations, persist to a database, or
process real athlete data. Interpreting normalized input and linking it to
Athlete, Competition, Event, Result, or Standard records belongs to Layer 5.
