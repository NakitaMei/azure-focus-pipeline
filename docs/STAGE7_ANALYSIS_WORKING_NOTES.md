# Stage 7 — Analysis Working Notes

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 7 — Extensions (scheduling · AI cost · latency) · **Status: CLOSED 8 Sep 2026 (see §13)**
**Sessions covered:** Kick-off 31 Aug 2026 (recap; full record in STAGE7_KICKOFF_WORKING_NOTES.md) · AWS groundwork 3 Sep 2026 (P2 material; full record in AWS_SETUP_LOG.md) · Analysis session 7 Sep 2026
**All times UTC unless marked SAST (SAST = UTC+2).**

This is the complete narrative for final review: every step, what it produced,
what it tracks, and why it was done that way. The plain-English summary comes
first; terms are defined where they first bite.

---

## 0. Plain-English summary (the whole stage so far)

Stage 7 turns three real-world exercises into portfolio findings: a VM
start/stop schedule (does automation actually save money?), real AI token
spend flowing through the billing pipeline (can a local audit trail be
reconciled to the invoice-grade export?), and billing latency (how long
until spend becomes visible data — and what happens when you don't watch
the clock properly?).

As of 7 September: every input is verified and every pre-analysis loose end
is closed. The headline results so far, in plain English:

- **The token reconciliation ties perfectly.** The local CSV written by the
  generation script and Azure's own FOCUS export agree on token counts to
  the unit and on cost to six decimal places ($0.281718 for batch 1). This
  is the strongest possible answer to "can Finance trust the export?"
- **The latency finding is honest rather than precise.** The first-appearance
  timestamps were never captured live (the kick-off log stayed blank), and
  the export's overwrite mode destroyed the history that could have answered
  retroactively. The finding states bounds, explains why only bounds exist,
  and repairs the method with a second, forward-measured sample.
- **The credit-expiry incident (F-K1) is visible in the billing data itself:**
  the export goes silent exactly 22–30 August, matching the subscription's
  disabled period — and the gap manifests as *missing dates*, not zero-cost
  rows, which changes how averages must be computed.
- **The AI spend landed on a shadow resource.** All token cost bills to a
  Foundry-created resource in NetworkWatcherRG, outside the governed sandbox
  resource group, carrying platform tags instead of the allocation schema.
  In a one-person sandbox, on the first afternoon of AI work, organic
  shadow-IT appeared — the governance note writes itself.
- **The scheduling automation works and its effect is visible in the data:**
  every job Completed since 31 Aug, weekends off by design, and the export's
  daily row counts drop from 13–14 (weekdays) to 10 (weekends) because the
  sleeping VM emits fewer meters.
- **The 1.2-preview export demonstrates the x_ on-ramp live:** three columns
  that Azure ships as x_ extensions at 1.0r2 (x_InvoiceId, x_PricingCurrency,
  x_SkuMeterName) appear as root FOCUS columns (InvoiceId, PricingCurrency,
  SkuMeter) in the 1.2-preview file — the exact promotion mechanism the
  project's v1.5 framing is built on, observed in our own data.

Remaining: chunks 2–6 (reconciliation write-up, unit economics, scheduling
analysis, autoscale paragraph, governance note), the batch-2 latency sample
completing overnight, and Stage-8 housekeeping (key rotation is now urgent).

---

## 1. Kick-off recap (31 Aug) — what this session inherited

Full detail in STAGE7_KICKOFF_WORKING_NOTES.md. In one paragraph: the
subscription was found Disabled (free credit expired ~21 Aug) and upgraded to
pay-as-you-go at 11:10; both FOCUS exports were rebuilt (1.0r2 into the
original loader path at 11:59; a separated 1.2-preview export at 12:02, which
is only creatable at billing-account scope — F-K7); an Azure OpenAI deployment
was stood up after a deprecation-and-quota gauntlet (F-K2/F-K3) ending on
gpt-4.1-nano Global Batch (F-K4: the only type with quota, at 50% of
interactive price); 800 requests of real token spend were submitted at
13:28:28 (batch 1, completed ~6 minutes later); and the VM start/stop
automation was built, round-trip tested, and armed (Nightly-Stop daily 18:00
SAST; Weekday-Start Mon–Fri 08:00 SAST). Findings F-K1–F-K10 were banked.
Loose ends A1–A6 were left for this session.

**Definition — FOCUS export:** Azure's scheduled job that writes the
subscription's cost-and-usage data, in the FinOps Open Cost and Usage
Specification schema, to Parquet files in our storage account. It is the
pipeline's raw material. Each run writes a manifest.json describing itself.

## 2. Interlude (3 Sep) — AWS groundwork, done first per the handover

Not Stage 7 material, but done inside this working period and recorded here
for completeness: the AWS account was created with guardrails-before-resources
discipline (budget budget-p2-sandbox-10usd before anything billable;
pre-provisioned anomaly monitor verified rather than created — a
platform-posture difference vs Azure), and a native FOCUS 1.2 export now
flows daily to s3://nakita-p2-focus-exports at daily grain, Parquet,
overwrite. The console offered FOCUS 1.0 and 1.2 only — P2's opening
version-drift data point, mirroring Azure's 1.0r2 + 1.2-preview. Nine
findings (F-A1–F-A9) are logged in AWS_SETUP_LOG.md. First S3 delivery check
is pending (passive; no dependency).

## 3. Analysis session, 7 Sep — closing A1–A6 (the pre-chunk work)

The session's first job was to close the six kick-off loose ends. Everything
below was verified against primary sources: the portal, the export files
themselves, the manifests, and the kick-off screenshot bundle (13 images,
15:13–16:24 SAST 31 Aug, reviewed individually).

