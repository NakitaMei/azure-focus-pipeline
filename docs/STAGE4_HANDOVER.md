# Stage 4 — Handover

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 4 — Spec-derived conformance harness · **Status: COMPLETE**
**Date completed:** 19 August 2026
**Next stage:** 5 — Query layer and dashboard (open in a fresh chat)

Read this first when picking up Stage 5. It is the short version; the full
reasoning, findings F23–F46 and every decision are in
`STAGE4_WORKING_NOTES.md`.

---

## What exists now

**Nine scripts**, each with one job:

| Script | Does | Output |
|---|---|---|
| `spec_source.py` | fetches and parses the specification at five tags | `docs/spec/*.json` |
| `rules.py` | requirement-sentence parser (module, not a script) | — |
| `validate.py` | the conformance harness | console + `docs/conformance-report.md` |
| `version_diff.py` | spec diff between tags, plus impact on the harness | console |
| `seed_data.py` | synthetic fixtures across three schema eras | 3 Parquet + manifests |
| `self_test.py` | 15 generator checks | pass/fail |
| `build_unified.py` | sanitises the real export, merges the layers | `focus_unified`, `raw-sanitised` |
| `generate_layer_c.py` | the v1.4 supplemental datasets | 3 CSVs |
| `check_files.py` | verifies what was written | counts + checksums |

**Run order:** `spec_source` → `seed_data` → `self_test` → `build_unified` →
`generate_layer_c` → `validate --report`. Verified end to end.
`spec_source.py` is the **only** script that touches the network.

**Seven datasets validated, across two specification versions:**

| Target | Rows | Cols | Validated at |
|---|---:|---:|---|
| `real:31 July 2026` | 118 | 99 | v1.2 |
| `synthetic-v1.2` | 76 | 66 | v1.2 |
| `synthetic-legacy` | 10 | 51 | v1.2 |
| `unified` | 204 | 114 | v1.2 |
| `negative` | 14 | 68 | v1.2 — **never merged** |
| `layerC:billing_period` | 3 | 6 | **v1.4** |
| `layerC:invoice_detail` | 2 | 18 | **v1.4** |
| `layerC:contract_commitment` | 2 | 28 | **v1.4** |

---

## Result

| | |
|---|---|
| Checks | **166**, plus 3 cross-dataset |
| Citing a specification sentence | 165 |
| Derived, labelled as such | 1 (`PERIOD-ordering`) |
| Nullability statements at v1.2 | 88 — **70 implemented, 18 refused with reasons** |
| Planted violations detected | **14 of 14, 0 incidental** |
| Real Azure export | **236 MUST, 1,170 SHOULD** |
| Everything else | 0 MUST |

`validate.py` exits **1**, and that is correct: a MUST is broken on the real
layer. Do not "fix" it.

---

## The seven things Stage 5 must not get wrong

These are the Stage 4 findings that change how a query must be written. Each one
produces a **wrong number that looks right** if ignored.

### 1. Group tags on the PARSED value, never on the raw string

`Tags` is a JSON string, and Azure does not emit its keys in a stable order.
In this dataset:

| | |
|---|---|
| Distinct raw `Tags` strings | 3 |
| Distinct parsed `team` values | **2** |

`platform` appears under **two different raw strings** — identical tags, different
key order. `GROUP BY Tags` splits one team into two and both halves look
plausible. Use `json_extract_string(Tags, '$.team')`.

### 2. Untagged is 38 of 204 rows, and `x_CostCenter` is useless

`Tags` is null on **38 rows (19%)**. That is the UNTAGGED bucket Master v3 §5.1
requires to be surfaced rather than dropped.

`x_CostCenter` is populated on **zero** rows in every era. In the raw export it
holds `''` on all 118 rows; `focus_unified` normalises that to NULL by decision
D3. **Do not use it as an allocation key** — and note that a query written
against `data/raw-sanitised/` instead of `focus_unified` would need
`WHERE x_CostCenter IS NULL OR x_CostCenter = ''`, because there `''` survives.

### 3. Every cost aggregation needs a currency filter or `BillingCurrency` in the `GROUP BY`

`focus_unified` holds USD and EUR. Inherited guardrail from Stage 3, unchanged,
and still the easiest way to produce a total that is wrong in a way nothing about
it looks wrong.

### 4. A showback of `SUM(BilledCost)` is dominated by one purchase row

| ChargeCategory | Rows | BilledCost |
|---|---:|---:|
| Usage | 198 | 27.17 |
| Usage (Correction) | 1 | −1.85 |
| **Purchase** | **2** | **2,702.40** |
| Tax | 1 | 11.16 |
| Credit | 1 | −25.00 |
| Adjustment | 1 | −3.72 |

**Two rows are 99% of BilledCost.** A team showback on BilledCost is a chart of
one reservation purchase. Use `EffectiveCost` for consumption showback and put
Purchase, Tax, Credit and Adjustment in the reconciling panel §5.1 asks for —
which is exactly why that requirement exists.

