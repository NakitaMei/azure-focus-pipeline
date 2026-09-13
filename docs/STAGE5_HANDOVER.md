# Stage 5 — Handover

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 5 — Query layer and dashboard · **Status: COMPLETE**
**Date completed:** 31 August 2026
**Next stage:** 6 — v1.4 alignment layer (open in a fresh chat)

Read this first when picking up Stage 6. Full reasoning, findings S1–S6,
incident A1 and the dashboard build log are in `STAGE5_WORKING_NOTES.md`.

---

## Where the project stands, Stages 1–5

| Stage | Status | Evidence |
|---|---|---|
| 1 — Azure setup, real FOCUS export | ✅ Complete (pre-Stage-4) | 118-row real export at 1.0r2, 96 cols; $20/month budget set on the sandbox subscription |
| 2 — Ingestion & sanitisation | ✅ Complete | `build_unified.py`, `data/raw-sanitised/`, D3 normalisation ('' → NULL in focus_unified) |
| 3 — Synthetic layers & guardrails | ✅ Complete | `seed_data.py` (3 eras, x_Synthetic flagged), negative fixtures never merged, the four standing guardrails |
| 4 — Spec-derived conformance harness | ✅ Complete (19 Aug) | 166 checks; 14/14 planted violations caught; real export: 236 MUST / 1,170 SHOULD, all from empty-string nulls; exits 1 correctly |
| 5 — Query layer & dashboard | ✅ **Complete (31 Aug)** | `queries.sql` (13 queries, §5.1-audited, zero exceptions), findings S1–S6, incident A1, four-persona Looker dashboard published, URL + captures in /docs |
| — GitHub publication | ⏳ Carried (Stages 4 → 5 → 6) | Deliberate deferral; `publication_check.py` runs LAST before first push |

## What Stage 5 built

- **`queries.sql`** — 13 queries: showback (1a–1d, incl. bill/consumption
  bridge), budget vs actual (2a–2c, incl. out-of-scope disclosure),
  anomaly log (3a–3b), savings ladder (4a–4b), block-pricing waste (5),
  commitment utilisation (6, verdict-based).