### A1 — Runbook job history: CLOSED
Every job since kick-off shows Completed. The pattern is the proof of design:
Stop fires 18:00 daily including weekends; Start fires 08:00 weekdays only —
no Start jobs on 5–6 Sep (Sat/Sun), and the weekend Stop jobs complete
harmlessly against an already-stopped VM (idempotent). Scheduler jitter
3–13 seconds. The 31 Aug 16:05/16:10 pair are the manual round-trip tests.
The Automation deprecation banner (agent-based Hybrid Runbook Worker) does
not apply — no hybrid workers in use.
*Plain English: the lights-out schedule has run itself, correctly, every day
since it was armed, and skipped exactly the mornings it was told to skip.*

### A2/A3 — Batch check + second submit: CLOSED
- **Batch 1** (batch_128040f3-3a41-41da-a291-b30561680e2f): Completed, zero
  failures (error file absent). Timeline: created 13:28 → in progress 13:30 →
  finalizing 13:35 → completed 13:36 UTC. Totals (CSV, logged 13:40:07Z):
  19,200 prompt / 1,403,791 completion / 1,422,991 total / est $0.281718.
- **Batch 2** (batch_c73d52ec-26d1-4874-9004-754d165e0fa8): submitted this
  morning after a small environment saga (below). Submission hand-logged
  **04:49 UTC**; completed by 04:58:12 UTC — ~9 minutes against a 24-hour
  window. Totals: 19,200 prompt / 1,397,963 completion / 1,417,163 total /
  est $0.280553.
- **Cross-validation:** batch 2's totals were computed twice by independent
  paths — the generation script's own check (04:58Z) and a purpose-built
  sum_batch_usage.py reading the output file (05:27Z) — identical to the
  token. The duplicate CSV row this created was removed; the CSV now holds
  exactly one row per batch, and the cost column was renamed
  est_cost_usd_batch (it held per-batch values under a _cumulative name).
- **Analysis fact banked:** identical input across batches (19,200 tokens —
  the same 800 requests) with output differing by 5,828 tokens (~0.4%) —
  generation nondeterminism, now *measured* rather than asserted.
- **The environment saga, honestly recorded:** the fresh terminal lacked the
  session-scoped env vars (expected; they are deliberately not in any file);
  one script edit briefly replaced a variable *name* with a placeholder URL
  (reverted); the exports then used AZURE_OPENAI_KEY where the script reads
  AZURE_OPENAI_API_KEY (fixed). Root cause class: env-var name mismatches.
  Mitigation now standard: `grep os.environ <script>` before exporting.
  During the fixes the API key appeared in a screenshot and a chat message —
  see Key rotation under section 6.
*Plain English: both batches of real AI spend are complete, their token
counts are confirmed by two independent methods, and the audit CSV is clean.*

### A4 — First-seen timestamps: CLOSED as honest bounds (full finding in §4)
The kick-off log template was never filled — the daily "when did the cost
first appear" checks did not happen, and the export's overwrite mode deleted
the intermediate runs that could have answered the question after the fact.
Decision, per the standing rule (claims not yet true get removed, not
softened): the latency finding states bounds, names the method failure as a
finding in its own right, and runs a corrected forward-measured sample on
batch 2.

### A5 — Manifest check: CLOSED, with a schema diff as bonus
Four manifests/files pulled and verified (August + September, both versions):
- 1.0r2 declares dataVersion **1.0r2**; files carry **96 columns = 44 FOCUS
  + 52 x_** — matching Stage 1 exactly. Subscription-scoped export resource.
- 1.2-preview declares **1.2-preview**; files carry **105 columns = 53 root
  + 52 x_**. Billing-account-scoped export resource (F-K7 confirmed).
- **The promotion trio:** x_InvoiceId → InvoiceId · x_PricingCurrency →
  PricingCurrency · x_SkuMeterName → SkuMeter. The Stage-1 fallback columns
  became root FOCUS columns one version later — the x_ → business case →
  spec column on-ramp (the SkuMeter/SkuPriceDetails precedent), observed in
  our own pipeline. This is primary evidence for the v1.5 framing in chunk 2.
- Also new at 1.2-preview: CapacityReservationId/Status (absent entirely at
  1.0r2), CommitmentDiscountQuantity/Unit, ServiceSubcategory,
  SkuPriceDetails; new extensions x_AmortizationClass, x_ServiceModel,
  x_SkuPlanName.
- Both trees share manifestVersion 2024-04-01; granularity Daily; overwrite.
- Data-hygiene bonus: x_ResourceGroupName holds both `rg-p1-sandbox` and
  `RG-P1-SANDBOX` — case-inconsistent strings for one group, the same
  grouping trap class as Stage 4's tag-key-order finding.
- Sanitisation: the 1.2-preview manifest embeds the billing-account ID.
*Plain English: the exports declare exactly the versions they should, the
newer preview literally shows extension columns being adopted into the
standard, and we caught a case-inconsistency that would split one resource
group into two in a naive report.*

### A6 — Resource group / region: CLOSED, from the billing data itself
The export rows' ResourceId settles it: the billed resource
nakitameiring-6066-resource sits in **resourcegroups/networkwatcherrg**
(provider microsoft.cognitiveservices), meters billing as West US 3 global
batch. F-K5's NetworkWatcherRG suspicion: confirmed. The intended resource
oai-p1-sandbox (rg-p1-sandbox, Sweden Central) exists, idle, $0 — teardown
decision deferred to Stage 8. The billed rows carry tags
{"deployment":"gpt-4.1-nano-1","project":"nakitameiring-6066"} — *platform-
emitted* tags, not the allocation schema (no team, no cost-centre): in a
team showback these rows fall into UNTAGGED despite Tags being populated.
"Tagged, but not governably tagged."
*Plain English: the AI money flowed through a resource the quick-create
wizard made in the wrong place with its own labels — a perfect miniature of
enterprise shadow-IT, caught by the allocation queries exactly as they're
designed to.*

