# Findings and recommendations

This document is the audit report of the project: what was found, what it
rests on, what it costs or risks, and what to do about it. It is written so
that it can be read on its own, and each finding says which layer of data it
comes from. "Real" means the Azure sandbox's own export. "Synthetic" means the
engineered layer built to reproduce situations the sandbox could not, such as
a reserved-instance purchase, a tax line or a second currency, with every row
flagged as engineered. Nothing that rests on synthetic data is presented as a
fact about Azure.

Each finding carries six things. The finding itself, in plain language. The
evidence, with its data label and where to find it in this repository. The
FinOps Framework capability it belongs to, using the Foundation's own names,
so that a reader who knows the Framework can place it and a reader who does
not can look it up. The impact: what it costs, what it hides, or what it
breaks. The recommendation, stated as an action. And its status: built,
stated as a limitation, mitigated, or still open.

The findings are ordered by consequence rather than by the stage in which
they were found. Version drift comes first because it decides whether any
later number is being read correctly; the sanitiser's own miss comes last,
because it was found on the final day and belongs on the record for the same
reason as the others.

| # | Finding | Evidence (data) | Capability | Impact | Recommendation | Status |
|---|---|---|---|---|---|---|
| 1 | Azure's native FOCUS export declares `1.0r2` (96 columns) while the announcement implies 1.2; the 1.2-preview declares 105 columns and is selectable only at billing-account scope. Three `x_` columns become root columns one version later. | Export manifests, July–Sept 2026 (real) · `docs/READINESS_MEMO_1_2_to_1_4.md` | Data ingestion | A pipeline coded to the announced version reads columns that are not there and breaks silently on the next promotion. | Read the manifest's `dataVersion` before anything else; gate every version-specific rule on it at row level; keep `version_diff.py` in the release checklist. | Built in; era gates on every row |
| 2 | `CommitmentDiscountId` holds `''` where the specification requires null, on every row of the real export: 236 MUST failures from one habit. | `docs/conformance-report.md` (real, 31 July 2026) | Data ingestion · Reporting | Manufactures 354 phantom failures three columns away and **disables the mandated invoice reconciliation**: `InvoiceId` is `''` too, so nothing joins. | Normalise `''` → NULL at ingestion (done in `focus_unified`, decision D3); raise with the provider; never run the empty-string sweep on the merged view, where it reports zero and reads as a pass. | Mitigated in the pipeline; provider-side open |
| 3 | The three-way invoice tie-out closes to the cent, with tax, credit and purchase shown as reconciling items: but only on the v1.4-shaped synthetic layer; the real rows cannot be tied (see #2) or are not yet invoiced. | `sql/stage6_reconciliation.sql` (synthetic) · Q1–Q6 screenshots | Invoicing & chargeback | The control exists and is proven; it cannot yet be exercised on this provider's data as delivered. | State it as a limitation, not a claim; re-run the day Azure populates `InvoiceId` and ships the 1.4 supplemental datasets. | Stated in README |
| 4 | Real AI token spend ties exactly to the bill, twice: 1,422,991 tokens / $0.281718 and 1,417,163 / $0.280553. Output tokens differ by 0.4 % on identical input. | `sql/stage7_queries.sql` C2/C2b · `data/stage7/token_generation_log.csv` (real) | Reporting · Unit economics | Token spend is reconcilable at the token, so per-job cost variance is measurable and attributable to generation, not billing. | Keep a local usage subledger for every AI workload and reconcile it to the export monthly; treat rate as stable and job cost as variable. | Proven; method reusable |
| 5 | Batch buying mode bills at half the interactive list rate ($0.05 / $0.20 vs $0.10 / $0.40 per million tokens), verified in billing; the enqueued-token limit (2 M of 50 M) is the only AI-native budget. | C3 · deployment blade screenshot (real) | Rate optimisation · Budgeting | 50 % on rate for latency-tolerant work; quota is the first cost control and currency budgets cannot see it. | Default latency-tolerant workloads to batch; set the enqueued-token limit deliberately at deployment and own the quota request as a cost decision. | Adopted in the sandbox |
| 6 | The AI billing resource was created by a quick-create wizard in `NetworkWatcherRG`, outside the governed resource group, with platform tags only. | Cost Analysis screenshot · export `ResourceId` (real) | Allocation | Real spend invisible to team showback on day one: the untagged bucket, in a one-person sandbox. | Azure Policy: allowed resource groups and required tags on AI resource types; allocation queries must surface UNTAGGED as its own line, never drop it. | Detected by query; policy not yet applied |
| 7 | VM start/stop scheduling removed 70.2 % of compute-hours and saved $0.00: free-tier compute bills nothing and disk + IP are 100 % of the VM's bill. | C4a–C4c · Fri/Sat exhibit (real) | Workload optimisation | Scheduling is a compute lever; on this workload the floor is the whole bill. The saving switches on when the allowance ends or the size grows. | Keep the schedule (its own cost is nil); attribute future savings against the compute meter only; never quote a saving on a meter that bills zero. | Capability proven; counterfactual stated |
| 8 | Commitment coverage of *coverable* spend is 85.5 % against a naive all-usage figure of 63.4 %; the EUR line is 0 % on both. | `sql/stage6_coverage.sql` Q7–Q9 (synthetic) | Rate optimisation · Reporting | The naive figure sends a buyer shopping for commitments to cover demand that is not eligible. | Report coverage with an eligibility flag; publish the uncovered-eligible action list (Q8) instead of the headline. | Built; native column arrives with FOCUS 1.4 |
| 9 | Commitment closure is not evaluable for the 3-year reservation: the export covers 1 of 1,096 term days. | Cross-dataset check · Q10 (synthetic) | Reporting | A utilisation dashboard would report 0.09 %: the length of the export, not the performance of the commitment. | Utilisation needs the term from `contract_commitment`; report "not evaluable" as a verdict, never as a number. | Built |
| 10 | Billing-period timestamps carry a UTC offset; cost timestamps are naive. An equality join passes on a UTC machine and fails in Cape Town; a cast-to-date fails west of Greenwich. | Stage 6 finding S7 · four-timezone proof (synthetic) | Data ingestion | Verdicts that depend on the analyst's laptop. | Compare periods at civil-date grain, reading the text as written; generate plain dates at source. | Fixed; proven in four zones |
| 11 | The subscription outage (Aug 22–30) shows in the export as **absent dates**, not zero-cost rows. | Export row dates (real) | Anomaly management · Forecasting | Any average over days-present silently excludes the outage; a hard-coded day count under-reports it. | Count days from the data; treat missing dates as a first-class anomaly signal. | Applied in C4a |
| 12 | Billing latency for a daily export is quantised: batch-2 charges landed on the first export tick after usage (≤ 11.2 h); batch 1 is bounded, not measured, because first-seen times were not logged and overwrite mode destroyed the evidence. | Kick-off LOG §B (real) | Reporting · Data ingestion | You cannot recover observability you did not log. | Log first-seen timestamps forward, every time; state unmeasured values as bounds. | Method corrected for sample 2 |
| 13 | The reference `focus-validator` evaluates allowed-value checks across the column, not per row: one conformant value masks any number of non-conformant ones. | `docs/reference-validator-run.log` · Stage 4 notes §31.2 (planted fixtures) | Data ingestion | On production data, enum violations would essentially never be detected. | Raise upstream; keep this harness's per-row check as the control until fixed. | Not yet raised |
| 14 | The API key was exposed three times in one week (chat paste, screenshot, chat paste) despite a values-in-environment design. | Kick-off LOG (real) | Governance | Credential exposure is the failure mode that does not scale down. | Rotate on every logged exposure; screen every publishable artefact for the class; keys never in files. | Key 1 regenerated 7 Sep 2026 |
| 15 | The sanitiser verified the parquet and wrote the manifest beside it with the subscription id intact; the publication checker caught it on the first run against the publish tree. | `publication_check.py` run, 13 Sep 2026 (real) | Governance | A control that covers one file is not a control over the folder. | Sanitise every carried-over string, not chosen columns; run the checker last, every time, against the tree that ships. | Fixed at source; checker clean |

## What to do first, in an enterprise

The findings above come from a sandbox that cost fifteen dollars. The
question a reader responsible for a real estate will ask is which of them
matter at scale, and in what order. This is that order.

**Allocation, before dashboards.** Finding 6 is the one that scales worst.
A quick-start wizard put real spend outside the governed part of the estate
with the wrong tags, in a sandbox with a single user, on the first day of
using AI. Every team in a large organisation has the same wizard. A policy
that restricts where high-variance resources may be created, and requires
the organisation's tags at creation, costs nothing and prevents the untagged
bucket from growing. Until it shrinks, nothing built on top of the allocation
can be trusted.

**Read the manifest, and gate on the version.** Finding 1. The export Azure
delivered was a version behind the announcement, and the next version moved
three provider columns into the standard. A pipeline that assumes the
announced version reads columns that are not there. Every rule that depends
on a version should be gated on the version the export declares, and the
specification diff should be re-run at every tag.

**Fix the placeholder at ingestion.** Finding 2. One line that turns empty
text strings into proper empty values is the difference between an invoice
reconciliation that runs and one that cannot. It is the cheapest fix in this
document and it removes the largest count of failures.

**Report coverage against coverable spend.** Finding 8. The naive figure
sends a buyer shopping for commitments to cover demand that no commitment
can cover. The eligibility-aware figure produces a short action list
instead. The difference is real money spent on the wrong contract.

**Log first-seen timestamps.** Finding 12. Observability that was not logged
cannot be recovered afterwards, and the project learned this the expensive
way. Logging when a charge first appears in the portal and in the export is a
line in a file, and it turns a bound into a measurement.
