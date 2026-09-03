# Historical results

Layer 2 accepts already-structured historical swim data. It does not parse
websites, PDFs, spreadsheets, screenshots, or messages, and it contains no
external API or production database integration.

## HistoricalResult

One `HistoricalResult` represents one athlete swim in one competition event on
one date and round. It retains athlete, competition, event, and source UUIDs;
pool length, stroke, distance, heat/lane metadata; raw and normalized time;
optional splits and AQUA points; result, standard, and verification statuses;
notes; and entity timestamps.

The primary `source_id` identifies the canonical claim. `source_ids` links all
compatible or conflicting claims retained for the same swim. The in-memory
repository also retains each normalized claim and its complete `Source` record.

## Time normalization and splits

Source text remains unchanged in `official_time_raw`. Strict helpers normalize
accepted forms such as `34.19`, `1:17.07`, and `2:47.85` into integer
centiseconds. Float seconds are never canonical. Missing or ambiguous notation
is rejected rather than guessed. DNS, DNF, and disqualified records may omit a
time.

Each `Split` preserves its raw text and normalized centiseconds. Split distances
must increase, may not exceed the event distance, and cumulative times must be
chronological. A cumulative finish split must equal the official time. Missing
splits remain valid and are never synthesized.

## Pool, result, and standard states

SCM (25 m), LCM (50 m), and unknown pool lengths are explicit. Pool length is a
deduplication discriminator, so short- and long-course swims remain distinct.
Result status distinguishes official, provisional, reported, disqualified, DNS,
DNF, and unknown claims.

`aqua_points` and `standard_status` are stored only when supplied. Layer 2 does
not calculate AQUA points, attach a duplicated `Standard`, or decide whether a
standard was passed.

## Duplicate identity

Identity matching uses athlete, competition, event, swim date, round, and pool
length. Known, different heat numbers remain separate; an unknown heat can link
only when it selects one unambiguous candidate. Normalized time and structured
claim values are secondary fingerprints.

Exact repeat ingestion is idempotent. Equivalent swims from additional sources
link their provenance without creating another canonical swim. Different rounds,
known heats, and pool lengths are not collapsed.

## Source priority and conflicts

Priority, from highest to lowest, is:

1. Official federation final result
2. Official competition result system or Splash
3. Official competition document
4. Club document
5. Professional or coach message
6. Screenshot or manual entry
7. Other unverified source

A higher-priority verified claim may replace a lower-priority unverified
canonical claim while retaining both source claims. A lower-priority claim never
overwrites a higher-priority verified result. Incompatible claims that cannot be
safely resolved retain their source records and mark the canonical verification
state as `CONFLICT`; verified records are never silently mutated.

## Layer boundary

Layer 2 validates, normalizes, identifies, deduplicates, prioritizes, and stores
structured claims through a persistence-agnostic repository contract. Layer 3
may consume these records for historical analytics, but no PB, trend,
standard-gap, or other performance analytics are calculated here.