### Corroborations that fell out of the file work
- **F-K1 confirmed in data:** last billed day Aug 21 → zero rows Aug 22–30 →
  resumption Aug 31. Matches the disabled-subscription window. Precision
  upgrade: the gap is **absent dates, not $0 rows** (the notes expected
  zero-usage backfill). Implication for S6 handling: any average over
  "days present" silently excludes the outage. Feeds the readiness memo.
- **F-K9 verified:** the 31 Aug charges landed in the *August* export files
  via the early-September MTD reruns (August tree rerun as late as 5 Sep) —
  exactly as predicted. Late-arriving charges are why prior-month files keep
  refreshing after month end.
- **F-K8 enriched:** the screenshot pair shows "Classic Virtual Machine
  Contributor" selected at 15:50 SAST and corrected to "Virtual Machine
  Contributor" by 15:51 — the legacy-role trap caught in under a minute,
  with the managed identity scoped to rg-p1-sandbox only (least privilege).
- **New from the deploy blade:** the enqueued-token limit was set to
  2,000,000 of 50,000,000 at deployment — a quota-side cost control on the
  AI resource itself (the AI-native analogue of the $20 budget), and the
  blade's own wording ("50% less cost than Global Standard") is the citable
  counterfactual for chunk 3.
- **Plan-vs-actual drift recorded:** the log template was pre-filled with
  gpt-4o-mini / Global Standard; execution delivered gpt-4.1-nano / Global
  Batch, forced by F-K2 (deprecation) and F-K3 (quota).

## 4. Chunk 1 — The billing-latency finding (drafted 7 Sep)

**Plain-English summary.** We measured how long Azure takes to turn token
spend into visible billing data — and documented what can and cannot be
known when observation isn't logged in real time. Spend generated on 31
August was demonstrably in the FOCUS export by 5 September, but the exact
first-appearance moment is unrecoverable: the daily checks weren't
performed, and the export's overwrite mode destroyed the run history that
would have answered retroactively. Rather than soften that into a fake
number, the finding states bounds, explains why only bounds exist, and
repairs the method with a second, forward-measured sample submitted this
morning. Three timezone traps found along the way justify the project's
UTC-everywhere rule.

### 4.1 The three clocks
| Clock | Source | Renders as |
|---|---|---|
| Usage | Batch job lifecycle (API epoch) | UTC |
| Cost Management | Cost Analysis / FOCUS export | ChargePeriodStart at civil-date grain (S7) |
| Observation | Portal blades, editor viewers | **Local time, unlabelled** |

Evidence for the third row: one screenshot shows the manual Stop job as
*created 16:05* (portal, SAST) beside runbook output *StartTime 2:06:18 PM*
(UTC); and the CSV's correct `2026-08-31T13:40:07+00:00` displayed as
"15:40" in the VS Code viewer. Neither surface labels its timezone.
**Finding: the display layer is itself a source of timestamp error —
measure from stored values, never from rendered ones.** (A first read of
the viewer produced a wrong "CSV logged local time" conclusion, retracted
same-day when the raw file was inspected: the CSV was correct, tz-aware
UTC throughout. The retraction is kept on the record as the exhibit.)

### 4.2 Sample 1 (batch 1, 31 Aug) — bounded, honestly
- Clock start: batch submitted **31 Aug 13:28:28 UTC** (logged live).
  Processing 13:30–13:35; completed ≤13:36 UTC.
- Charge attribution: both AI rows carry **ChargePeriodStart 2026-08-31** —
  the same civil date as usage. At the grain S7 mandates, attribution
  latency is **zero days**.
- Export availability: rows present in the August 1.0r2 run submitted
  **05 Sep 01:56:33 UTC** → availability latency **≤ ~4.5 days**. Almost
  certainly shorter (F-K9: the 1–4 Sep MTD reruns likely carried the rows
  earlier), but OverwritePreviousReport deleted those runs —
  **overwrite mode trades storage cost for latency observability**.
- Cost Analysis availability: **unknown**; confirmed visible only 07 Sep
  ~04:45 UTC. The daily-check protocol existed in the kick-off open items
  and was not executed — *unlogged observability is unrecoverable
  observability.*

### 4.3 Sample 2 (batch 2, 07 Sep) — the corrected method, running
Submission hand-logged **04:49 UTC**; completed by 04:58:12 UTC.
**MEASURED (8 Sep):** batch 2's rows (ChargePeriodStart 2026-09-07 — zero-day
attribution at S7 grain, reproduced) are present in the 1.2-preview run
submitted **07 Sep 16:08:02Z** — the FIRST cadence tick after usage, wall-clock
**≤ 11h10m after batch completion** — and in the 1.0r2 run of **08 Sep
01:56:00Z**, also that export's first tick after usage. Measured result:
**both exports delivered on the first available tick; latency = 1 cadence
tick; tightest wall-clock bound ≤ 11.2h** (true value somewhere in 0–11.2h —
no intraday Cost Analysis checks were logged, honestly noted, so the export
side is the measured surface). Contrast with sample 1's ≤ ~4.5-day
overwrite-blinded bound: the forward-measured method turned an unknowable
into a same-day number. Kept observation: because the export runs
~01:56 UTC daily, export latency in this pipeline is *quantised* — the
honest unit of answer for a daily export is "N cadence ticks," not hours. Protocol addendum (7 Sep): the two exports run at DIFFERENT
times of day — 1.0r2 ~01:56 UTC, 1.2-preview ~16:08 UTC (manifests) — so the
pipeline samples twice daily. Next checkpoints for batch 2 (usage 04:49–04:58
UTC): the 1.2-preview run TONIGHT ~16:08 UTC (≈18:08 SAST; if present, export
latency ≤ ~11.3h) and the 1.0r2 run 08 Sep 01:56 UTC.

