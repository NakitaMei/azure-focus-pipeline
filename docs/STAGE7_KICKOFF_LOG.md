# Stage 7 — Kick-off log (UTC everywhere) — FINAL, reconciled 07 Sep 2026

Provenance: [live] = captured at the time · [recon] = reconstructed 07 Sep from
screenshots/portal/manifests/exports · [unrecoverable] = not captured live, stated
as an honest bound. Blank template + reconstruction is itself a chunk-1 finding.

## A. Budget guard
- [x] $20/month budget confirmed active — 31 Aug 2026 ~11:15 UTC [live — working
  notes + banked screenshot]: budget-p1-sandbox-20usd, billing-account scope,
  alerts 50/80/100% actual + 100% forecast, recipient confirmed
- [x] Post-reactivation check the same hour (subscription had been Disabled — F-K1)
- Dedicated OpenAI-RG budget: none; instead enqueued-token quota 2,000,000 of
  50,000,000 on the deployment [recon] — AI-native guardrail

## B. Azure OpenAI
- Resource / location: nakitameiring-6066-resource, RG networkwatcherrg (F-K5
  NetworkWatcherRG read CONFIRMED from export ResourceId); meters bill as
  West US 3 glbl batch. Idle twin: oai-p1-sandbox (rg-p1-sandbox, Sweden Central,
  $0, teardown decision taken at Stage 8: delete — Step 11)
- Deployment: gpt-4.1-nano-1 · gpt-4.1-nano v2025-04-14 · GlobalBatch · created
  31 Aug 13:16 UTC [live — notes]. Plan-vs-actual drift: template said
  gpt-4o-mini/Global Standard; F-K2/F-K3 (deprecation + quota) forced the change
- Batch 1 (batch_128040f3-3a41-41da-a291-b30561680e2f):
  - SUBMITTED 31 Aug 13:28:28 UTC [live — notes; the latency clock start]
  - Processing 13:30 → completed ~13:34–13:36 UTC [notes ~13:34; portal timeline
    13:36] — ~6–8 min against a 24h window
  - Totals [live — CSV, logged 13:40:07Z]: 19,200 in / 1,403,791 out /
    1,422,991 total / est $0.281718
- Batch 2 (batch_c73d52ec-26d1-4874-9004-754d165e0fa8):
  - SUBMITTED 07 Sep 04:49 UTC [live — hand-logged]; completed by 04:58:12Z
    [live — script check]; independently re-summed 05:27Z by sum_batch_usage.py,
    identical totals (cross-validated)
  - Totals: 19,200 in / 1,397,963 out / 1,417,163 total / est $0.280553
  - Same 800-request input, output −5,828 tokens vs batch 1 (~0.4%) —
    generation nondeterminism, measured
  - CSV NOTE: duplicate batch-2 row (05:27:43Z append) DELETED — keep the
    04:58:12Z row; column est_cost_usd_cumulative actually holds per-batch values
    — renamed est_cost_usd_batch in the clean copy (confirmed 13 Sep)
- Clock-discipline corrections [07 Sep]:
  - CSV timestamps are genuine tz-aware UTC (…T13:40:07+00:00). Earlier
    "SAST-mislabelled" read RETRACTED — the viewer rendered UTC as local.
    Finding: display-layer timezone traps (VS Code viewer local-renders;
    portal shows SAST; runbook output prints UTC)
- First appearance in Cost Analysis (UTC): [unrecoverable — daily-check cadence
  in the notes' open items was not executed; confirmed visible 07 Sep ~04:45]
- First appearance in the FOCUS export (UTC): [unrecoverable exactly — present
  in the Aug 1.0r2 run submitted 05 Sep 01:56:33Z; per F-K9 likely an earlier
  1–4 Sep rerun, destroyed by OverwritePreviousReport]
  → Latency stated as bounds: usage 31 Aug 13:30–13:35Z; in export ≤05 Sep
  01:56Z. Forward-measured batch-2 sample running: submission 04:49Z hand-logged;
  Cost Analysis checks today (log UTC + seen/not-seen); pull the 08 Sep 01:56Z
  export run
- Reconciliation VERIFIED 07 Sep: export rows (ChargePeriodStart 2026-08-31)
  Inp 19,200 / $0.000960 · Outp 1,403,791 / $0.280758 · total $0.281718 —
  EXACT match to CSV, counts and cost. Rates $0.05/$0.20 per 1M = the 50%
  batch discount confirmed (F-K4; assumed rates in notes now verified).
  PricingQuantity (1K blocks) + ConsumedQuantity (units) native — the
  Finance/Engineering denominator pair. Rows tagged {"deployment","project"}
  only — platform tags, not the allocation schema → UNTAGGED in team showback
- F-K1 CORROBORATED in data: last billed day Aug 21 → zero rows Aug 22–30 →
  resumption Aug 31. Precision upgrade: the gap manifests as ABSENT DATES,
  not $0 rows (notes expected zero-usage backfill) — S6 handling implication:
  day-present averages silently exclude the outage
- F-K9 VERIFIED: 31 Aug charges landed in the AUGUST file via early-Sep reruns

## C. Automation start/stop schedule
- Account: auto-p1-sandbox, North Europe, deliberately untagged [live]
- Managed identity + Virtual Machine Contributor @ rg-p1-sandbox: 31 Aug
  ~13:50–13:51 UTC [live; F-K8 Classic-role near-miss caught in the dropdown]
- Runbooks published: Stop-SandboxVM 13:57 · Start-SandboxVM 14:02 UTC [live;
  empty-draft portal trap recorded]
- Manual round trip: Stop job 14:05:31, op Succeeded 14:06:18–32 (14s), VM
  deallocated · Start job 14:10:18, Succeeded, VM Running [live]
- Schedules linked ~14:20 UTC: Nightly-Stop daily 18:00 SAST (no expiry) ·
  Weekday-Start Mon–Fri 08:00 SAST from 01/09 [live]
- First scheduled stop observed: 31 Aug 16:00:08 UTC [recon — job history]
- First scheduled start observed: 01 Sep 06:00:09 UTC [recon]
- Through 06 Sep: all jobs Completed; weekend pattern verified (no Start
  05–06 Sep; idempotent weekend Stops); jitter 3–13s; visible in export row
  counts (13–14 weekday vs 10 weekend rows)

## Notes / surprises
- Blank-template finding: everything reconstructable EXCEPT first-seen
  timestamps — unlogged observability is unrecoverable; overwrite mode
  compounds it. Corrected method = batch-2 forward sample.
- Second batch fired 07 Sep, not 01 Sep as the notes' cadence intended —
  6-day slip, honestly recorded; consequence is a two-point daily grain
  (Aug 31 + Sep 7) rather than consecutive days.
- Key rotation (F-K10) now TRIPLY triggered: kick-off chat paste + 07 Sep
  screenshot + 07 Sep chat paste. Regenerated 07 Sep (F-K10 closed); env vars only,
  never in files. publication_check.py covers this class.
- Autoscale screenshot + paragraph: delivered in the Stage 7 analysis (§11) —
  closed 08 Sep.