### 5. Correction rows cannot be analysed by unit economics

`ChargeClass = "Correction"` exempts a row from the price × quantity identity —
the specification says so explicitly as a MAY. One row here. Any unit-price,
variance or rate-efficiency query must exclude corrections or it will report a
discrepancy that the specification permits.

### 6. Commitment utilisation needs the TERM, and the term is in Layer C

`contract_commitment` carries `ContractCommitmentPeriodStart/End`. Without it,
utilisation is unanswerable rather than merely imprecise:

| Commitment | Coverage | Verdict |
|---|---|---|
| `res-basv2-1yr-001` | term fully covered | closes exactly at 74.40 |
| `res-basv2-3yr-upfront-001` | **1 of 1,096 days** | not evaluable — a short export, not a shortfall |
| `res-basv2-legacy-2023` | no contract record | term unknown |

A utilisation dashboard that reports the 3-year reservation as 0.09% utilised is
reporting the length of the export, not the performance of the commitment.

### 7. Never reason from sign, and never assume `IS NULL` finds absent values

Negative `BilledCost` is a legitimate Usage row (the rebate). And `''` is not
NULL — that single fact produced 354 phantom failures in chunk 3 and disabled a
mandatory reconciliation. `focus_unified` is safe because D3 normalised it;
**anything querying the per-layer views is not.**

---

## Guardrails carried forward from Stage 3, still binding

1. **`data/raw/` is never committed.** Unsanitised personal data.
2. **Negative fixtures are never merged.** They live outside `data/synthetic/`.
3. **Era awareness.** A rule or query about a column introduced at 1.2 cannot be
   applied to a 1.0-era row. 128 of 204 rows predate several columns.
4. **The empty-string sweep binds to per-layer views, never to `focus_unified`.**

---

## What Stage 4 already banked toward Stage 6

**Start Stage 6 by inventorying this, not by rebuilding it.**

- **The three-way reconciliation exists.** `XDS-invoice-reconciliation` joins
  cost_and_usage to `invoice_detail` on `InvoiceId` — the key the specification
  names — and reports **202 of 204 rows carry no InvoiceId**, which is the
  "unallocatable rows shown as reconciling items" requirement.
- **`version_diff.py` produces the raw material for the "1.2 → 1.4 readiness
  memo"**: columns added and removed, feature levels and nullability changed, and
  which of the harness's own checks a v1.4 move would break.
- **Two of the memo's conclusions are already established.** F10 and F24 were
  fixed upstream at v1.4, in the way this project derived independently; F12 was
  also fixed at v1.4.

---

## Open items entering Stage 5

- [ ] **Publication / GitHub session** — full checklist in working notes §24 and
      §31. Deferred by decision; nothing depends on it.
      **Run `publication_check.py` last, immediately before the first push**
      (working notes §32). It is a control rather than a checklist item: it
      compares every publishable file against the real identifiers in
      `data/raw/`, and reports the file and count without ever printing a value.
- [ ] **Two community issues** — working notes §31. Worth raising **before**
      Amsterdam in late September, not after.
- [ ] Two SHOULD-level rules the reference validator catches and this harness does
      not: `ServiceName SHOULD have one and only one ServiceSubcategory`, and
      `PricingUnit SHOULD conform to UnitFormat`. Both implementable.
- [ ] A named multi-row collision fixture (deferred from chunk 4a) — needs its own
      fixture set, because the negative file's contract is one fault per row.
- [ ] `focus_unified.snappy.xlsx` at project root is a local inspection
      convenience. Not for commit.

---

## Stage 5 opening prompt (paste into the fresh chat)

> Attached: master v3 (§5.1 rules are binding), the keepsake, this handover, the
> Stage 4 working notes, `focus_unified` and the three Layer C CSVs. Write
> `queries.sql`: showback by team with UNTAGGED surfaced and tax/credit/purchase
> reconciling items in their own panel; budget vs actual; anomaly log; the savings
> ladder with each counterfactual labelled; the block-pricing waste query;
> commitment utilisation. Every query obeys the §5.1 standing rules — then audit
> your own SQL against them line by line before returning it. Then the Looker
> Studio design for the four persona views, each labelled with which cost metric
> it uses and why.
>
> Seven Stage 4 findings bind the SQL and are set out in the handover: parse Tags
> rather than grouping on the raw JSON string; 38 rows are untagged and
> `x_CostCenter` is empty on all of them; currency in every GROUP BY; two Purchase
> rows are 99% of BilledCost so consumption showback uses EffectiveCost;
> Correction rows are exempt from unit economics; commitment utilisation needs the
> term from `contract_commitment` or it reports export length rather than
> performance; and `''` is not NULL outside `focus_unified`.

Same working method as Stage 4: one chunk at a time, stop after each so I can run
it and send a screenshot. Explain new SQL ideas in plain language and define terms
as they come up. Verify against my actual files rather than assuming. Keep
updating my Stage 5 working notes as we go — plain-English summary first, then the
technical detail.