### 4.4 A second latency surface, found by accident
The disabled-subscription period shows billing data has *presence* latency
as well as *value* latency: Aug 22–30 are **absent dates**, not zero-cost
days. Any consumer averaging over days-present silently excludes outages.
Feeds S6 zero-cost-day handling and the readiness memo.

### 4.5 Case-study paragraph shape
Three clocks · the bounded first sample with the overwrite lesson · the
quantised second sample with real numbers (filled 8 Sep) · the methods
sentence: *claims not yet true get removed, not softened; where a number
could not be recovered, a bound is stated and the method that would have
recovered it is now in place.*

## 5. Evidence locker for the remaining chunks (verified, ready to use)

**Chunk 2 — token reconciliation: WRITTEN UP IN §8 (7 Sep).** Original locker entry kept below for the audit trail:
CSV ↔ export tie is EXACT: Inp 19,200 units / $0.000960 · Outp 1,403,791
units / $0.280758 · total $0.281718 vs CSV $0.281718. PricingQuantity in 1K
blocks beside ConsumedQuantity in raw units — the two denominators native in
the real rows. Framing evidence: the promotion trio from §A5 (the x_ on-ramp
observed live); the real rows' virtual-currency-adjacent structure vs the
synthetic Layer-B PricingCurrency pair; provenance labels: these two rows
are REAL data (x_Synthetic absent/false), never sandbox-synthetic.

**Chunk 3 — cost per 1K tokens, two views + pricing axis:**
Verified rates $0.05 in / $0.20 out per 1M (÷ PricingQuantity) — the
assumed rates from kick-off now confirmed against billed cost. Batch = 50%
of Global Standard ($0.10/$0.40), citable from the deploy blade's own
wording. Batch-vs-interactive: same tokens, two prices, different buying
mode (file-in/file-out, 24h window that actually ran 6–9 minutes).
Nondeterminism: identical input, output −0.4% between runs — unit costs on
the output side vary run-to-run even at fixed prices.

**Chunk 4 — scheduling analysis:**
Job history complete and clean; weekend design verified; the effect visible
in export row counts (13–14 weekday vs 10 weekend). August 1–21 constant
~$0.3275/day = the 24/7 baseline; F-K6 framing binds: capability + elapsed
days measured, $0.00 monetary saving inside the free window, 70.2% of
compute-hours off (≈70% of compute cost at PAYG rates) as the counterfactual, disk (+IP) floor a schedule cannot
touch, stop = deallocate.

**Chunk 5 — autoscale:** screenshot + paragraph delivered — §11 (closed 8 Sep).

**Chunk 6 — governance note (300 words) inputs:** F-K2 lifecycle ladder ·
F-K3 quota-decides-model · F-K4 batch lever + enqueued-token quota guardrail
· F-K5 shadow resource in networkwatcherrg with platform-only tags (now
data-confirmed) · F-K10 key exposure and rotation discipline.

## 6. Open items (as of 7 Sep, morning)

- [x] Batch-2 latency sample: 08 Sep 01:56Z export run pulled; §4.3 filled
      (closed 8 Sep).
- [x] **Rotate the OpenAI key — now urgent.** (Closed — see the rotation
      line below.) F-K10's trigger count is
      three (kick-off chat paste; 07 Sep terminal screenshot; 07 Sep chat
      paste). Regenerate Key 1, re-export env var. Before any publication
      step, and ideally today.
- [x] AWS S3 first-delivery peek — carried to Project 2; out of P1 scope
      (Stage 8 decision, 13 Sep).
- [x] Delete local duplicate CSV row — clean copy confirmed 13 Sep: two
      rows, one per batch, column `est_cost_usd_batch`.
- [x] Chunk 2 drafted (§8, 7 Sep). Follow-up inside it: reconcile batch 2
      against the 08 Sep 01:56Z export run (CSV side already tabled).
- [x] Chunk 3 drafted (§9, 7 Sep).
- [x] Chunk 4 drafted (§10, 7 Sep) — C4 queries in stage7_queries.sql.
- [x] Chunk 5 drafted (§11, 7 Sep) — screenshots banked: gated / registered /
      configured (chunk5-autoscale-blade_*.png); nothing deployed.
- [x] Chunk 6 drafted (§12, 7 Sep) — governance note ready for review.
- [x] Latency checkpoints pulled 8 Sep; §4.3 and §8.4 filled with measured
      numbers — first-tick delivery in both exports, second exact tie.
- [x] Key rotated 7 Sep (Regenerate Key 1; F-K10 CLOSED — governance note's
      "rotation" line is now a record, not a promise).
- [x] Sanitisation running list — carried into STAGE8_WORKING_NOTES Step 9
      (the C3 sweep): subscription ID · billing-account
      ID (1.2-preview manifest) · AWS account ID · terminal screenshots with
      exported secrets · monitor ARN.

## 7. Standing rules — applied this session
Claims not yet true get removed, not softened (the latency bounds; the
retraction in §4.1). Real token spend is REAL data — provenance labelled
accordingly. S1–S7 bind all SQL; S7 especially (civil-date grain — §4.2's
zero-day attribution). One chunk at a time, screenshots verified, errors
owned: the Python 3.9 type-hint bug, the env-var mismatch, and the wrong
first read of the CSV clock were all ours, and all fixed on the record.

## 8. Chunk 2 — Token reconciliation (drafted 7 Sep)

**Plain-English summary.** The question a CFO asks of any new spend channel:
does the provider's billing data tie to our own records? Here the "subledger"
is the local CSV written by the generation script at batch completion, and
the "ledger" is Azure's FOCUS export — invoice-grade billing rows. For batch
1 they tie EXACTLY: token counts to the unit, cost to six decimal places,
with zero unexplained variance. This is the control-account discipline run
for six years on Xero, applied to AI tokens — and the row structure that
makes it possible is the early form of what FOCUS 1.5 will standardise, so
the whole chunk doubles as the v1.5 on-ramp exhibit.

