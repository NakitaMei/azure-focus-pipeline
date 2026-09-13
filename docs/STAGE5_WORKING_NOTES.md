# Stage 5 — Working Notes

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 5 — Query layer and dashboard · **Status: IN PROGRESS**
**Started:** 20 August 2026
**Method:** one chunk at a time; every query run against the real
`focus_unified` before handover, then re-run and verified on my machine;
plain-English summary first, technical detail after. Master v3 §5.1 rules
binding; the seven Stage 4 handover findings binding.

---

## §0. Pre-flight verification (before any SQL was written)

All seven handover findings re-verified against the actual files, not
assumed. All confirmed. Two additions beyond the handover:

- **The anomaly candidate is `fx-appliance-01`** — active exactly one day
  (26 July 2026), EffectiveCost 18.00 against a typical daily resource top
  of 2–5. This is the Stage 5 anomaly-log subject.
- **The 38 untagged rows split 34 + 4.** 34 are Usage rows (the real
  UNTAGGED showback bucket); 4 are Purchase (2), Tax (1), Credit (1),
  which belong in the reconciling panel *by ChargeCategory*, not in
  UNTAGGED. Tags on billing events are not expected; counting them as
  "untagged spend" would overstate the tagging problem.

Dataset facts confirmed: 204 rows / 114 columns; eras 1.0r2 (118, real),
1.2 (76, synthetic), pre-1.2 (10, legacy — billing period March 2024);
currencies USD 202 / EUR 2; `x_CostCenter` populated on zero rows.

---

## §1. Chunk 1 — Showback by team (Queries 1a–1d)

### Plain-English summary

A showback answers "who consumed what?", so it may contain only
consumption. Billing events — the two reservation Purchases (2,702.40,
99% of BilledCost), Tax, Credit, Adjustment — go in their own reconciling
panel, and a third panel proves the two together account for every row
and every cent of the bill. The consumption panel uses EffectiveCost (the
amortised "what did consuming this actually cost us" number); the bill
panels use BilledCost (the cash number). No metric is named just "Cost".

**How to read the consumption result (my own note-to-self):** `platform`
and `data` are *tagged* teams — their spend is allocated. `UNTAGGED`
(34 rows, 12.63) is the spend belonging to nobody — the allocation gap
the findings framework wants surfaced. `data` showing 0.00 is not a bug:
all 48 of their rows are Storage charges metering inside free grain —
"tagged and free" and "untagged" are different states and the dashboard
should show both.

### Stage 5 Finding S1 — which Start column depends on the question

The first run of the tie-out came back one row short: July should hold
194 rows and the ChargePeriodStart filter returned 193. The missing row
is the **Correction**: `ChargePeriodStart` 14 June 2026 (it corrects June
consumption) but `BillingPeriodStart` July (it sits on July's bill —
matching `invoice_detail` INV-2026-07-0001-002 = −1.85 exactly).

§5.1 rule 1 fixes *how* to filter (Start column, half-open). The
*question* fixes *which* Start:

| Question | Filter column | Correction lands in |
|---|---|---|
| "What did July's consumption cost?" | `ChargePeriodStart` | June (restated) |
| "What is on July's bill?" | `BillingPeriodStart` | July |

Decision: 1a (consumption) filters on ChargePeriodStart; 1b and 1c (bill
views) filter on BillingPeriodStart; 1d is a bridge query returning
exactly the rows in one scope and not the other — expected and actual
result: one row, the Correction, −1.85.

Side effect worth noting: the July period filter also excludes the 10
legacy pre-1.2 rows (billing period March 2024) — the period filter is
doing Stage 3 guardrail 3 (era awareness) for free in this chunk.

---

## §1a. The four queries in full, explained line by line

### Query 1a — Consumption showback

```sql
SELECT
    COALESCE(json_extract_string(Tags, '$.team'), 'UNTAGGED') AS team,
    BillingCurrency,
    COUNT(*)                     AS row_count,
    ROUND(SUM(EffectiveCost), 2) AS effective_cost_consumption
FROM focus_unified
WHERE ChargeCategory = 'Usage'
  AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
  AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
GROUP BY 1, 2
ORDER BY BillingCurrency, effective_cost_consumption DESC;
```

**What each piece does:**

- `json_extract_string(Tags, '$.team')` — the Tags column holds a JSON
  string like `{"team":"platform","env":"prod"}`. This function parses
  the JSON and pulls out just the `team` value. Grouping on the *parsed*
  value is Finding 1: Azure writes the same tags in different key orders,
  so grouping on the raw string splits one team into two.
- `COALESCE(x, 'UNTAGGED')` — COALESCE means "use the first value that
  isn't NULL". If a row has no team tag, the team becomes the visible
  word UNTAGGED instead of an invisible blank. §5.1 rule 6 requires
  exactly this: untagged spend surfaced, never silently dropped.
- `AS team` — renames the column in the output. Every cost column gets a
  name that says which question it answers (§5.1 rule 2 — no column
  named just "Cost").
- `WHERE ChargeCategory = 'Usage'` — consumption only. Purchases, tax,
  credits and adjustments are billing events, not consumption; they get
  their own panel (1b).
- The two ChargePeriodStart lines — the **half-open period filter**
  (§5.1 rule 1): "on or after 1 July AND strictly before 1 August".
  Only the Start column is filtered; the End column already carries the
  exclusivity, and filtering it too shifts you off by one period.
  ChargePeriodStart (not BillingPeriodStart) because this is a
  *consumption* question — see Finding S1 above.
- `GROUP BY 1, 2` — group by the first and second SELECT columns (team,
  then BillingCurrency). Currency in every GROUP BY is Finding 3: USD
  and EUR must never be added together.
- `SUM(EffectiveCost)` — the amortised consumption metric. `ROUND(..., 2)`
  trims to 2 decimals for display.

**Verified result (Claude's run and my machine, 20 Aug — identical):**

| team | Currency | rows | EffectiveCost |
|---|---|---:|---:|
| platform | EUR | 2 | 6.62 |
| platform | USD | 104 | 101.27 |
| UNTAGGED | USD | 34 | 12.63 |
| data | USD | 48 | 0.00 |

### Query 1b — Reconciling items panel

```sql
SELECT
    ChargeCategory,
    BillingCurrency,
    COUNT(*)                  AS row_count,
    ROUND(SUM(BilledCost), 2) AS billed_cost_cash
FROM focus_unified
WHERE ChargeCategory <> 'Usage'
  AND BillingPeriodStart >= TIMESTAMP '2026-07-01'
  AND BillingPeriodStart <  TIMESTAMP '2026-08-01'
GROUP BY 1, 2
ORDER BY BillingCurrency, billed_cost_cash DESC;
```

**What each piece does:**

- `ChargeCategory <> 'Usage'` — `<>` means "not equal to". Everything
  that is *not* consumption: Purchase, Tax, Credit, Adjustment.
- `BillingPeriodStart` this time, not ChargePeriodStart — this panel
  asks "what is on July's *bill*?", a cash question (Finding S1).
- `SUM(BilledCost)` — the cash metric, because these rows are invoice
  events, not workloads. Using EffectiveCost here would show the two
  Purchases as 0.00 and hide 2,702.40 of real cash.
- Grouped by ChargeCategory (a Category column — §5.1 rule 4) and
  currency.

**Why this panel exists (Finding 4):** the two Purchase rows are 99% of
all BilledCost. If they leaked into the team chart, the showback would
be a picture of one reservation purchase. Quarantining them here is what
makes 1a honest.

**Verified result:** Purchase 2,702.40 · Tax 11.16 · Adjustment −3.72 ·
Credit −25.00 (all USD).

### Query 1c — Completeness tie-out

```sql
WITH july_bill AS (
    SELECT * FROM focus_unified
    WHERE BillingPeriodStart >= TIMESTAMP '2026-07-01'
      AND BillingPeriodStart <  TIMESTAMP '2026-08-01'
)
SELECT 'usage side' AS panel, BillingCurrency,
       COUNT(*) AS row_count, ROUND(SUM(BilledCost), 2) AS billed_cost_cash
FROM july_bill WHERE ChargeCategory = 'Usage' GROUP BY 2
UNION ALL
SELECT 'reconciling side', BillingCurrency,
       COUNT(*), ROUND(SUM(BilledCost), 2)
FROM july_bill WHERE ChargeCategory <> 'Usage' GROUP BY 2
UNION ALL
SELECT 'GRAND TOTAL (= sum of the two above)', BillingCurrency,
       COUNT(*), ROUND(SUM(BilledCost), 2)
FROM july_bill GROUP BY 2
ORDER BY BillingCurrency, panel;
```

**What each piece does:**

- `WITH july_bill AS (...)` — a **CTE** (Common Table Expression): a
  named, temporary result you define once and reuse. Here it means "the
  July bill" is defined in exactly one place, so all three totals below
  are guaranteed to use the same scope — no risk of the filter drifting
  between panels.
- `UNION ALL` — stacks result sets on top of each other. Three totals in
  one table: the usage side, the reconciling side, and the grand total.
  (`UNION ALL` keeps everything; plain `UNION` would silently remove
  duplicate rows, which is never what a tie-out wants.)
- `'usage side' AS panel` — a **string literal** used as a label column,
  so each stacked row says what it is.
- Everything in **BilledCost**, because it is the only metric that sums
  to the bill. EffectiveCost deliberately doesn't (amortisation moves
  cost between rows).