- **`run_queries.py` v2** — named headers; string/comment-aware statement
  splitter (v1's naive `;`-split broke on a semicolon inside a string).
- **`export_for_looker.py`** — writes exports/*.csv; 13 `P1S5` Google
  Sheets in Drive feed the dashboard.
- **Dashboard** — "P1 Azure FOCUS Pipeline — Stage 5 Dashboard
  (July 2026)", four persona pages (Team showback / Anomaly / Budget vs
  actual / Executive), report-level currency control, metric named in
  every title. URL + captures: `docs/dashboard/`.

## Stage 5 findings that bind future SQL (S1–S6)

1. **S1** `ChargePeriodStart` for consumption questions;
   `BillingPeriodStart` for bill questions. The Correction row proves it
   (June consumption, July bill — matches invoice_detail
   INV-2026-07-0001-002 = −1.85).
2. **S2** A budget comparison must scope to the budget's subject
   (`x_Synthetic = FALSE`); otherwise it reports dataset design.
3. **S3** Round for display only — never before summing.
4. **S4** PricingQuantity ≠ ConsumedQuantity has two causes; only block
   rounding is waste, and only after restating both in the same unit.
5. **S5** ResourceName collides across layers ("vm-web-01" is both a
   real VM and a synthetic fixture). **Group and join on ResourceId**
   (COALESCE to name only for the 23 null-Id rows); display names.
6. **S6** An anomaly baseline must be *defined*: median of NONZERO
   resource-days. Zero-cost days are scored but never the benchmark.

Plus **A1**, the anomaly incident: fx-appliance-01, one day, 18.00
EffectiveCost / 0.00 BilledCost — a cash-based detector sees nothing.

## What is already banked FOR Stage 6 (inventory this, don't rebuild)

- **`XDS-invoice-reconciliation` exists in the Stage 4 harness** — joins
  cost_and_usage to `invoice_detail` on `InvoiceId` and reports 202 of
  204 rows carry no InvoiceId (the "unallocatable rows as reconciling
  items" requirement, half-done).
- **Query 1c/1d are the reconciliation warm-up**: the bill tie-out
  pattern (BilledCost, BillingPeriodStart, labelled panels, UNION
  totals) is exactly the shape Stage 6's per-invoice tie-out needs, and
  the −1.85 correction is already mapped to its invoice line.
- **`version_diff.py` output = the readiness memo's raw material**:
  columns added/removed, feature-level and nullability changes, and
  which harness checks a 1.4 move breaks.
- **Three memo conclusions pre-established**: F10 and F24 fixed upstream
  at v1.4 in the way this project derived independently; F12 also fixed
  at v1.4.
- **Layer C paths (local)**: `data/unified/focus_unified.snappy.parquet`,
  `data/supplemental/` for the three CSVs (billing_period,
  invoice_detail, contract_commitment). `contract_commitment` join key:
  cost.CommitmentDiscountId = contract.ContractCommitmentId.
- **Known fixture quirks** (state them, don't rediscover them): the 1yr
  commitment's description says "1-year" but its recorded term is 31
  days (trust the period columns); ~23 Usage rows have no ResourceId;
  invoice_detail is 2 rows / 18 cols at v1.4.

## Open items entering Stage 6

- [ ] **GitHub publication session** — checklist in Stage 4 working
      notes §24/§31; `publication_check.py` runs last, immediately
      before the first push.
- [ ] **Budget figure** — 20.00 USD/month is still a flagged assumption
      (queries 2a/2b + dashboard note). Confirm before Amsterdam.
- [ ] Two community issues worth raising before Amsterdam (Stage 4
      working notes §31).
- [ ] Two SHOULD-level rules the reference validator has and the
      harness doesn't (ServiceSubcategory uniqueness; PricingUnit
      UnitFormat) — both implementable.

## Working method (unchanged, restate in the Stage 6 opener)

One chunk at a time — Claude writes, Nakita runs locally and sends a
screenshot, review before proceeding. Plain language first, every new
term defined. Exact copy-pasteable commands. Claude fixes files rather
than instructing edits where error risk exists. Verify against actual
files, never assume (paths especially — use `find`). Decisions flagged
for Nakita's call. Errors owned openly. Living notes updated
continuously: plain-English summary before technical detail.

---

## Stage 6 opening prompt (paste into the fresh chat)

> Attached: master v3 (§2.1 and the §5.1 standing rules remain binding),
> the Stage 5 handover, Stage 5 working notes, `focus_unified` and the
> three Layer C CSVs (billing_period, invoice_detail,
> contract_commitment). Build Stage 6, the v1.4 alignment layer:
> (1) the three-way reconciliation Cost & Usage ↔ Invoice Detail ↔
> Billing Period, proving SUM(BilledCost) per InvoiceId ties to the
> invoice total to the cent, with unallocatable rows included and shown
> as reconciling items; (2) the eligibility-aware coverage analysis —
> coverage of *coverable* spend, not of all spend; (3) the one-page
> "1.2 → 1.4 readiness" memo: what this pipeline already satisfies, what
> changes when Azure ships 1.4, and the covering/covered recognition
> note with the consolidation-accounting parallel.
>
> Findings S1–S6 from the Stage 5 handover bind all SQL — especially S1
> (bill questions filter on BillingPeriodStart), S5 (join on Ids, never
> names) and S3 (round for display only). Stage 4 already banked the
> XDS-invoice-reconciliation join (202 of 204 rows carry no InvoiceId)
> and version_diff.py's memo raw material, with F10/F24/F12 conclusions
> pre-established — start by inventorying these, not rebuilding them.
> Same working method as Stages 4–5: one chunk at a time, stop after
> each so I can run it and send a screenshot; plain language with terms
> defined as they appear; verify against my actual files; keep Stage 6
> working notes updated as we go, plain-English summary first.