### 8.1 Method (and its audit against the §5.1 standing rules)

Reconciliation grain: per meter, per civil day, per batch. Local side:
token_generation_log.csv (one row per batch; prompt/completion split; cost
estimated at verified batch rates). Billed side: the August 1.0r2 export
(dataVersion confirmed 1.0r2, 96 cols), AI rows selected by ResourceId.

```sql
-- stage7_queries.sql §C2 · DuckDB · binds S1–S7 and §5.1
WITH export_ai AS (
  SELECT CAST(ChargePeriodStart AS DATE) AS charge_date,
         x_SkuMeterName                  AS meter,      -- provider drill-down only
         SUM(ConsumedQuantity)           AS tokens,
         SUM(PricingQuantity)            AS pricing_qty_1k,
         SUM(BilledCost)                 AS billed_usd
  FROM read_parquet('data/raw/focus-export/exports/focus-export-p1-sandbox-focus-cost/20260801-20260831/*/part_*.snappy.parquet')
  WHERE ResourceId ILIKE '%/networkwatcherrg/%nakitameiring-6066-resource'
    AND ChargeCategory = 'Usage'                         -- one side only
    AND BillingCurrency = 'USD'                          -- currency filtered
    AND ChargePeriodStart >= DATE '2026-08-01'
    AND ChargePeriodStart <  DATE '2026-09-01'           -- Start-only, half-open
  GROUP BY 1, 2
)
SELECT * FROM export_ai ORDER BY charge_date, meter;
```

Rule audit, line by line: period filter on Start only, half-open ✓ ·
BillingCurrency filtered before aggregation ✓ · ChargeCategory pinned to one
side (Usage) before summing ✓ · BilledCost used because the question is
invoice reconciliation (labelled; EffectiveCost would answer a different
question and here equals it anyway — no commitments on these rows) ✓ ·
x_SkuMeterName used as provider-specific drill-down, not as a portable
grouping key ✓ · no reasoning from sign ✓.

### 8.2 The reconciliation — batch 1 (charge date 2026-08-31)

| Side | Meter | Tokens | USD |
|---|---|---|---|
| Export | gpt 4.1 nano Batch Inp glbl Tokens | 19,200 | 0.000960 |
| Export | gpt 4.1 nano Batch Outp glbl Tokens | 1,403,791 | 0.280758 |
| **Export total** | | **1,422,991** | **0.281718** |
| **CSV (local)** | prompt + completion | **1,422,991** | **0.281718** |
| **Variance** | | **0** | **0.000000** |

Exact tie on counts AND cost. The implied unit rates fall straight out:
0.000960/19.2 = $0.05 per 1M input; 0.280758/1,403.791 = $0.20 per 1M
output — confirming the kick-off's *assumed* batch rates against billed
reality (F-K4 closed as verified), and confirming the 50%-of-interactive
batch discount ($0.10/$0.40 Global Standard) the deploy blade advertised.

Also verified on the same rows: Billed = Effective = List (the batch
discount lives in the unit rate, not a discount mechanism — no elimination
filter needed, but the rule was applied anyway); InvoiceId null in the
1.2-preview twin rows = not yet invoiced, null-as-information, conformant.

### 8.3 The structure that made it easy — and the v1.5 on-ramp

What the real rows already carry, at 1.0r2:
- **Two denominators, natively.** ConsumedQuantity holds raw tokens (Units);
  PricingQuantity holds the same quantity in 1K blocks (x_PricingUnit-
  Description "1K"). Finance's rate denominator and Engineering's
  consumption measure coexist on every row — chunk 3 runs on this pair.
- **Token semantics in meter names, not columns.** "…Batch Inp glbl Tokens"
  lives in x_SkuMeterName (1.0r2) / SkuMeter (1.2-preview). The *quantity*
  is standard; the *meaning* ("these are tokens", "input vs output",
  "batch pricing") rides in provider strings.

That second point is exactly the gap FOCUS 1.5's native AI token tracking
addresses, and this project's Layer-B design anticipates it: synthetic
token rows carry PricingCurrency = "tokens" with the paired
PricingCurrencyEffectiveCost, plus x_ token columns — modelling semantics
as *data* rather than string-parsing. The mechanism isn't speculative;
it's the spec's own documented on-ramp, and we now hold primary evidence
it works: **three of Stage 1's x_ fallback columns (x_InvoiceId,
x_PricingCurrency, x_SkuMeterName) appear as root columns (InvoiceId,
PricingCurrency, SkuMeter) in our own 1.2-preview export** — the same
x_ → business case → spec column path that produced SkuMeter and
SkuPriceDetails at 1.1. Building token costs as x_ columns today is
therefore not a workaround; it is participation in the spec's evolution
mechanism, with the promotion already observable one version out.

