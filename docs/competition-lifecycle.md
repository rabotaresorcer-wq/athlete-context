# Competition Lifecycle and Monitoring

Layer 6 represents the lifecycle of a competition that has already been approved
by the athlete's coaching or professional team. Athlete Context does not select,
recommend, rank, or infer competitions. A `PlannedCompetition` can only be created
with an explicit approval marker and reuses the existing `Competition` record.

## Lifecycle

The lifecycle supports `PLANNED`, `MONITORING`, registration information, start
details, completion while awaiting results, official-result availability,
`CLOSED`, `CANCELLED`, and `UNKNOWN`. Optional states may be skipped when an
official update arrives later in the lifecycle.

A verified result publication advances the lifecycle only to
`OFFICIAL_RESULT_AVAILABLE`. Closing additionally requires an existing verified,
official Layer 2 `HistoricalResult` and a consistent Layer 5 `ContextLinkResult`
with matching athlete, competition, event, and source provenance. Layer 6 never
fabricates or ingests a historical result.

## Event-scoped monitoring

`create_monitoring_plan` produces checks only for the supplied approved
competition. The default configurable policy schedules regulation, requirements,
deadline, and start-detail checks before the start date. A result check is placed
after midnight UTC following the competition's end date (or start date when no
end date is known), plus the configured delay.

`get_due_checks` is a pure date comparison over pending checks. No timer, cron
job, queue, worker, browser, or network request is created. If the start date is
unknown, the plan contains no invented check times.

## Federation updates

Update categories cover regulations, eligibility or requirements, registration
deadlines, schedules, start lists, results, cancellations, and other information.
Each monitored update extends the existing federation source-record model and
preserves its competition ID, source ID, language, publication and capture times,
verification status, payload, and exact reference.

Updates are appended rather than overwritten. Repeating an identical update is
idempotent. Unverified information cannot replace a verified check outcome, while
conflicting updates remain in the plan and produce an explicit conflict state.
A verified, non-conflicting cancellation moves the competition to `CANCELLED`.

## Boundaries

Layer 6 consumes records from earlier layers and organizes an approved event's
lifecycle. It does not choose competitions, crawl federation sites, integrate
with TYF, parse PDF/OCR/web content, call external APIs, run background jobs,
analyze performance, generate explanations or coaching, use a database, or
process real athlete data.