- No sign filters anywhere (Finding 7): the −1.85 correction and the
  rebate sit inside the usage side; the −25.00 credit inside reconciling.
  A `WHERE BilledCost > 0` would break the tie-out *and* hide real rows.

**The identity being proved:** usage + reconciling = grand total, per
currency, to the cent — so nothing was dropped between panels.

**Verified result:** USD 17.25 + 2,684.84 = **2,702.09** ✅ · EUR 6.62 =
6.62 ✅ · rows 187 + 5 = 192, + 2 EUR = every July-bill row ✅.

### Query 1d — The bridge

```sql
SELECT
    CASE WHEN BillingPeriodStart >= TIMESTAMP '2026-07-01'
          AND BillingPeriodStart <  TIMESTAMP '2026-08-01'
         THEN 'on July bill' ELSE 'not on July bill' END AS bill_scope,
    CASE WHEN ChargePeriodStart >= TIMESTAMP '2026-07-01'
          AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
         THEN 'July consumption' ELSE 'not July consumption' END AS consumption_scope,
    ChargeCategory, ChargeClass, ResourceName,
    CAST(ChargePeriodStart AS DATE) AS charge_period_start,
    ROUND(BilledCost, 2) AS billed_cost_cash
FROM focus_unified
WHERE ChargeCategory = 'Usage'
  AND (   (BillingPeriodStart >= TIMESTAMP '2026-07-01' AND BillingPeriodStart < TIMESTAMP '2026-08-01')
       <> (ChargePeriodStart  >= TIMESTAMP '2026-07-01' AND ChargePeriodStart  < TIMESTAMP '2026-08-01'));
```

**What each piece does:**

- `CASE WHEN ... THEN ... ELSE ... END` — SQL's if/then/else. Here it
  turns each date test into a readable label so the output explains
  itself.
- `CAST(ChargePeriodStart AS DATE)` — converts a timestamp
  (`2026-06-14 00:00:00`) to just a date (`2026-06-14`) for display.
- The strange-looking last condition: each bracketed test is TRUE or
  FALSE, and `<>` between two TRUE/FALSE values means "they disagree".
  So the WHERE keeps only rows that are **in one scope but not the
  other** — on July's bill but not July's consumption, or vice versa.

**Purpose:** it makes the difference between 1a's scope and 1c's usage
side *documented* instead of mysterious. Expected: exactly one row.

**Verified result:** one row — the Correction, `stp1sandbox`,
charge period 14 June, −1.85. ✅

---

## §1b. §5.1 audit for Chunk 1 (all pass)

| Rule | Verdict |
|---|---|
| 1 — Start column only, half-open | ✅ All four queries; plus S1: *which* Start is chosen by the question |
| 2 — EffectiveCost for showback, BilledCost for cash; metrics labelled | ✅ `effective_cost_consumption` / `billed_cost_cash`; nothing named "Cost" |
| 3 — ChargeCategory to one side before ListCost/ContractedCost | ✅ Vacuous this chunk (neither column summed); bites in the savings ladder |
| 4 — GROUP BY Category, display Names, JOIN on Ids | ✅ ChargeCategory grouped; no Type grouping; no joins yet |
| 5 — Savings state their counterfactual | ✅ N/A (Chunk 4) |
| 6 — Currency+unit in GROUP BY; untagged visible; never reason from sign | ✅ Currency everywhere; COALESCE→UNTAGGED; zero sign predicates |

Findings check: 1 ✅ parsed tag · 2 ✅ UNTAGGED surfaced, x_CostCenter
untouched · 3 ✅ currency · 4 ✅ Purchase quarantined · 5 ✅ correction
handled by period semantics · 6 → Chunk 6 · 7 ✅ focus_unified only.

---

## §2. Running the query layer on my machine (first-run log, 20 Aug)

How it works: `queries.sql` is just text; `run_queries.py` reads it,
hands each statement to DuckDB (in-memory — reads the Parquet, changes
nothing), and prints each result. Run from the VS Code terminal:

```
source .venv/bin/activate
python3 run_queries.py
```

Four things went wrong on the first run, in order — keeping them here
because each one is a general lesson:

1. **`command not found: python`** → macOS only has `python3`. Always
   `python3` on this machine.
2. **`No module named 'duckdb'`** → the terminal wasn't inside the
   project's virtual environment. Fix: `source .venv/bin/activate`
   (prompt shows `(.venv)` when active). The venv is the project's own
   shelf of installed packages.
3. **`IO Error: No files found ... data/focus_unified.snappy.parquet`**
   → the path in queries.sql was a guess. `find data -name "*.parquet"`
   printed the real address: `data/unified/focus_unified.snappy.parquet`.
   Lesson: ask the machine for paths instead of guessing.