Provenance labels, per the standing rule: the two August rows (and
tomorrow's September rows) are REAL data — x_Synthetic absent — and every
claim in this chunk rests on them; the PricingCurrency-pair modelling
lives in the synthetic layer and is labelled as such wherever shown.

### 8.4 Batch 2 — CSV side tabled, export side pending (deliberately)

CSV side (final): 19,200 prompt / 1,397,963 completion / 1,417,163 total /
est $0.280553 at the now-verified rates. Expected billed side: two Usage
rows, ChargePeriodStart 2026-09-07, same meters, in the September 1.0r2
file after the 08 Sep 01:56Z run. **RECONCILED (8 Sep):** the September files (both versions) carry the
two rows at ChargePeriodStart 2026-09-07 — Inp 19,200 / $0.000960 · Outp
1,397,963 / $0.279593 · total 1,417,163 tokens / **$0.280553 = CSV estimate
to six decimals. Second batch, second EXACT tie** — reproducibility proven,
zero variance both times, and the verified rates held constant across runs.
Two facts the pair will demonstrate: reproducibility of the exact-tie
result, and measured nondeterminism — identical 800-request input, output
−5,828 tokens (−0.4%), est cost −$0.001165 — same job, same prices,
different bill. Unit-economics implication handed to chunk 3: output-side
cost per run varies even at fixed rates, so per-1K-token rates are stable
where per-job costs are not.

### 8.5 Case-study paragraph shape

Subledger-to-ledger tie-out for AI spend: local audit CSV vs FOCUS export,
exact on counts and cost · rates confirmed from billed data, batch = 50% ·
the two-denominator row structure · semantics-in-strings today, the
Layer-B PricingCurrency pair as the 1.5 shape, the promotion trio as live
proof of the on-ramp · reconciliation as the transferable CFO discipline.

## 9. Chunk 3 — Cost per 1K tokens: Finance view, Engineering view, and the pricing axis (drafted 7 Sep)

**Plain-English summary.** "What does a token cost?" has two honest answers
depending on who is asking. Finance asks for the RATE: billed cost divided
by the quantity the provider priced (PricingQuantity — here, 1K-token
blocks). Engineering asks for EFFICIENCY: cost divided by what was actually
consumed or produced (ConsumedQuantity, requests, essays). On this real
data the two coincide per-1K — Azure priced exactly consumed/1000, no block
rounding at this scale — and that coincidence is itself the finding: the
views only diverge where PricingQuantity ≠ ConsumedQuantity (block pricing,
minimums), which is precisely the phenomenon the synthetic Layer-B
block-pricing fixture engineers (1,000-unit blocks, 501 consumed). Real
rows show the clean case; synthetic rows show the divergent case; together
they teach the denominator discipline. Second axis: the same tokens carry
two possible prices — batch vs interactive — and our batch ran at exactly
50%, with the counterfactual stated honestly (it's a rate comparison, not
an achievable alternative: interactive quota didn't exist — F-K3).

### 9.1 Finance view — rate per 1K on the PricingQuantity denominator

| Measure | Batch 1 (31 Aug) | Batch 2 (7 Sep, CSV est) |
|---|---|---|
| Input $/1K | 0.000960 / 19.2 = **$0.00005** | $0.00005 |
| Output $/1K | 0.280758 / 1,403.791 = **$0.00020** | $0.00020 |
| Blended $/1K | 0.281718 / 1,422.991 = **$0.000198** | 0.280553 / 1,417.163 = **$0.000198** |

Blended sits a hair under the output rate because the mix is 98.65% output
tokens — the general lesson: **a blended token rate is a mix statement,
not a price**; quote input and output rates separately, blended only with
the mix disclosed.

### 9.2 Engineering view — consumption efficiency

Same rows, work-based denominators:
- Cost per request: 0.281718 / 800 = **$0.000352** (batch 1);
  0.280553 / 800 = **$0.000351** (batch 2).
- Cost per 1K consumed tokens: identical to §9.1 here, BECAUSE
  PricingQuantity × 1000 = ConsumedQuantity exactly on every row (verified:
  19.2→19,200; 1,403.791→1,403,791). Divergence between the views is a
  *pricing-structure* phenomenon, demonstrated in the synthetic layer
  (labelled as such), absent from these real rows.
- Nondeterminism (from §8.4) lands here: identical input, output −0.4% →
  per-1K rates rock-stable across runs; per-JOB cost varies. Unit rates
  are contracts; job costs are distributions. Budget AI work accordingly.

### 9.3 The pricing axis — batch vs interactive

Counterfactual, stated per the standing rule: *the same token volumes at
Global Standard (interactive) rates $0.10/$0.40 per 1M* —
batch 1: 19,200×0.10/1M + 1,403,791×0.40/1M = 0.001920 + 0.561516 =
**$0.563436**, vs $0.281718 billed = **saving $0.281718, exactly 50.0%**,
matching the deploy blade's advertised discount and the verified rate pair.
Honesty caveats attached wherever this appears: (1) interactive was not an
achievable alternative on this subscription — Global Standard quota was
zero (F-K3) — so this is a rate comparison, not a foregone option; (2) the
"24-hour turnaround" batch trade-off cost us 6–9 minutes in practice, both
runs; (3) batch is a different buying mode (file-in/file-out), not merely a
discount (F-K4).

### 9.4 Where the chart lands

The unit-economics chart (deliverable) goes in the Looker view at assembly:
input/output/blended $ per 1K on the PricingQuantity denominator, the
consumption-efficiency variant explicitly labelled "Engineering view", and
the batch-vs-interactive rate pair as the comparison series. With two
batches the honest chart is a table; the chart earns its place once the
daily grain accumulates.

### 9.5 Case-study paragraph shape

Two denominators, two questions · real rows coincide (and why), synthetic
rows diverge (and why that's engineered) · blended-rate-is-a-mix warning ·
rates stable / job costs vary (measured nondeterminism) · 50% batch saving
with all three honesty caveats attached.

## 10. Chunk 4 — Scheduling analysis: capability proven, saving $0.00, and why that's the finding (drafted 7 Sep)

**Plain-English summary.** The start/stop automation works perfectly and has
saved no money at all — and demonstrating BOTH halves of that sentence, with
the data to prove each, is the deliverable. Every billed dollar on this VM,
in both the 24/7 baseline period and the scheduled period, comes from two
meters a schedule cannot touch: the managed disk and the reserved IP — the
"floor". The compute meter the schedule *does* control currently bills $0.00
(the free account's 12-month allowance of 750 B-series hours/month absorbs
it — a separate mechanism from the $200 credit, which is why it survived the
F-K1 expiry). So the honest statement is three-part: capability measured and
proven; monetary saving measured at exactly $0.00; counterfactual value real
but conditional on the free allowance ending. This is F-K6's framing,
confirmed by the export to the cent.

### 10.1 The measured record

| Period | Regime | Billed/day | Composition |
|---|---|---|---|
| Aug 1–21 (21 days) | 24/7, credit-funded | **$0.3275** | Disk $0.2075 + IP $0.1200; compute $0.00 |
| Sep 1–6 (6 days) | Scheduled, PAYG | **$0.3344** (Sep 6 read $0.2837 on the 7 Sep pull; settled to $0.3344 on the 8 Sep pull) | Disk $0.2085 + IP $0.1175; compute $0.00 |

- **The decisive pair: Fri 4 Sep $0.3344 vs Sat 5 Sep $0.3344.** The VM was
  deallocated the entire Saturday; the bill is identical to the cent —
  deallocation stops compute billing, but the disk and reserved IP bill in
  every state. The floor is 100% of current cost.
- **Capability, separately proven (§3/A1):** every scheduled job Completed;
  weekend design verified; deallocation confirmed (kick-off round-trip:
  PowerState deallocated). And visible in the *export's shape*: weekend days
  emit 10 rows vs 13–14 on weekdays — fewer meters from a sleeping VM.
  **Row-count signature ≠ cost signature** — activity changed, money didn't.
- Baseline vs scheduled daily ($0.3275 vs $0.3344) differ by rate noise, not
  schedule effect; Sep 6's dip on the 7 Sep pull was MTD last-day provisionality (F-K9 family)
  and settled to $0.3344 on the 8 Sep pull,
  flagged so no one reads a saving into it.

### 10.2 Why $0.00 — the meter anatomy

ServiceName "Virtual Machines" here is carrying the DISK meter (Premium SSD
Managed Disks) — an allocation subtlety worth a sentence on its own: the
service label reads compute, the money is storage. The compute meter (B-series)
appears only as $0.00 rows: the free account's 12-month 750 B-series-hours/
month allowance covers a 24/7 single VM entirely (744 max hours/month), and
it is independent of the expired $200 credit. Consequence: the schedule's
target meter costs nothing this year; the floor meters it cannot touch cost
everything. F-K6's "$0.00 monetary saving in the free window" — data-confirmed.

### 10.3 The counterfactual, stated honestly

Hours arithmetic from the schedule (Stop daily 18:00 SAST, Start Mon–Fri
08:00 SAST): on 50 of 168 weekly hours → **70.2% of compute-hours
eliminated**. Monetary value of those hours today: $0.00 (free allowance).
At PAYG B-series rates the eliminated hours are worth ≈70% of the VM's
would-be compute spend (hours off ≈ cost off at pay-as-you-go; the ~65%
quoted earlier from F-K6 had no derivation behind it and is withdrawn) — a
real, conditional saving that switches on when the allowance ends (~Jul
2027) or the VM grows beyond B-series free eligibility. The floor is
unaffected in every scenario: **scheduling is a compute lever only.**

### 10.4 What actually cuts today's bill (optimize hooks, P5-adjacent)

1. The floor is **Premium** SSD at ~$0.21/day — right-sizing to Standard SSD
   is the only lever that reduces the current bill; a schedule never will.
2. The reserved IP (~$0.12/day) bills while the VM sleeps; releasing it
   would cut the floor but break the static-address convenience — a
   documented trade, not a recommendation.
3. Ranked honestly: disk tier change > IP decision > scheduling, for THIS
   workload, TODAY — and the ranking inverts the day compute starts billing.
   Cost levers must be ranked against the meters that actually bill, not
   the meters that feel expensive.

### 10.5 Case-study paragraph shape

Automation proven end-to-end · saving measured at exactly $0.00 with the
Fri/Sat identical-bill exhibit · floor anatomy (disk+IP; service-label
subtlety) · free-allowance mechanics and why F-K1 didn't kill it · 70.2%
of compute-hours as the conditional counterfactual (≈70% of compute cost
at PAYG, hours-proportional) · the optimize ranking · the transferable lesson: measure levers
against billing meters, and report $0.00 as $0.00.


### 10.6 Stage 8 addendum (13 Sep) — what the re-run on the 8 Sep file added

Re-running C4a/C4b/C4c on the overwritten September file (VM-only view,
1–6 Sep, AI resource excluded) held every figure above and added two facts:
the compute meter is not merely $0.00 on deallocated days, it is **absent** —
`Basv2 Series VM` emits 21 rows across 21 August days but only 4 across the 6
scheduled September days (the two weekend days carry no compute row at all);
and the Automation account's own meter (`Process Automation`) bills $0.0000,
so the schedule's running cost is nil. Days-in-data are now counted from the
data (21 and 6) rather than hard-coded, per the F-K1 lesson that missing days
are not zero days.

## 11. Chunk 5 — Autoscale: gated, configured, deliberately not deployed (drafted 7 Sep)

**Plain-English summary.** Scheduling (chunk 4) and autoscaling are the two
supply-management levers: one moves capacity by the calendar, the other by
demand. The deliverable here is a capability demonstration — walk the scale-set
create wizard to the autoscale configuration, capture it, and create nothing —
and the walk itself produced a finding before the blade even opened: autoscale
was NOT AVAILABLE on this subscription until the Microsoft.Insights resource
provider was registered. Fresh subscriptions get capabilities as opt-ins, not
defaults — the same lesson as model quota (F-K3), now on the infrastructure side.

### 11.1 The exhibit arc (three screenshots)
1. **Gated:** VMSS create wizard, Scaling mode "Autoscaling" greyed out —
   "Subscription needs Microsoft.Insights registration to use autoscaling."
2. **Registered:** Subscriptions → Resource providers → microsoft.insights →
   Registered (free; a capability flag, not a resource).
3. **Configured (chunk5-autoscale-blade_4):** Scaling configuration panel —
   Default condition, mode Autoscale, **Instance Count (2, 20, 2)** =
   min 2 / max 20 / default 2, **CPU thresholds (80%, 20%)** = scale out
   above 80%, in below 20%, no schedule; predictive autoscaling off;
   scale-in policy "Balance across zones then delete VM with highest
   instance ID"; force delete off. Cancelled without Review + create.

### 11.2 Reading the panel with cost eyes
- **Instance count is the cost multiplier.** Min × per-instance footprint is
  the autoscale FLOOR — the demand-side analogue of §10's disk+IP floor; max ×
  footprint is the EXPOSURE CEILING. This default condition delegates a 10×
  cost range (2→20 instances) to a CPU metric.
- **The default is availability-biased, not cost-biased:** min 2 (not 1),
  across Zones 1–3 — out of the box, the floor is DOUBLED for resilience. A
  cost-aware sandbox config would set min 1; production would justify min 2
  in writing. Defaults encode priorities; read them.
- **Every added instance brings its own disk** — the §10 floor multiplies per
  instance. Autoscale, like scheduling, is a compute lever whose savings story
  must be netted against per-instance fixed meters.
- **FinOps controls are embedded in the create flow itself:** Flexible
  orchestration with five candidate sizes and **Allocation strategy = Lowest
  price** (Azure picks the cheapest available size per instance) — plus the
  Spot tab one click away. Rate optimisation surfaces before deployment, not
  only after.
- Scale-in policy and predictive autoscaling are the operational refinements:
  WHICH instance dies (zone balance vs newest) and WHETHER capacity moves on
  forecast rather than observation.

### 11.3 The case-study paragraph (deliverable text)
> Autoscaling is the demand-driven sibling of the calendar-driven scheduling
> measured in this project — and on a fresh subscription it is not even
> available until the Microsoft.Insights provider is registered, a reminder
> that cloud capabilities are opt-ins with governance implications. The
> scale-set wizard's default autoscale condition (min 2, max 20, default 2
> instances; scale out at 80% CPU, in at 20%) delegates a tenfold cost range
> to a metric, with the minimum count acting as a demand-side cost floor and
> every added instance multiplying the fixed per-instance meters (disk, IP)
> that this project showed dominate small workloads. The wizard embeds rate
> optimisation directly in the create flow — five candidate sizes under a
> lowest-price allocation strategy, with Spot capacity a tab away. The
> configuration was captured and deliberately NOT deployed: a scale set's
> minimum footprint would multiply exactly the floor costs the scheduling
> analysis proved dominant, and declining to create it is the same budget
> discipline the project has applied since its first guardrail.

## 12. Chunk 6 — AI cost governance note (deliverable 6, ~300 words, drafted 7 Sep)

Inputs: F-K2 (deprecation ladder) · F-K3 (quota decides the model) · F-K4
(batch lever + enqueued-token quota) · F-K5 (shadow resource — now
data-confirmed) · F-K10 (key exposure ×3). Deliverable text:

> **Governing AI spend: what one afternoon of real token cost taught.**
> AI cost governance starts before the first token. Model choice was not
> ours to optimise: the catalogue's deprecation ladder (F-K2) and a
> zero-quota default on every interactive deployment type (F-K3) meant the
> model that could be deployed was the model quota allowed — gpt-4.1-nano on
> Global Batch. Governance implication: quota is not an obstacle to AI
> adoption; it is the first cost control, and requesting it should be a
> deliberate, owned decision, not a ticket filed in frustration.
> Buying mode is the second control. Batch processing halved the unit rate
> (verified in billing at $0.05/$0.20 per million tokens against
> $0.10/$0.40 interactive) for a 24-hour turnaround that in practice ran
> under ten minutes, twice. The enqueued-token limit — set to 2 million of
> an allowed 50 million at deployment — is the AI-native budget: a quota-side
> cap where currency budgets cannot yet see.
> Placement is the third. The Foundry portal's quick-create put the billing
> resource in NetworkWatcherRG — outside the governed resource group,
> carrying platform tags instead of the allocation schema. The spend was
> real, reconciled to the cent, and invisible to team showback: organic
> shadow AI on day one, in a one-person sandbox. Allocation queries caught
> it; policy (allowed resource groups, required tags) would have prevented it.
> Credentials are the fourth. The API key was exposed three times in one
> working week — chat paste, screenshot, chat paste again — despite a
> names-in-code, values-in-environment design. Rotation is scheduled,
> exposure is logged, and the publication checker screens for the class.
> None of this required scale to surface. Every control that matters at a
> million dollars a month — quota, buying mode, placement, tagging,
> credentials — was already load-bearing at 28 cents.

Word count ~300; tone CFO-to-engineering; every claim traceable to a banked
finding or a billed row.


## 13. Stage 7 — CLOSED (8 Sep 2026)

All six deliverables complete and evidence-backed:
1. Billing-latency finding — bounded historical sample + forward-measured
   sample (first-tick delivery, ≤11.2h; zero-day charge attribution twice).
2. Token reconciliation — two batches, two EXACT ties (counts to the unit,
   cost to six decimals); v1.5 on-ramp framed on the observed promotion trio.
3. Unit economics — Finance/Engineering views (coincide, and why), blended-
   rate warning, 50.0% batch saving with three honesty caveats.
4. Scheduling — capability proven, saving measured at $0.00, floor anatomy,
   conditional counterfactual (70.2% of compute-hours; ≈70% of compute cost at PAYG).
5. Autoscale — gated→registered→configured exhibit arc + deliverable paragraph;
   nothing deployed.
6. Governance note (~300 words) — quota, buying mode, placement, credentials;
   all claims traceable; F-K10 closed by rotation before publication.

Carried to Stage 8: sanitisation running list (§6) · teardown decision
(oai-p1-sandbox, vmss none created) · case-study assembly from each chunk's
"paragraph shape" · AWS S3 first-delivery peek (P2 side, passive).
Next gate: Fable full review per REVIEW_BRIEF.md, then Stage 8 publication —
target live before 20 Sept (Amsterdam).
