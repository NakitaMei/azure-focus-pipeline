-- ============================================================================
-- queries.sql — Project 1, Stage 5 query layer
-- Engine: DuckDB · Source: focus_unified (Stage 4 output, D3-normalised)
-- Governed by Master v3 §5.1 standing rules and the seven Stage 4 findings.
-- Built chunk by chunk; this file currently contains Chunk 1 (Query 1a–1d).
-- ============================================================================

-- Setup: parquet path confirmed against the repo on 20 Aug.
CREATE OR REPLACE VIEW focus_unified AS
SELECT * FROM read_parquet('data/unified/focus_unified.snappy.parquet');

-- Layer C (Chunk 6): path confirmed against the repo on 25 Aug
-- (find . -name "contract_commitment.csv").
CREATE OR REPLACE VIEW contract_commitment AS
SELECT * FROM read_csv('./data/supplemental/contract_commitment.csv');

-- ============================================================================
-- QUERY 1 — SHOWBACK BY TEAM
-- Metrics: EffectiveCost (consumption panel) / BilledCost (reconciling +
-- tie-out panels). No panel is named just "Cost" (§5.1 rule 2).
--
-- PERIOD COLUMN DECISION (Stage 5 finding — the Correction row):
--   The Correction has ChargePeriodStart = 14 June (it corrects June
--   consumption) but BillingPeriodStart = July (it sits on July's bill,
--   matching invoice_detail INV-2026-07-0001-002 = -1.85).
--   §5.1 rule 1 fixes HOW to filter (Start column, half-open) but the
--   QUESTION fixes WHICH Start:
--     · consumption questions  → ChargePeriodStart  (1a)
--     · bill/cash questions    → BillingPeriodStart (1b, 1c)
--   Query 1d proves the two scopes differ by exactly that one row.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1a. CONSUMPTION SHOWBACK — "what did each team's July consumption cost?"
-- Metric: EffectiveCost (amortised consumption cost — the allocation metric).
-- Scope: ChargeCategory = 'Usage', ChargePeriodStart in July.
-- Finding 1: team from the PARSED tag, never the raw Tags string.
-- Finding 2: UNTAGGED surfaced via COALESCE at the presentation layer
--            (§5.1 rule 6). x_CostCenter is NOT used — empty in every era.
-- Finding 3: BillingCurrency in the GROUP BY — never sum across currencies.
-- Finding 7: no sign filters — the rebate row stays in.
-- ----------------------------------------------------------------------------
SELECT
    COALESCE(json_extract_string(Tags, '$.team'), 'UNTAGGED') AS team,
    BillingCurrency,
    COUNT(*)                     AS row_count,
    ROUND(SUM(EffectiveCost), 2) AS effective_cost_consumption
FROM focus_unified
WHERE ChargeCategory = 'Usage'
  AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
  AND ChargePeriodStart <  TIMESTAMP '2026-08-01'   -- §5.1 rule 1
GROUP BY 1, 2
ORDER BY BillingCurrency, effective_cost_consumption DESC;

-- ----------------------------------------------------------------------------
-- 1b. RECONCILING ITEMS PANEL — "what sits on July's bill besides consumption?"
-- Metric: BilledCost (cash metric — these are billing events, not workloads).
-- Scope: ChargeCategory <> 'Usage', BillingPeriodStart in July (bill view).
-- Finding 4: the two Purchase rows (2,702.40 — 99% of BilledCost) land
--            here, which is exactly why this panel exists. The 4 untagged
--            non-Usage rows belong here by ChargeCategory, not in the
--            UNTAGGED consumption bucket.
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- 1c. COMPLETENESS TIE-OUT — proves the July BILL is fully accounted for.
-- Both sides in BilledCost (the only metric that sums to the bill), per
-- currency, filtered on BillingPeriodStart. usage_side + reconciling_side
-- must equal grand_total to the cent; row counts must sum likewise.
-- Finding 7: no sign filters — the -1.85 correction and the rebate sit
-- inside usage_side, the -25.00 credit inside reconciling_side.
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- 1d. BRIDGE — rows on July's bill whose consumption is NOT July (and vice
-- versa). Expected result: exactly one row — the Correction. This is the
-- documented explanation for why 1a's scope and 1c's usage side differ
-- by -1.85 and one row.
-- ----------------------------------------------------------------------------
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