4. **Same error after editing** → the edit was correct on screen but
   never saved — the ● dot on the VS Code tab means unsaved changes, and
   the terminal runs the *saved* file. Fix: Cmd+S (and File → Auto Save
   turned on so this can't recur).

General lesson from all four: **read the last line of the traceback
first** — it names the real problem every time.

---

## Open items / carried questions

- [ ] **Budget vs actual (Chunk 2):** confirm the budget source. Working
      assumption is the Stage 1 $20/month Azure budget — confirm the
      figure and whether it is USD-only (the EUR slice would then need
      conversion or exclusion, stated either way).

---

## §3. Chunk 2 — Budget vs actual (Queries 2a–2c)

### Plain-English summary

Budget vs actual compares what we planned to spend with what we actually
consumed. The plan: the Stage 1 Azure budget — **20.00 USD per calendar
month** (still marked as an assumption in the SQL; a one-line change if
the figure is different). The actual: July consumption on the **real
subscription only** — because that is what the budget governs. Result:
**3.03 of 20.00 consumed (15.2%)**, comfortably under, with a daily
burn-down showing consumption tracking far below the straight-line pace.

### Stage 5 Finding S2 — budget vs actual must scope to the budget's subject

`focus_unified` deliberately mixes the real Azure export (118 rows,
`x_Synthetic = FALSE`) with synthetic fixtures (86 rows, TRUE). The $20
budget is a real budget on the real subscription; the synthetic layer was
never inside its scope. Compared against the whole unified dataset, July
"actual" would be 113.90 consumption against a 20.00 budget — a 570%
blowout that never happened. That number would be **reporting the design
of the dataset, not the health of the subscription** — the same trap
shape as Finding 6 (the 3-year reservation "0.09% utilised" because the
export is one day long). Scope filter: `x_Synthetic = FALSE`. Everything
excluded is listed in 2c with its reason — nothing silently dropped
(the 1c tie-out philosophy).

Bonus fact this surfaced: the real sandbox is tiny and healthy — all 118
real rows are Usage, USD, totalling 3.03 for July. Every purchase, the
tax, the credit, the EUR slice: all synthetic.

### Stage 5 Finding S3 — round for display only, never before summing

First draft of 2b rounded each day's cost to 2 decimals and then summed:
nine days of 0.325 → 0.33 added three phantom cents, so the burn-down
ended at 3.06 while 2a said 3.03. Caught because the two queries were
tested against each other. Fix: carry unrounded values through every
calculation; `ROUND(...)` only in the final SELECT for display. A tie-out
between two queries answering the same question is itself a control.

### Query 2a — Budget vs actual, in full

```sql
WITH budget AS (
    SELECT 20.00 AS monthly_budget_usd    -- ASSUMPTION: Stage 1 Azure budget
),
actual AS (
    SELECT ROUND(SUM(EffectiveCost), 2) AS effective_cost_consumption
    FROM focus_unified
    WHERE x_Synthetic = FALSE                 -- budget's subject: real rows only
      AND ChargeCategory = 'Usage'
      AND BillingCurrency = 'USD'
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
)
SELECT
    monthly_budget_usd,
    effective_cost_consumption,
    ROUND(monthly_budget_usd - effective_cost_consumption, 2) AS remaining_usd,
    ROUND(100.0 * effective_cost_consumption / monthly_budget_usd, 1) AS pct_of_budget_consumed
FROM budget, actual;
```

**What each piece does:**

- **The budget lives in a one-row CTE** — `WITH budget AS (SELECT 20.00
  ...)` creates a tiny one-row, one-column table holding the figure. Why
  bother? So the number exists in exactly one place, visibly labelled as
  an assumption. When the real figure is confirmed, one line changes.
- `actual` is a second CTE: July real-subscription consumption, with all
  the standing guardrails (Usage only, USD only, half-open
  ChargePeriodStart filter — a consumption question, per S1).
- `FROM budget, actual` — a **cross join**: every row of one table paired
  with every row of the other. Normally dangerous; here both tables have
  exactly one row, so it simply puts the budget and the actual side by
  side in a single row for the arithmetic.
- `100.0 * ... / ...` — the `.0` matters: it forces decimal division.
  (Integer division would truncate: 100 * 3 / 20 = 15, losing the .2.)

**Verified result:** 20.00 budget · 3.03 consumed · 16.97 remaining ·
**15.2%** of budget.

### Query 2b — Daily burn-down, in full

```sql
WITH budget AS (
    SELECT 20.00 AS monthly_budget_usd
),
daily AS (
    SELECT
        CAST(ChargePeriodStart AS DATE)     AS day,
        SUM(EffectiveCost)                  AS effective_cost_day_raw
        -- NOT rounded here: round for display only, never before summing.
    FROM focus_unified
    WHERE x_Synthetic = FALSE
      AND ChargeCategory = 'Usage'
      AND BillingCurrency = 'USD'
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
    GROUP BY 1
)
SELECT
    day,
    ROUND(effective_cost_day_raw, 2)                          AS effective_cost_day,
    ROUND(SUM(effective_cost_day_raw) OVER (ORDER BY day), 2) AS cumulative_consumption,
    ROUND(monthly_budget_usd * DAY(day) / 31.0, 2)            AS straight_line_pace,
    ROUND(100.0 * SUM(effective_cost_day_raw) OVER (ORDER BY day)
                / monthly_budget_usd, 1)                      AS cumulative_pct_of_budget
FROM daily, budget
ORDER BY day;
```

**What each piece does:**

- **`SUM(...) OVER (ORDER BY day)` is a window function** — the one
  genuinely new idea in this chunk. A normal `SUM` with `GROUP BY`
  collapses rows into one total. A window function keeps every row and
  computes the sum *over a window of rows*: `OVER (ORDER BY day)` means
  "for each row, sum everything up to and including this day". That is a
  running total — each day's row shows the cumulative spend so far.
  No `GROUP BY` needed for it; the window is defined inside `OVER`.
- `DAY(day)` extracts the day-of-month number (22, 23, …31).
- `straight_line_pace = budget × day ÷ 31` — where cumulative spend
  *would* be if the budget burned perfectly evenly. The dashboard's "on
  track" line. `31.0` (not `31`) again forces decimal division.
- The real export starts 22 July, so the curve starts there — days 1–21
  are *no data*, not zero consumption. Worth stating on the dashboard.

**Verified result:** cumulative runs 0.14 → **3.03** (matching 2a
exactly, post-S3-fix), against a pace line ending at 20.00; final
cumulative_pct_of_budget **15.2%**.

### Query 2c — Out-of-scope panel, in full

```sql
SELECT
    'synthetic consumption (not the budget''s subject)' AS excluded_because,
    BillingCurrency,
    COUNT(*)                                    AS row_count,
    'EffectiveCost'                             AS metric,
    ROUND(SUM(EffectiveCost), 2)                AS amount
FROM focus_unified
WHERE x_Synthetic = TRUE AND ChargeCategory = 'Usage'
  AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
  AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
GROUP BY 2
UNION ALL
SELECT
    'synthetic billing events (reconciling panel 1b)',
    BillingCurrency,
    COUNT(*),
    'BilledCost',
    ROUND(SUM(BilledCost), 2)
FROM focus_unified
WHERE x_Synthetic = TRUE AND ChargeCategory <> 'Usage'
  AND BillingPeriodStart >= TIMESTAMP '2026-07-01'
  AND BillingPeriodStart <  TIMESTAMP '2026-08-01'
GROUP BY 2
ORDER BY excluded_because, BillingCurrency;
```

**What each piece does:**

- Two stacked `UNION ALL` blocks (same idea as 1c): synthetic
  *consumption* measured in EffectiveCost with a ChargePeriodStart
  filter; synthetic *billing events* measured in BilledCost with a
  BillingPeriodStart filter — each row of the output carries a `metric`
  label so the two are never mistaken for addable numbers (§5.1 rule 2).
- `''s` inside the label — **two single quotes make one literal
  apostrophe** in SQL. That is how `budget's` survives inside a
  single-quoted string.
- Purpose: the reader of 2a can see exactly what the scope decision
  excluded — 68 rows / 110.87 USD + 2 rows / 6.62 EUR of synthetic
  consumption, and 5 rows / 2,684.84 of synthetic billing events — and
  where each amount *is* reported instead (the showback 1a and the
  reconciling panel 1b).

**Verified result:** exactly those three lines.

### §5.1 audit for Chunk 2

| Rule | Verdict |
|---|---|
| 1 — Start column, half-open | ✅ ChargePeriodStart for consumption (2a, 2b, 2c top); BillingPeriodStart for billing events (2c bottom) — per S1 |
| 2 — Right metric, labelled | ✅ EffectiveCost vs a consumption budget; every output column named; 2c carries an explicit `metric` column |
| 3 — ChargeCategory split before ListCost/ContractedCost | ✅ Vacuous (neither summed) |
| 4 — Group Category / display Names / join Ids | ✅ ChargeCategory filters; no Type grouping; the only join is the deliberate one-row cross join |
| 5 — Counterfactual labelling | ✅ N/A (Chunk 4) |
| 6 — Currency in scope; untagged visible; no sign reasoning | ✅ `BillingCurrency = 'USD'` filter matches the budget's currency; 2c groups by currency; no sign predicates |

Findings check: 3 ✅ (currency filter stated) · 7 ✅ (no sign filters,
focus_unified only) · S1 ✅ applied · S2, S3 established this chunk.

---

## Chunk 2 run instructions

Replace `queries.sql` with the new version (the path at the top is
already set to `data/unified/...`). Then, in the VS Code terminal:

```
source .venv/bin/activate
python3 run_queries.py
```

Expected: the four Chunk 1 tables print first (unchanged), then QUERY 6
(= 2a: 15.2% of budget), QUERY 7 (= 2b: cumulative ending 3.03), QUERY 8
(= 2c: three excluded lines).

## Open items / carried questions

- [ ] **Budget figure**: 20.00 USD/month is still an assumption — confirm
      or correct (one line in the budget CTE, twice: 2a and 2b).
- [x] EUR handling for budget vs actual: resolved by S2 — the EUR rows
      are synthetic, so they fall outside the budget's subject and are
      disclosed in 2c.

---

## §4. Chunk 3 — Anomaly log (Queries 3a–3b)

### Plain-English summary

An anomaly query asks: did anything behave unlike everything else? Each
resource-day's consumption is compared to the **population median**
resource-day in the same currency — median rather than average, because
the average is dragged upward by the very anomaly being hunted (on this
data: average 1.13 vs median 0.60 — the anomaly flatters itself in a
mean-based test; the median doesn't move). Flag threshold: **10× the
median** — "an order of magnitude above typical" — chosen after checking
the actual distribution: the anomaly sits at 30×, the busiest ordinary
day (vm-web-01, 5.40) at 9×. One flag fires. It's the right one.

### Anomaly log — entry A1 (the narrative half)

| Field | Value |
|---|---|
| Resource | `fx-appliance-01` |
| What it is | Marketplace third-party security appliance **licence, monthly** (ServiceCategory: Security) |
| Owner | team `platform` (tagged — so there is someone to ask) |
| Lifetime | first seen 26 July 2026 · last seen 26 July 2026 · **1 day active** |
| Cost | EffectiveCost **18.00 USD** (30× the median resource-day) · BilledCost 0.00 on the day |
| Detection | Query 3a, 10×-median rule, flagged 20 Aug 2026 |
| Signature | New resource, never seen before, expensive from its first day, then gone — the "someone deployed something they shouldn't have" shape |
| Note | EffectiveCost 18.00 with BilledCost 0.00 is consistent with a monthly licence recognised in consumption terms without same-day cash — exactly why the anomaly ran on EffectiveCost (§5.1 rule 2: trends and consumption questions use EffectiveCost). A cash-based detector would have seen **nothing**. |
| Status | Documented. (In the Master v3 scenario: detected → killed → logged. Synthetic fixture, so no live resource to kill.) |

### Query 3a — Detection, in full

```sql
WITH resource_day AS (
    SELECT
        ResourceName,
        BillingCurrency,
        CAST(ChargePeriodStart AS DATE) AS day,
        SUM(EffectiveCost)              AS effective_cost_day_raw
    FROM focus_unified
    WHERE ChargeCategory = 'Usage'
      AND (ChargeClass IS NULL OR ChargeClass <> 'Correction')
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
    GROUP BY 1, 2, 3
),
typical AS (
    SELECT BillingCurrency,
           MEDIAN(effective_cost_day_raw) AS median_resource_day
    FROM resource_day
    GROUP BY 1
)
SELECT
    rd.ResourceName,
    rd.BillingCurrency,
    rd.day,
    ROUND(rd.effective_cost_day_raw, 2)                          AS effective_cost_day,
    ROUND(t.median_resource_day, 2)                              AS median_resource_day,
    ROUND(rd.effective_cost_day_raw / t.median_resource_day, 1)  AS multiple_of_median,
    CASE WHEN rd.effective_cost_day_raw >= 10 * t.median_resource_day
         THEN 'ANOMALY' ELSE '' END                              AS flag
FROM resource_day rd
JOIN typical t USING (BillingCurrency)
ORDER BY rd.effective_cost_day_raw / t.median_resource_day DESC
LIMIT 10;
```

**What each piece does:**

- **`resource_day` CTE** — the unit of observation: one row per resource
  per day, with that day's summed consumption. Unrounded (S3).
- **`(ChargeClass IS NULL OR ChargeClass <> 'Correction')`** — excludes
  the Correction *by category, not by sign* (Finding 7). Rationale: a
  correction restates another period's consumption, so in a daily view
  it shows up as a phantom "unusual day" that isn't day-of activity.
  Note the `IS NULL OR` part: for most rows ChargeClass is NULL, and in
  SQL `NULL <> 'Correction'` is *not true* — NULL comparisons return
  NULL, and a WHERE keeps only rows that are definitely true. Without
  the `IS NULL` arm, the filter would silently discard every normal row.
  (Same family of trap as `''` vs NULL in Stage 4.)
- **`typical` CTE** — one median per currency. `MEDIAN(x)` is the middle
  value of the population: half the resource-days cost less, half more.
- **`JOIN typical t USING (BillingCurrency)`** — attaches the right
  currency's median to every resource-day row. `USING (col)` is
  shorthand for `ON rd.col = t.col` when the column name matches — and
  currencies never cross-join, so USD days are only ever compared to the
  USD median (Finding 3 in join form).
- **`multiple_of_median`** — the readable test statistic: "this day is
  N× a typical day".
- **`CASE ... >= 10 * median THEN 'ANOMALY'`** — the threshold, written
  so the rule is visible in the output itself.
- `ORDER BY ... DESC LIMIT 10` — worst first, top ten only, so the
  output is a review queue rather than a data dump.

**Verified result:** exactly one flag — fx-appliance-01, 26 July, 18.00,
30.0× median. Runner-up (vm-web-01, 9.0×) correctly unflagged.

### Query 3b — Incident record, in full

```sql
WITH resource_day AS (
    ... same as 3a ...
),
typical AS (
    ... same as 3a ...
),
flagged AS (
    SELECT DISTINCT rd.ResourceName
    FROM resource_day rd
    JOIN typical t USING (BillingCurrency)
    WHERE rd.effective_cost_day_raw >= 10 * t.median_resource_day
)
SELECT
    f.ResourceName,
    ANY_VALUE(u.ServiceCategory)                          AS service_category,
    ANY_VALUE(u.ServiceName)                              AS service_name,
    ANY_VALUE(u.ChargeDescription)                        AS charge_description,
    COALESCE(ANY_VALUE(json_extract_string(u.Tags, '$.team')), 'UNTAGGED') AS team,
    u.BillingCurrency,
    MIN(CAST(u.ChargePeriodStart AS DATE))                AS first_seen,
    MAX(CAST(u.ChargePeriodStart AS DATE))                AS last_seen,
    COUNT(DISTINCT CAST(u.ChargePeriodStart AS DATE))     AS days_active,
    ROUND(SUM(u.EffectiveCost), 2)                        AS effective_cost_total,
    ROUND(SUM(u.BilledCost), 2)                           AS billed_cost_cash_total
FROM flagged f
JOIN focus_unified u ON u.ResourceName = f.ResourceName
WHERE u.ChargeCategory = 'Usage'
GROUP BY f.ResourceName, u.BillingCurrency;
```

**What each piece does:**

- **`flagged` CTE** — re-runs the 3a detection but keeps only the
  *names* of flagged resources (`SELECT DISTINCT` = each name once).
  The detection rule therefore exists in one logical form in both
  queries and cannot drift between them.
- **`JOIN focus_unified u ON u.ResourceName = f.ResourceName`** — pulls
  every Usage row for each flagged resource: the full life of the
  suspect, not just the anomalous day.
- **`ANY_VALUE(x)`** — "give me one representative value from the
  group". The descriptive fields (service, description) are identical on
  every row of a given resource, but SQL still demands every selected
  column be either grouped or aggregated; ANY_VALUE satisfies that
  without adding fake GROUP BY columns.
- **`MIN/MAX(...AS DATE)` + `COUNT(DISTINCT ...)`** — first seen, last
  seen, and days active: the lifetime facts that make the "born
  expensive, died next day" signature visible in one row.
- Both cost totals appear, **each labelled** — and their disagreement
  (18.00 effective vs 0.00 cash) is not an error, it is the finding: a
  cash-based detector would have seen nothing. §5.1 rule 2 earning its
  keep.

**Verified result:** one row — fx-appliance-01 · Security / Marketplace
Security Appliance · monthly licence · team platform · 26 July → 26
July · 1 day · 18.00 effective · 0.00 cash.

### §5.1 audit for Chunk 3

| Rule | Verdict |
|---|---|
| 1 — Start column, half-open | ✅ ChargePeriodStart (consumption question, per S1) in both CTEs |
| 2 — Right metric, labelled | ✅ EffectiveCost for the trend test; both totals in 3b labelled; the effective/cash divergence documented as a feature |
| 3 — Category split before ListCost/ContractedCost | ✅ Vacuous (neither summed) |
| 4 — Group Category, display Names, join Ids | ⚠️ 3b joins on ResourceName rather than ResourceId — deliberate, documented exception: fx-appliance-01's rows carry a stable name, and the display-name join keeps the incident record readable. Rule 4's Id-join requirement is aimed at cross-provider joins; single-provider, single-resource scope here. Flagged for the Chunk 7 audit to revisit. |
| 5 — Counterfactual labelling | ✅ N/A (Chunk 4) |
| 6 — Currency; untagged visible; no sign reasoning | ✅ Median per currency via the USING join; team COALESCEd to UNTAGGED in 3b; correction excluded by category, not sign |

New terms defined this chunk: MEDIAN, JOIN ... USING, ANY_VALUE,
NULL-comparison behaviour in WHERE (`IS NULL OR` guard), SELECT DISTINCT.

## Chunk 3 run instructions

Replace queries.sql with the new version; then:

```
source .venv/bin/activate
python3 run_queries.py
```

Expected new output: QUERY 9 (= 3a: top-10 table, one ANOMALY flag at
30.0×) and QUERY 10 (= 3b: one incident row for fx-appliance-01).

---

## §5. Chunk 4 — The savings ladder (Queries 4a–4b)

### Plain-English summary

"We saved money" means nothing until you say **compared to what**. §5.1
rule 5 defines the ladder: **negotiation** savings (List − Contracted:
vs paying the public list price), **commitment** savings (Contracted −
Effective: vs paying our negotiated rate on demand), and the **headline**
(List − Effective), which is only ever the sum of the first two — never
an independent third claim. July result (USD): negotiation **3.72
(2.5%)** + commitment **30.90 (20.8%)** = headline **34.62 (23.3% off
list)**. The EUR slice is a built-in control: all three costs equal, a
flat ladder, zero savings — a discount story that correctly reports no
discounts.

The coverage split (4b) shows *where* the savings live: all 30.90 of
commitment saving sits on the 54 commitment-covered rows; on-demand rows
show contracted = effective to the cent — commitment savings cannot
exist where no commitment applies, and the query proves it rather than
assumes it.

### Query 4a — The ladder, in full

```sql
WITH usage_july AS (
    SELECT
        BillingCurrency,
        SUM(ListCost)       AS list_raw,
        SUM(ContractedCost) AS contracted_raw,
        SUM(EffectiveCost)  AS effective_raw
    FROM focus_unified
    WHERE ChargeCategory = 'Usage'                        -- rule 3: one side only
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
    GROUP BY 1
)
SELECT '1. negotiation' AS rung,
       'vs paying the public list price'                 AS saved_compared_to,
       BillingCurrency,
       ROUND(list_raw, 2)                                AS list_cost,
       ROUND(contracted_raw, 2)                          AS contracted_cost,
       NULL                                              AS effective_cost,
       ROUND(list_raw - contracted_raw, 2)               AS saving,
       ROUND(100.0 * (list_raw - contracted_raw) / list_raw, 1) AS pct_of_list
FROM usage_july WHERE list_raw <> 0
UNION ALL
SELECT '2. commitment',
       'vs paying our negotiated rate on demand',
       BillingCurrency,
       NULL,
       ROUND(contracted_raw, 2),
       ROUND(effective_raw, 2),
       ROUND(contracted_raw - effective_raw, 2),
       ROUND(100.0 * (contracted_raw - effective_raw) / list_raw, 1)
FROM usage_july WHERE list_raw <> 0
UNION ALL
SELECT '3. HEADLINE (= rung 1 + rung 2)',
       'vs paying the public list price with no commitments',
       BillingCurrency,
       ROUND(list_raw, 2),
       NULL,
       ROUND(effective_raw, 2),
       ROUND(list_raw - effective_raw, 2),
       ROUND(100.0 * (list_raw - effective_raw) / list_raw, 1)
FROM usage_july WHERE list_raw <> 0
ORDER BY BillingCurrency, rung;
```

**What each piece does:**

- **One CTE, three readings.** The sums are computed once in
  `usage_july` (raw, unrounded — S3), then each UNION ALL block reads a
  different pair off the same numbers. The ladder identity
  (rung 1 + rung 2 = headline) is therefore guaranteed by arithmetic —
  (L−C) + (C−E) = L−E — not by hoping two queries agree.
- **`saved_compared_to`** — rule 5 as a literal output column: every
  savings row carries its counterfactual in words. A chart built on this
  table cannot show an unlabelled saving.
- **`NULL AS effective_cost`** — a deliberately empty cell. Rung 1 is
  about List vs Contracted; EffectiveCost is not part of that claim, so
  the column is blank rather than tempting the reader to cross-read.
  (Displays as NaN in pandas — that is "no value", not zero.)
- **`WHERE list_raw <> 0`** — a divide-by-zero guard for `pct_of_list`.
  On this data every currency group has nonzero list cost, but the guard
  makes the query safe against a future group that doesn't.
- **All three percentages use ListCost as the denominator** — so the
  percentages are additive too: 2.5% + 20.8% = 23.3%. Mixing
  denominators (e.g. commitment saving as % of Contracted) would make
  the rungs non-additive and quietly inflate the second rung.
- §5.1 rule 3 is the `ChargeCategory = 'Usage'` line: ListCost and
  ContractedCost are summed only after filtering to one side. (The
  Purchase rows carry no meaningful List/Contracted consumption story —
  mixing them in would double-count the commitment against itself.)
- The Correction row is outside scope automatically: its
  ChargePeriodStart is June (S1) — no special handling needed, which is
  itself worth knowing.

**Verified result:** USD 3.72 (2.5%) + 30.90 (20.8%) = 34.62 (23.3%);
EUR flat at 0.00 across all rungs.

### Query 4b — Where the savings come from, in full

```sql
SELECT
    CASE WHEN CommitmentDiscountId IS NOT NULL
         THEN 'commitment-covered' ELSE 'on-demand' END  AS coverage,
    BillingCurrency,
    COUNT(*)                                             AS row_count,
    ROUND(SUM(ListCost), 2)                              AS list_cost,
    ROUND(SUM(ContractedCost), 2)                        AS contracted_cost,
    ROUND(SUM(EffectiveCost), 2)                         AS effective_cost,
    ROUND(SUM(ListCost) - SUM(ContractedCost), 2)        AS negotiation_saving,
    ROUND(SUM(ContractedCost) - SUM(EffectiveCost), 2)   AS commitment_saving
FROM focus_unified
WHERE ChargeCategory = 'Usage'
  AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
  AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
GROUP BY 1, 2
ORDER BY BillingCurrency, coverage;
```

**What each piece does:**

- **`CASE WHEN CommitmentDiscountId IS NOT NULL`** — the split key:
  a row either sits under a commitment discount or it doesn't. This is
  an existence test on an Id column (is it populated?), not a join —
  rule 4's "join on Ids" concern doesn't arise.
- The two saving columns reuse the rung definitions, so 4b is the same
  ladder viewed sideways: sum 4b's negotiation_saving across coverage
  groups and you get rung 1 (1.20 + 2.52 = 3.72 ✓); sum
  commitment_saving and you get rung 2 (30.90 + 0.00 = 30.90 ✓).
- **The built-in expectation test:** on-demand rows must show
  contracted_cost = effective_cost (no commitment applies, so no
  commitment saving is possible). Verified: 37.10 = 37.10, saving 0.00.
  If that cell were ever nonzero, the data — not the query — would have
  a problem worth investigating.

**Verified result:** commitment-covered USD: 54 rows, 1.20 negotiation +
30.90 commitment; on-demand USD: 132 rows, 2.52 negotiation + 0.00
commitment; EUR on-demand flat.

### §5.1 audit for Chunk 4

| Rule | Verdict |
|---|---|
| 1 — Start column, half-open | ✅ ChargePeriodStart (consumption question, S1) in both |
| 2 — Right metric, labelled | ✅ All three cost columns named in full; savings columns named by rung |
| 3 — Category to one side before ListCost/ContractedCost | ✅ **The rule's home chunk**: `ChargeCategory = 'Usage'` before any List/Contracted sum, in both queries |
| 4 — Group Category / display Names / join Ids | ✅ Coverage split is an IS NOT NULL test on an Id, not a join; no Type grouping |
| 5 — Savings state their counterfactual | ✅ **The rule's other home**: `saved_compared_to` is an output column; headline labelled as rung 1 + rung 2, never independent |
| 6 — Currency; untagged visible; no sign | ✅ Currency in every GROUP BY; no sign predicates; (team view not in this chunk — ladder-by-team is a Looker pivot on 4b's pattern if wanted) |

New terms defined this chunk: NULL as a deliberate blank output column,
divide-by-zero guard, additive percentages (common denominator), the
ladder identity as arithmetic rather than reconciliation.

## Chunk 4 run instructions

Replace queries.sql; then `source .venv/bin/activate` (if needed) and
`python3 run_queries.py`.

Expected new output: QUERY 11 (= 4a: six rows — three rungs × two
currencies; USD saving column reads 3.72 / 30.90 / 34.62) and QUERY 12
(= 4b: three rows; on-demand commitment_saving exactly 0.00).

---

## §2a. Runner upgrade — version 2 (named headers + a real splitter)

Two changes to `run_queries.py`, both worth understanding:

1. **Named headers.** Results are now titled from the comment above each
   query ("QUERY 1a. CONSUMPTION SHOWBACK …") instead of a bare sequence
   number, so screenshots are self-explanatory and the off-by-one
   confusion (setup statement = old "QUERY 1") is gone.
2. **A real statement splitter — because the old one broke.** Version 1
   split the file on every semicolon after stripping comments. Chunk 5's
   SQL contains a semicolon *inside a quoted string* (in a verdict
   label), and v1 cut the statement in half there — a parser error
   before the query even reached DuckDB. The general lesson: **you
   cannot split SQL on ';' with find-and-replace logic**, because ';'
   means different things inside strings, inside comments, and outside
   both. v2 walks the file character by character, tracks whether it is
   currently inside a string ('' = escaped quote) or a comment (-- to
   end of line), and only treats ';' as a boundary outside both. Same
   family as the NULL-comparison and ''-vs-NULL traps: the *meaning* of
   a symbol depends on context, and tooling that ignores context fails
   quietly until it doesn't.

---

## §6. Chunk 5 — Block-pricing waste (Query 5)

### Plain-English summary

Some services bill in **blocks**: storage write operations priced per
1,000-operation block, tokens priced per million. FOCUS shows this as
two quantities — `ConsumedQuantity` (what you used, in your units) and
`PricingQuantity` (what you were charged for, in the *pricing* unit).
The July result: one genuine waste case — storage write operations,
2,000 consumed but **3.0 blocks charged**, one phantom block = 0.05 USD
at **66.7% block utilisation** — and three rows that a naive query would
have falsely accused.

### Stage 5 Finding S4 — quantity divergence has two causes; only one is waste

`PricingQuantity <> ConsumedQuantity` was true on 37 July rows, but for
two completely different reasons:

| Cause | Example | Waste? |
|---|---|---|
| **Unit conversion** | 1,500,000 Tokens priced as 1.5 "1M Tokens"; 186 Units priced as 0.0186 blocks-of-10,000 (exact division) | **No** — the columns speak different units |
| **Block rounding** | 2,000 Operations priced as 3.0 1K-blocks (should be 2.0) | **Yes** — 1 block paid, never used |

Waste is only assessable after restating consumption in the **pricing
unit** (via `x_PricingBlockSize`) and checking whether pricing rounded
up. This is §5.1 rule 6's "group by unit before aggregating" in its
sharpest form: comparing quantities across units isn't just imprecise,
it manufactures false findings. 35 of 37 rows would have been wrongly
flagged. Where the block size isn't recorded (the token row), the query
says "not assessable" rather than guessing — the same honesty rule as
Finding 6's "not evaluable" verdict on the 3-year reservation.

### Query 5 — in full

```sql
WITH divergent AS (
    SELECT
        ResourceName,
        ChargeDescription,
        BillingCurrency,
        PricingUnit,
        ConsumedUnit,
        x_PricingBlockSize,
        SUM(ConsumedQuantity)  AS consumed_qty_raw,
        SUM(PricingQuantity)   AS priced_qty_raw,
        SUM(EffectiveCost)     AS effective_cost_raw
    FROM focus_unified
    WHERE ChargeCategory = 'Usage'
      AND (ChargeClass IS NULL OR ChargeClass <> 'Correction')   -- Finding 5
      AND PricingQuantity IS NOT NULL AND ConsumedQuantity IS NOT NULL
      AND PricingQuantity <> ConsumedQuantity
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
    GROUP BY 1, 2, 3, 4, 5, 6
),
assessed AS (
    SELECT *,
        CASE WHEN x_PricingBlockSize IS NOT NULL AND x_PricingBlockSize <> 0
             THEN consumed_qty_raw / x_PricingBlockSize END AS consumed_in_pricing_units
    FROM divergent
)
SELECT
    ResourceName,
    ChargeDescription,
    BillingCurrency,
    consumed_qty_raw                                   AS consumed_quantity,
    ConsumedUnit                                       AS consumed_unit,
    priced_qty_raw                                     AS pricing_quantity,
    PricingUnit                                        AS pricing_unit,
    ROUND(consumed_in_pricing_units, 4)                AS consumed_in_pricing_units,
    ROUND(effective_cost_raw, 2)                       AS effective_cost_consumption,
    CASE
        WHEN consumed_in_pricing_units IS NULL
            THEN 'unit conversion — block size not recorded; waste not assessable'
        WHEN priced_qty_raw - consumed_in_pricing_units < 0.0001
            THEN 'unit rescaling only — exact division, no rounding waste'
        ELSE 'BLOCK ROUNDING WASTE'
    END                                                AS verdict,
    ROUND(priced_qty_raw - consumed_in_pricing_units, 4)             AS waste_blocks,
    ROUND((priced_qty_raw - consumed_in_pricing_units)
          * effective_cost_raw / NULLIF(priced_qty_raw, 0), 2)       AS waste_cost_effective,
    ROUND(100.0 * consumed_in_pricing_units / NULLIF(priced_qty_raw, 0), 1)
                                                       AS block_utilisation_pct
FROM assessed
ORDER BY (priced_qty_raw - consumed_in_pricing_units)
         * effective_cost_raw / NULLIF(priced_qty_raw, 0) DESC NULLS LAST;
```

**What each piece does:**

- **`divergent` CTE** — only rows where the two quantities disagree, on
  the Usage side, correction excluded **by category** (Finding 5: this
  is price × quantity territory, exactly what corrections are exempt
  from). Sums stay raw (S3).
- **`assessed` CTE** — the S4 restatement: consumption ÷ block size =
  consumption *in pricing units*. A `CASE` with no `ELSE` returns NULL
  when the block size is missing — and that NULL is meaningful: "cannot
  assess", carried honestly through the rest of the query.
- **The verdict `CASE`** — three honest outcomes, checked in order:
  block size unknown → *not assessable*; restated consumption equals
  the priced quantity (to a 0.0001 tolerance — never `=` on decimals
  after division) → *rescaling only*; otherwise → **waste**.
- **`NULLIF(priced_qty_raw, 0)`** — turns 0 into NULL so a division by
  zero becomes a NULL result instead of an error. Belt-and-braces
  cousin of Chunk 4's `WHERE list_raw <> 0` guard.
- **`waste_cost_effective`** — waste blocks × the effective unit price
  (effective_cost ÷ priced blocks): the money attached to blocks paid
  for and never used. Labelled per §5.1 rule 2.
- **`ORDER BY ... DESC NULLS LAST`** — most expensive waste first;
  `NULLS LAST` keeps the not-assessable row at the bottom instead of
  DuckDB's default of sorting NULLs first.

**Verified result:** write operations — **BLOCK ROUNDING WASTE**, 1.0
block, 0.05 USD, 66.7% utilisation · Blob and Files — rescaling only,
100.0% · tokens — not assessable. One true positive, zero false
accusations.

### §5.1 audit for Chunk 5

| Rule | Verdict |
|---|---|
| 1 — Start column, half-open | ✅ ChargePeriodStart (consumption question, S1) |
| 2 — Right metric, labelled | ✅ EffectiveCost, named `effective_cost_consumption`; waste column named for its basis |
| 3 — Category split before ListCost/ContractedCost | ✅ Vacuous (neither summed); Usage-side filter present anyway |
| 4 — Group Category / display Names / join Ids | ✅ Grouped on descriptive columns for display; no joins |
| 5 — Counterfactual labelling | ✅ The waste figure's counterfactual is stated by construction: vs paying only for restated consumption |
| 6 — Currency; units; no sign reasoning | ✅ **The rule's sharpest test**: currency in grouping AND quantities only compared after restatement into a common unit — S4 is rule 6 applied to quantities |

Findings check: 5 ✅ correction excluded by category · 7 ✅ no sign
predicates · S1 ✅ · S3 ✅ raw sums · **S4 established this chunk**.

New terms defined: NULLIF, CASE with no ELSE (meaningful NULL),
decimal-comparison tolerance, NULLS LAST.

## Chunk 5 run instructions

**This time replace BOTH `queries.sql` AND `run_queries.py`** (the
runner is v2 — named headers and the fixed splitter). Then:

```
source .venv/bin/activate
python3 run_queries.py
```

Expected: every result now carries a named header (QUERY 1a … QUERY 4b),
and the new final table "QUERY 5 — BLOCK-PRICING WASTE" shows four rows:
one BLOCK ROUNDING WASTE at 0.05 / 66.7%, two rescaling-only at 100.0%,
one not-assessable.

---

## §7. Chunk 6 — Commitment utilisation (Query 6)

### Plain-English summary

A reservation is pre-paid capacity: every day of its term it is either
**Used** (a workload ran on it) or **Unused** (paid for anyway).
Utilisation = Used ÷ (Used + Unused) — but only over the commitment's
**term**, which lives in Layer C's `contract_commitment`, not in the
cost data (Finding 6). The query therefore ends in a **verdict column
that refuses to answer when the window can't support the answer**:

| Commitment | Verdict | Why |
|---|---|---|
| res-basv2-1yr-001 | **utilisation 83.1%** — evaluable, term fully observed | Term 1 Jul → 1 Aug 2026 (31 days), 31 observed. Used 61.80 + Unused 12.60 = **74.40 = ContractCommitmentCost to the cent** — the handover's "closes exactly at 74.40" reproduced independently |
| res-basv2-3yr-upfront-001 | **NOT EVALUABLE** — 1 of 1,096 term days | Reporting a % here would measure export length, not performance — the exact trap Finding 6 names |
| res-basv2-legacy-2023 | **TERM UNKNOWN** — no contract record | LEFT JOIN found nothing; without a term there is no denominator |

**Honest data observation (recorded, not hidden):** the 1yr fixture's
*description* says "1-year reserved capacity" but its recorded term is
31 days (1 Jul → 1 Aug 2026). The query trusts the recorded term — the
spec-governed field — over the free-text label. Fixture-generation
quirk, worth a line in any handover; the labels lie, the period columns
don't.

### Query 6 — in full

```sql
WITH commitment_usage AS (
    SELECT
        CommitmentDiscountId,
        BillingCurrency,
        SUM(EffectiveCost) FILTER (WHERE CommitmentDiscountStatus = 'Used')
            AS used_effective_raw,
        SUM(EffectiveCost) FILTER (WHERE CommitmentDiscountStatus = 'Unused')
            AS unused_effective_raw,
        MIN(CAST(ChargePeriodStart AS DATE)) AS first_observed,
        MAX(CAST(ChargePeriodStart AS DATE)) AS last_observed,
        COUNT(DISTINCT CAST(ChargePeriodStart AS DATE)) AS days_observed
    FROM focus_unified
    WHERE CommitmentDiscountId IS NOT NULL
      AND ChargeCategory = 'Usage'
    GROUP BY 1, 2
),
with_term AS (
    SELECT
        cu.*,
        cc.ContractCommitmentDescription,
        cc.ContractCommitmentCost,
        CAST(cc.ContractCommitmentPeriodStart AS DATE) AS term_start,
        CAST(cc.ContractCommitmentPeriodEnd   AS DATE) AS term_end,
        DATE_DIFF('day',
                  CAST(cc.ContractCommitmentPeriodStart AS DATE),
                  CAST(cc.ContractCommitmentPeriodEnd   AS DATE)) AS term_days
    FROM commitment_usage cu
    LEFT JOIN contract_commitment cc
           ON cu.CommitmentDiscountId = cc.ContractCommitmentId
)
SELECT
    REGEXP_EXTRACT(CommitmentDiscountId, '[^/]+$')     AS commitment,
    ContractCommitmentDescription                       AS description,
    BillingCurrency,
    term_start, term_end, term_days,
    days_observed, first_observed, last_observed,
    ROUND(used_effective_raw, 2)                        AS used_effective,
    ROUND(unused_effective_raw, 2)                      AS unused_effective,
    ROUND(used_effective_raw + COALESCE(unused_effective_raw, 0), 2)
                                                        AS used_plus_unused,
    ContractCommitmentCost                              AS contract_commitment_cost,
    CASE
        WHEN term_days IS NULL
            THEN 'TERM UNKNOWN — no contract record, not evaluable'
        WHEN days_observed < term_days
            THEN 'NOT EVALUABLE — window covers '
                 || days_observed || ' of ' || term_days
                 || ' term days (would measure export length, not performance)'
        ELSE 'utilisation '
             || ROUND(100.0 * used_effective_raw
                      / NULLIF(used_effective_raw + COALESCE(unused_effective_raw, 0), 0), 1)
             || '% of term — evaluable, term fully observed'
    END                                                 AS verdict
FROM with_term
ORDER BY term_start NULLS LAST;
```

**What each piece does:**

- **`SUM(x) FILTER (WHERE ...)`** — the new idea of this chunk: a
  conditional sum. "Sum EffectiveCost, but only over rows where the
  status is Used." Two FILTERed sums in one pass replace two separate
  queries — and because both read the same rows, they can't drift apart.
- **`WHERE ... ChargeCategory = 'Usage'`** — Purchase rows are excluded
  from the utilisation maths: the purchase is the *payment for* the
  commitment, not its consumption. (Including it would double-count the
  commitment against itself — rule 3's logic in commitment form.)
- **`LEFT JOIN`** — "keep every row from the left side even when the
  right side has no match." An INNER JOIN would have silently *deleted*
  the legacy commitment — the term-unknown case would never appear. The
  LEFT JOIN keeps it, with NULLs where the contract fields would be, and
  the verdict CASE turns those NULLs into an explicit answer.
- **`ON cu.CommitmentDiscountId = cc.ContractCommitmentId`** — an
  Id-to-Id join, §5.1 rule 4 satisfied (and the Chunk 3 name-join
  exception stays the exception).
- **`DATE_DIFF('day', start, end)`** — the term length in days; with a
  half-open term (end = 1 Aug), this gives exactly 31 for July. The
  denominator Finding 6 demands.
- **`REGEXP_EXTRACT(id, '[^/]+$')`** — the Azure Id is a long path;
  this keeps everything after the last slash ("res-basv2-1yr-001") for
  display. Display names, join Ids — rule 4 in one line.
- **`||`** — string concatenation: the verdict sentence is assembled
  from live numbers, so the refusal message itself carries the evidence
  ("1 of 1096 term days").
- **`COALESCE(unused_effective_raw, 0)`** — the legacy commitment has
  Used rows but no Unused rows; without the COALESCE, Used + NULL = NULL
  and the total would vanish.
- **`NULLIF(..., 0)`** — divide-by-zero guard on the utilisation
  denominator, as in Chunk 5.

**Verified result:** the three-verdict table above, with used_plus_unused
= 74.40 tying contract_commitment_cost = 74.40 on the evaluable row.

### §5.1 audit for Chunk 6

| Rule | Verdict |
|---|---|
| 1 — Start column, half-open | ✅ No period filter needed (scope is per-commitment, bounded by term evaluation); date columns used only via Start |
| 2 — Right metric, labelled | ✅ EffectiveCost throughout, columns named used_/unused_effective; contract cost carried under its own name |
| 3 — Category to one side | ✅ Usage-only before any summing; Purchase explicitly excluded with the reason documented |
| 4 — Group Category / display Names / join Ids | ✅ **The rule's showcase**: join on Ids, display via REGEXP_EXTRACT'd name and description |
| 5 — Counterfactual labelling | ✅ N/A (no savings claim; utilisation labelled with its basis and window) |
| 6 — Currency; no sign reasoning | ✅ BillingCurrency grouped and displayed; status split by category (Used/Unused), never by sign |

Findings check: Finding 6 ✅ **executed in full** — term from Layer C,
refusal verdicts for short-window and missing-term cases · 7 ✅ ·
S3 ✅ raw sums, ROUND at display.

New terms defined: FILTER clause, LEFT JOIN vs INNER JOIN,
DATE_DIFF, REGEXP_EXTRACT, || concatenation.

## Chunk 6 run instructions

Replace `queries.sql` (runner unchanged from v2). **One path to set
before running** — the setup block now also creates a view over the
Layer C contract file. In the terminal:

```
find . -name "contract_commitment.csv"
```

then paste the printed path into the `read_csv('...')` line near the top
of queries.sql (same procedure as the Parquet in §2 — this is now a
practiced move). Then `python3 run_queries.py`.

Expected new final table "QUERY 6 — COMMITMENT UTILISATION": three rows,
three different verdicts — 83.1% evaluable (with 74.40 = 74.40),
NOT EVALUABLE 1-of-1096, TERM UNKNOWN.

---

## §8. Chunk 7a — Full-file §5.1 audit (and what it caught)

### The audit caught a real defect (Findings S5 and S6)

The Chunk 3 flag ("3b joins on ResourceName — revisit") was tested
against the data rather than waved through, and it turned out to be a
**defect, not a style point**:

- **S5 — names collide; Ids don't.** `ResourceName` is not unique:
  "vm-web-01" names **two different resources** — the *real* sandbox VM
  (all zero-cost rows) and a *synthetic* fixture (72.30 of spend). Ditto
  "stp1sandbox". Grouping the anomaly detection by name silently merged
  a real resource with its synthetic namesake — cross-layer
  contamination that distorted daily totals and the baseline. §5.1 rule
  4 ("group and join on Ids, display Names") exists precisely for this.
  **Fix:** both 3a and 3b now key on
  `COALESCE(ResourceId, ResourceName)` (the fallback covers 23 rows
  with no ResourceId), and ResourceName appears only as a display
  column via ANY_VALUE.
- **S6 — the baseline must be defined, not inherited.** Id-grouping
  surfaced 10 zero-cost resource-days that name-merging had hidden
  inside nonzero totals, which dragged the median from 0.60 to 0.28 and
  would have tripled the anomaly flags. Decision: **"typical" = the
  median of NONZERO resource-days** — zero-cost days are free-grain
  metering, not meaningful benchmarks for a spend anomaly. Zero days
  are still *scored* (a spike on a normally-free resource must still be
  flaggable); they are only excluded from the *baseline*. Implemented
  as `MEDIAN(x) FILTER (WHERE x <> 0)`.

Post-fix result: identical conclusion on a now-defensible basis —
fx-appliance-01 flagged at 30.0×, vm-web-01 at 9.0× unflagged, incident
record A1 unchanged. Two cosmetic differences vs the earlier run:
vm-web-prod-01 dropped out of the top-10 (its 3.6 day sits below
vm-web-01's Id-corrected 3.8), and tie ordering shuffles as always.

The Master v3 wording is "audit your own SQL against the rules line by
line" — this is what that instruction is for. The first pass produced
plausible numbers; the audit found they rested on a colliding key.
Same lesson as Stage 4's harness catching the seed data: **the audit
step is not ceremony.**

### The audit grid — every query × every rule (post-fix)

| Query | R1 period | R2 metric | R3 List/Contracted | R4 Ids/Names | R5 counterfactual | R6 currency/unit/sign |
|---|---|---|---|---|---|---|
| 1a | ✅ CPS | ✅ | n/a | ✅ | n/a | ✅ |
| 1b | ✅ BPS | ✅ | n/a | ✅ | n/a | ✅ |
| 1c | ✅ BPS | ✅ | n/a | ✅ | n/a | ✅ |
| 1d | ✅ both, on purpose | ✅ | n/a | ✅ | n/a | ✅ |
| 2a | ✅ CPS | ✅ | n/a | ✅ | n/a | ✅ |
| 2b | ✅ CPS | ✅ | n/a | ✅ | n/a | ✅ |
| 2c | ✅ CPS/BPS by metric | ✅ | n/a | ✅ | n/a | ✅ |
| 3a | ✅ CPS | ✅ | n/a | ✅ **fixed (S5)** | n/a | ✅ + S6 baseline |
| 3b | ✅ CPS | ✅ | n/a | ✅ **fixed (S5)** | n/a | ✅ |
| 4a | ✅ CPS | ✅ | ✅ Usage-only | ✅ | ✅ labelled column | ✅ additive % |
| 4b | ✅ CPS | ✅ | ✅ Usage-only | ✅ Id existence test | ✅ | ✅ |
| 5 | ✅ CPS | ✅ | ✅ | ✅ | ✅ by construction | ✅ **unit-restated (S4)** |
| 6 | ✅ term-scoped | ✅ | ✅ Purchase excluded | ✅ Id join, Name display | n/a | ✅ |

(CPS = ChargePeriodStart, BPS = BillingPeriodStart, per S1.)

**Verdict: the file passes.** No rule is satisfied "by exception" any
more — the one documented exception (3b) was eliminated by fixing the
underlying query.

---

## §9. Chunk 7b — Looker Studio design: the four persona views

Personas per Master v3 Stage 5: **Executive · Team showback · Anomaly ·
Budget vs actual.** One page each. Every chart title carries its cost
metric in brackets — a §5.1 rule 2 discipline carried into the visual
layer: nothing on any page is labelled just "Cost".

### Getting the data in (the plumbing)

Looker Studio cannot read the local Parquet. `export_for_looker.py`
runs every query and writes `exports/query_*.csv` (13 files). Two
connection options:

1. **Google Sheets (recommended)** — one spreadsheet, one tab per CSV,
   pasted or imported. Looker connects to the Sheet; re-running the
   exporter and re-pasting refreshes the dashboard. Fits the existing
   Drive-based storage.
2. **File upload** — quicker to start, but every refresh is a re-upload.

Either way: the dashboard reads **query results**, not the raw table —
so every §5.1 rule and Stage 4/5 finding is enforced *before* the data
reaches a chart, and Looker cannot un-enforce them.

### Page 1 — Executive: "are we healthy, and what did discounts earn?"

| Element | Source | Metric (in title) | Why this metric |
|---|---|---|---|
| Scorecard: July bill | 1c grand total | **BilledCost** | The cash number the invoice will show — 2,702.09 USD |
| Scorecard: July consumption | 1a total | **EffectiveCost** | The economics number — 113.90 USD; sits beside the bill to make the purchase distortion visible, not hidden |
| Bar: savings by rung | 4a | **savings vs labelled counterfactual** | Rule 5 on screen: each bar carries its `saved_compared_to` text — 3.72 negotiation + 30.90 commitment = 34.62 (23.3% of list) |
| Table: commitment verdicts | 6 | **EffectiveCost (Used/Unused)** | The verdict column verbatim — the dashboard *refuses* to show a utilisation % where the window can't support one |

The exec page's whole story: cash and economics are different questions;
here are both, labelled, with the savings claims carrying their
counterfactuals.

### Page 2 — Team showback: "who consumed what, and what isn't allocated?"

| Element | Source | Metric | Why |
|---|---|---|---|
| Stacked bar: consumption by team, per currency | 1a | **EffectiveCost** | The amortised allocation metric (rule 2); BilledCost would draw one reservation purchase |
| UNTAGGED highlighted (distinct colour + % of consumption) | 1a | **EffectiveCost** | The allocation gap surfaced, never dropped (rule 6) — 12.63 = 11% of USD consumption |
| Side panel: reconciling items | 1b | **BilledCost** | Billing events by category — cash metric because they are invoice events; keeps 2,702.40 of purchases out of the team chart |
| Footnote scorecards: tie-out | 1c | **BilledCost** | Usage + reconciling = bill, to the cent — proof nothing was dropped between panels |

Note for the data team's 0.00 row: display it. "Tagged and free" and
"untagged" are different states (§1).

### Page 3 — Anomaly: "did anything behave unlike everything else?"

| Element | Source | Metric | Why |
|---|---|---|---|
| Table: top resource-days, flag column conditionally formatted | 3a | **EffectiveCost** | Consumption is the trend question; and A1's punchline — 18.00 effective, 0.00 cash — means a BilledCost detector would have seen *nothing* |
| Incident card | 3b | **EffectiveCost + BilledCost, both labelled** | The evidence row: what, whose, when, both cost readings |
| Line: daily cost per resource, anomaly annotated | 3a export | **EffectiveCost** | The visual signature: flat population, one spike |
| Method note on-page | — | — | "Flag = ≥10× the median nonzero resource-day, same currency, keyed by ResourceId" — the threshold and basis stated where the reader looks (S5/S6) |

### Page 4 — Budget vs actual: "are we on plan?"

| Element | Source | Metric | Why |
|---|---|---|---|
| Gauge/scorecard: % of budget consumed | 2a | **EffectiveCost vs 20.00 USD budget** | 15.2% — consumption vs a consumption budget, real subscription only (S2) |
| Line: cumulative vs straight-line pace | 2b | **EffectiveCost** | The burn-down: 3.03 actual vs 20.00 pace; "days 1–21 = no data, not zero" noted on-page |
| Table: out-of-scope items | 2c | **per-row labelled metric** | What the budget comparison excluded and why — the S2 scope decision disclosed, not buried |

### Global design rules (all four pages)

1. Metric name in every chart title — never "Cost".
2. One currency per chart; a currency filter control at page level; EUR
   noted as synthetic-only.
3. Verdict/label columns from the SQL are displayed verbatim — the
   refusals (NOT EVALUABLE, not assessable) are content, not clutter.
4. Each page footer: source query id + "July 2026 · focus_unified ·
   Stage 5 query layer".

## Chunk 7 run instructions

Replace `queries.sql` (Chunk 3 carries the S5/S6 fix) and add
`export_for_looker.py` next to it. Then:

```
python3 run_queries.py        # confirm 3a/3b: same flag, new basis
python3 export_for_looker.py  # writes exports/ (13 CSVs)
```

Expected: 3a's median column is now named median_nonzero_resource_day,
fx-appliance-01 still the only ANOMALY at 30.0×; the exporter prints 13
file names. Next session: build the four Looker pages from §9.

## Open items

- [ ] Budget figure still assumed at 20.00 USD/month (one line, 2a + 2b).
- [ ] Looker build session (four pages per §9), then dashboard URL +
      screenshots into /docs per Master v3.
- [ ] GitHub publication session (carried from Stage 4; run
      publication_check.py last).

---

## §10. The Looker Studio dashboard — as built (29–31 Aug)

### Data plumbing

Thirteen Google Sheets in Drive, prefix `P1S5`, one per query result —
created directly from the query layer (CSV upload auto-converted to
native Sheets). The dashboard reads **query results only**, never raw
data: every §5.1 rule and every finding is enforced before a number
reaches a chart, and nothing in Looker can un-enforce them. Refresh
path: re-run `export_for_looker.py` → update the Sheets. Data is a
snapshot of the July dataset; adequate for Stage 5.

### The four persona pages, as built

**Page 1 — Team showback.** Consumption by team bar (1a,
EffectiveCost); reconciling items bar (1b, BilledCost — the Purchase
tower IS the Finding 4 picture); tie-out table (1c) showing both
identities: 17.25 + 2,684.84 = 2,702.09 and 187 + 5 = 192.
Report-level BillingCurrency control governs every page — the EUR view
is the control case (one 6.62 bar, empty reconciling panel, two-row
tie-out).

**Page 2 — Anomaly.** Detection table (3a) with conditional
formatting: flag = ANOMALY → red row; exactly one fires. Incident
record (3b). Scorecard pair: Anomaly cost — EffectiveCost **18** /
BilledCost **0**, captioned "a cash-based detector would have seen
nothing". Method note in full sentences (what the flag means and why —
not config shorthand).

**Page 3 — Budget vs actual.** Scorecards 15.2% / 3.03 / 16.97;
burn-down time series with two lines (cumulative vs straight-line pace
ending at 20.00); exclusions table (2c) = the S2 scope disclosure
on-page; notes for the budget assumption and the 22-July export start
("no data, not zero").

**Page 4 — Executive.** Cash-vs-economics scorecard pair: July bill
(BilledCost) 2,702.09 beside July consumption (EffectiveCost) 113.90 —
the purchase distortion displayed, not hidden. Savings ladder as
table-with-bars so each rung's `saved_compared_to` sentence travels
with its number (rule 5 in the visual layer): 3.72 / 30.90 / 34.62.
Commitment verdict table (6) with the refusal sentences verbatim.

Global rules held throughout: metric named in every chart title;
nothing labelled just "Cost"; one currency per view via the control;
verdicts and refusals displayed as content.

### Looker lessons learned (each cost a real fix)

1. **The Record Count trap.** Looker's automatic Record Count counts
   *Sheet rows per group* — on pre-aggregated query results that is
   always 1 and always wrong. Use the query's own columns
   (`row_count`). General rule: these Sheets are results, not raw data;
   their rows are already aggregates.
2. **"null" as text.** Empty values render as the word null. Style →
   Missing Data → Show blank. Blanks are honest; "null" reads as
   breakage.
3. **Filter on tokens, not labels.** `Equal to` on a long label with
   punctuation is fragile; `Contains "GRAND"` is sturdy. Same principle
   as rule 4: labels are for humans, matching wants short and stable.
   (And an unselected currency control passes ALL currencies — the
   2,708.71 vs 2,702.09 moment. The control is part of the number.)
4. **Time series need Date-typed fields.** Text-that-looks-like-a-date
   draws nothing; fix the field type in Manage added data sources.
5. **Report-level controls.** Right-click a control → Make
   report-level = one currency control governing every page.
6. **Data freshness is cached** (~15 min default); the toolbar refresh
   forces it. Slow updates are the cache, not an error.

### Stage 5 close-out checklist

- [ ] Ladder bars show their numbers; verdict-table nulls blanked;
      stray quote removed from the Executive footnote
- [ ] View-mode walk of all four pages with USD selected (then EUR once,
      as the control case)
- [ ] Share → get link → viewer access → **dashboard URL into /docs**
- [ ] **Screenshot each of the four pages into /docs** (Master v3
      Stage 5 deliverable: dashboard URL + screenshots)
- [ ] Budget figure: still the flagged $20 assumption — confirm before
      the Amsterdam deck quotes it
- [ ] Then Stage 5 = COMPLETE; GitHub publication session remains the
      carried open item (run publication_check.py last, per Stage 4
      handover)

---

## §11. EUR control-case observations (31 Aug) and completion

Three behaviours confirmed in the EUR captures, recorded so nobody
"fixes" them later:

1. **Correct emptiness.** Anomaly page: no data (no EUR anomalies
   exist). Executive: flat zero ladder, "No data" commitment table (no
   EUR commitments). Team showback: one 6.62 bar, two-row tie-out. A
   dashboard that knows when to show nothing is evidence the scoping
   works.
2. **The Budget page does not react to the currency control — by
   design.** Queries 2a/2b carry no BillingCurrency column: the budget
   comparison is USD-scoped inside the SQL (finding S2), so the control
   passes those charts through unchanged. The exclusions table (2c)
   does react, showing the EUR exclusion row under EUR.
3. **Chart titles are static.** They name the default USD view even
   when the control shows EUR. Cosmetic limitation of Looker text;
   the EUR screenshot is filed as a labelled control case.

### STAGE 5: COMPLETE — 31 August 2026

Delivered: thirteen §5.1-audited queries (zero exceptions after the
Chunk 7 audit fix); findings S1–S6; anomaly incident record A1;
runner v2 and Looker exporter; thirteen P1S5 Sheets; the four-persona
Looker Studio dashboard, published with viewer link; dashboard URL
document and page captures (USD set + EUR control case) for /docs.

Final ticks completed by Nakita: incognito link verification and filing
the captures + p1s5-dashboard-url.md into docs/dashboard/.

Carried out of Stage 5: **GitHub publication session** (run
publication_check.py last — Stage 4 handover §Open items) and the
**$20 budget figure confirmation** (still a flagged assumption in
queries 2a/2b and on the dashboard; confirm before Amsterdam quotes it).
