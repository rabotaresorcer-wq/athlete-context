# Historical Performance Analytics

Layer 3 provides deterministic, read-only calculations over stored
`HistoricalResult` records. It does not ingest, correct, or mutate those records.

## Comparable results

Results are compared only when athlete, event, distance, stroke, and pool length
match. Short-course (SCM 25 m) and long-course (LCM 50 m) results therefore remain
separate. Canonical analytics include only timed results that are both `OFFICIAL`
and `VERIFIED`. DNS, DNF, disqualified, untimed unknown, unverified, and conflicting
records are excluded. A caller may explicitly opt into conflict records, but they
are never included by default.

Results are ordered by swim date, then creation timestamp and identifier for a
deterministic series. Previous-result and historical-PB comparisons use only
earlier swim dates; same-day ordering is not guessed.

## Calculations

- **Personal best:** the fastest eligible comparable result.
- **Result progression:** all eligible comparable results in chronological order,
  including competition and source references.
- **Delta to previous:** target time minus the latest earlier comparable time.
  A negative value is faster; a positive value is slower. Percentage change uses
  the earlier time as its denominator.
- **Historical PB delta:** target time minus the fastest comparable result that
  existed before the target swim. Later results cannot affect this calculation.
- **PB progression:** only results that set a strictly faster PB, in chronological
  order.
- **Standard gap:** result time minus one explicitly supplied, verified standard
  for the same event. Layer 3 does not select standards. Missing, incompatible,
  unverified, or unsupported standards produce an unavailable result.
- **Trend:** compares the first and last times in the most recent window (default
  five). At least three results are required. A change within plus or minus 0.5%
  is `STABLE`; lower is `IMPROVING`; higher is `DECLINING`.
- **Consistency:** reports the mean, range, population standard deviation, and
  coefficient of variation for the most recent window (default five). At least
  three results are required.

All time calculations use integer centiseconds and decimal percentage arithmetic.
Outputs are derived Pydantic values and retain identifiers needed to trace results
back to their competition and source.

## Layer boundary

This layer does not implement parsing, translation, monitoring, competition
automation, context linking, external APIs, databases, explanation or coaching,
AQUA calculations, new ingestion, real athlete data, or advanced split analysis.