-- ============================================================================
-- QUERY 2 — BUDGET VS ACTUAL
-- Metric: EffectiveCost (consumption vs a consumption budget), labelled.
--
-- BUDGET ASSUMPTION (flagged, one-line change if wrong): the Stage 1 Azure
-- budget — 20.00 USD per calendar month, set on the REAL sandbox
-- subscription.
--
-- SCOPE DECISION (Stage 5 finding S2): a budget comparison must scope to
-- the budget's subject. The $20 budget governs the real subscription
-- (x_Synthetic = FALSE, 118 rows, all Usage). The synthetic layer was
-- never inside its scope — including it reports a 570% "blowout" that is
-- an artefact of dataset design, not subscription health. Same trap shape
-- as Finding 6. Everything excluded is shown in 2c, not silently dropped.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2a. BUDGET VS ACTUAL — July, real subscription, USD.
-- The budget lives in a one-row CTE so the figure exists in exactly one
-- place and is labelled as an assumption.
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- 2b. DAILY BURN-DOWN — cumulative consumption vs straight-line pace.
-- New idea: a WINDOW FUNCTION. SUM(...) OVER (ORDER BY day) is a running
-- total: each row shows the sum of everything up to and including that day.
-- straight_line_pace = the budget spread evenly across 31 days — the "on
-- track" line for the dashboard. Note: the real export starts 22 July, so
-- the curve starts there; days 1–21 have no data, not zero consumption.
-- ----------------------------------------------------------------------------
WITH budget AS (
    SELECT 20.00 AS monthly_budget_usd
),
daily AS (
    SELECT
        CAST(ChargePeriodStart AS DATE)     AS day,
        SUM(EffectiveCost)                  AS effective_cost_day_raw
        -- NOT rounded here: round for display only, never before summing.
        -- Rounding each day first then summing added three phantom cents
        -- (nine days of 0.325 -> 0.33). Caught in testing, 20 Aug.
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
    ROUND(monthly_budget_usd * DAY(day) / 31.0, 2)        AS straight_line_pace,
    ROUND(100.0 * SUM(effective_cost_day_raw) OVER (ORDER BY day)
                / monthly_budget_usd, 1)                  AS cumulative_pct_of_budget
FROM daily, budget
ORDER BY day;

-- ----------------------------------------------------------------------------
-- 2c. OUT-OF-SCOPE PANEL — everything the budget comparison excluded, and
-- why. Nothing is silently dropped (tie-out philosophy from 1c).
-- Consumption rows shown in EffectiveCost; billing events in BilledCost;
-- metric named per §5.1 rule 2, so the two are never summed together.
-- ----------------------------------------------------------------------------
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

-- ============================================================================
-- QUERY 3 — ANOMALY LOG
-- Metric: EffectiveCost (consumption trend question), labelled.
--
-- Method: each RESOURCE-day is compared against the population median
-- NONZERO resource-day in the same currency, and flagged at >= 10x.
--
-- Two Chunk 7 audit fixes (findings S5 and S6):
--   S5 IDENTITY: resources are keyed by ResourceId, not ResourceName —
--      ResourceName collides ("vm-web-01" names BOTH the real sandbox VM
--      and a synthetic fixture; name-grouping merged them). Ids group and
--      join; names display (§5.1 rule 4). COALESCE to name only for the
--      23 rows with no ResourceId.
--   S6 BASELINE: "typical" = median of NONZERO resource-days. Zero-cost
--      days (free-grain metering) are still scored, but a day that costs
--      nothing is not a meaningful benchmark for a spend anomaly.
--
-- Corrections are excluded BY CATEGORY (ChargeClass), not by sign
-- (Finding 7): a correction restates another period's consumption.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3a. DETECTION — every resource-day vs the median nonzero resource-day,
-- top 10.
-- ----------------------------------------------------------------------------
WITH resource_day AS (
    SELECT
        COALESCE(ResourceId, ResourceName)  AS resource_key,   -- S5: Ids group
        ANY_VALUE(ResourceName)             AS resource_name,  -- names display
        BillingCurrency,
        CAST(ChargePeriodStart AS DATE)     AS day,
        SUM(EffectiveCost)                  AS effective_cost_day_raw
    FROM focus_unified
    WHERE ChargeCategory = 'Usage'
      AND (ChargeClass IS NULL OR ChargeClass <> 'Correction')
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
    GROUP BY 1, 3, 4
),
typical AS (
    SELECT BillingCurrency,
           MEDIAN(effective_cost_day_raw)
               FILTER (WHERE effective_cost_day_raw <> 0)      -- S6 baseline
               AS median_nonzero_resource_day
    FROM resource_day
    GROUP BY 1
)
SELECT
    rd.resource_name,
    rd.BillingCurrency,
    rd.day,
    ROUND(rd.effective_cost_day_raw, 2)                        AS effective_cost_day,
    ROUND(t.median_nonzero_resource_day, 2)                    AS median_nonzero_resource_day,
    ROUND(rd.effective_cost_day_raw / t.median_nonzero_resource_day, 1)
                                                               AS multiple_of_median,
    CASE WHEN rd.effective_cost_day_raw >= 10 * t.median_nonzero_resource_day
         THEN 'ANOMALY' ELSE '' END                            AS flag
FROM resource_day rd
JOIN typical t USING (BillingCurrency)
ORDER BY rd.effective_cost_day_raw / t.median_nonzero_resource_day DESC
LIMIT 10;

-- ----------------------------------------------------------------------------
-- 3b. INCIDENT RECORD — the evidence row for every flagged resource:
-- what it is, who owns it, when it lived, what it cost. Keyed by
-- ResourceId (S5); the narrative half lives in the working notes (A1).
-- ----------------------------------------------------------------------------
WITH resource_day AS (
    SELECT
        COALESCE(ResourceId, ResourceName)  AS resource_key,
        BillingCurrency,
        CAST(ChargePeriodStart AS DATE)     AS day,
        SUM(EffectiveCost)                  AS effective_cost_day_raw
    FROM focus_unified
    WHERE ChargeCategory = 'Usage'
      AND (ChargeClass IS NULL OR ChargeClass <> 'Correction')
      AND ChargePeriodStart >= TIMESTAMP '2026-07-01'
      AND ChargePeriodStart <  TIMESTAMP '2026-08-01'
    GROUP BY 1, 2, 3
),
typical AS (
    SELECT BillingCurrency,
           MEDIAN(effective_cost_day_raw)
               FILTER (WHERE effective_cost_day_raw <> 0)
               AS median_nonzero_resource_day
    FROM resource_day GROUP BY 1
),
flagged AS (
    SELECT DISTINCT rd.resource_key
    FROM resource_day rd
    JOIN typical t USING (BillingCurrency)
    WHERE rd.effective_cost_day_raw >= 10 * t.median_nonzero_resource_day
)
SELECT
    ANY_VALUE(u.ResourceName)                             AS resource_name,
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
JOIN focus_unified u
  ON COALESCE(u.ResourceId, u.ResourceName) = f.resource_key   -- S5: join on Ids
WHERE u.ChargeCategory = 'Usage'
GROUP BY f.resource_key, u.BillingCurrency;

-- ============================================================================
-- QUERY 4 — THE SAVINGS LADDER
-- §5.1 rule 5 made executable: every savings number states its
-- counterfactual. The three rungs:
--   negotiation = ListCost - ContractedCost   (vs paying the public list price)
--   commitment  = ContractedCost - EffectiveCost (vs paying negotiated rate on demand)
--   headline    = ListCost - EffectiveCost    (= the sum of the two rungs, never
--                                              an independent third claim)
-- §5.1 rule 3: ListCost/ContractedCost summed ONLY on the Usage side.
-- S3: sums stay raw; ROUND only at display.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4a. THE LADDER — three labelled rungs per currency.
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- 4b. WHERE THE SAVINGS COME FROM — the ladder split by commitment coverage.
-- Expectation this makes visible: on-demand rows have contracted = effective
-- (commitment savings exist only where commitments apply); negotiation
-- savings can exist on both sides.
-- ----------------------------------------------------------------------------
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

-- ============================================================================
-- QUERY 5 — BLOCK-PRICING WASTE
-- Metric: EffectiveCost (consumption question), labelled.
--
-- Finding S4: PricingQuantity <> ConsumedQuantity has TWO causes and only
-- one is waste. (1) Unit conversion: consumed in Tokens, priced in "1M
-- Tokens" — different units, nothing wasted. (2) Block rounding: consumed
-- 2,000 operations, priced per 1K block, charged 3.0 blocks — one block
-- paid and never used. Waste is only assessable after converting both
-- quantities into the SAME unit (§5.1 rule 6), using x_PricingBlockSize.
--
-- Finding 5 guard: this is unit economics (price x quantity), so the
-- Correction row is excluded BY CATEGORY.
-- ----------------------------------------------------------------------------
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
        -- consumed quantity restated in PRICING units (blocks), where the
        -- block size is recorded; NULL = not assessable in this dataset
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

-- ============================================================================
-- QUERY 6 — COMMITMENT UTILISATION
-- Metric: EffectiveCost (Used vs Unused split), labelled.
--
-- Finding 6 made executable: utilisation is only meaningful over the
-- commitment's TERM, and the term lives in Layer C (contract_commitment),
-- not in the cost data. The verdict column refuses to report a
-- utilisation percentage when the observed window cannot support it:
--   · no contract record            -> TERM UNKNOWN, not evaluable
--   · window << term                -> NOT EVALUABLE (measures export
--                                      length, not performance)
--   · term fully observed           -> utilisation reported, and the
--                                      Used+Unused total tied to the
--                                      ContractCommitmentCost
-- Join: cost.CommitmentDiscountId = contract.ContractCommitmentId — an
-- Id-to-Id join (§5.1 rule 4). Purchase rows are excluded from the
-- utilisation maths: they are the payment for the commitment, not its
-- consumption.
-- ----------------------------------------------------------------------------
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
    -- the Id's tail is enough to identify the reservation on a dashboard
    REGEXP_EXTRACT(CommitmentDiscountId, '[^/]+$')     AS commitment,
    ContractCommitmentDescription                       AS description,
    BillingCurrency,
    term_start,
    term_end,
    term_days,
    days_observed,
    first_observed,
    last_observed,
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
