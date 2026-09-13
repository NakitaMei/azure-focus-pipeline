-- ============================================================================
-- stage7_queries.sql — Stage 7 analysis queries, one file, one section per chunk
-- Run everything:   duckdb < stage7_queries.sql   (from the repo root; sections print in order)
-- Standing rules bind every query: S1–S7 (S7: period comparisons at civil-date
-- grain) and master §5.1 (Start-only half-open filters; currency filtered or
-- grouped; ChargeCategory pinned to one side; BilledCost for invoice questions,
-- labelled; x_ columns for provider drill-down only; no reasoning from sign).
-- ============================================================================

-- ---- SOURCE SETUP — edit paths HERE ONLY -----------------------------------
-- Relative to the repo root. data/stage7/ holds the SANITISED copies of the
-- August and September real exports (subscription and billing-account ids
-- replaced by stable pseudonyms — see sanitise_stage7.py). They are kept apart
-- from data/raw-sanitised/ on purpose: validate.py discovers that folder as the
-- validated real layer, and these files are reconciled here, not validated.
CREATE OR REPLACE VIEW aug_focus AS
  SELECT * FROM read_parquet('data/stage7/ai.aug.part_0_0001.snappy.parquet');

-- September 1.0r2 file: holds the VM/scheduling rows for chunk 4 AND, since the
-- 08 Sep re-download, batch 2's AI rows (charge date 07 Sep). Every scheduling
-- query below therefore carries a date ceiling (< 07 Sep) and an AI-resource
-- exclusion, so the VM-only figures cannot absorb token spend.
CREATE OR REPLACE VIEW sep_focus AS
  SELECT * FROM read_parquet('data/stage7/ai.sept.part_0_0001.snappy.parquet');

-- The AI resource's rows (filters shared by C2/C3; period filters stay in queries)
CREATE OR REPLACE VIEW ai_rows_aug AS
  SELECT * FROM aug_focus
  WHERE ResourceId ILIKE '%nakitameiring-6066-resource%'
    AND ChargeCategory = 'Usage'
    AND BillingCurrency = 'USD';

-- The VM/scheduling rows for chunk 4: September, 1–6 Sep only (the documented
-- scheduled window), AI resource excluded. One place, so C4a/C4b/C4c agree.
CREATE OR REPLACE VIEW vm_rows_sep AS
  SELECT * FROM sep_focus
  WHERE BillingCurrency = 'USD'
    AND ChargeCategory  = 'Usage'
    AND ResourceId NOT ILIKE '%nakitameiring-6066-resource%'
    AND ChargePeriodStart >= DATE '2026-09-01'
    AND ChargePeriodStart <  DATE '2026-09-07';   -- ceiling: batch 2 landed on 07 Sep

-- S7 note: ChargePeriodStart in these Azure files is a timezone-naive UTC
-- timestamp, so CAST(... AS DATE) and dayofweek() read the civil date as written
-- with no session-timezone arithmetic. Same answer in Cape Town and Berlin.

-- ============================================================================
SELECT '=== C2 · TOKEN RECONCILIATION — export side (vs token_generation_log.csv) ===' AS section;
-- ============================================================================
SELECT CAST(ChargePeriodStart AS DATE) AS charge_date,
       x_SkuMeterName                  AS meter,
       SUM(ConsumedQuantity)           AS tokens,
       SUM(PricingQuantity)            AS pricing_qty_1k,
       ROUND(SUM(BilledCost), 6)       AS billed_usd
FROM ai_rows_aug
WHERE ChargePeriodStart >= DATE '2026-08-01'
  AND ChargePeriodStart <  DATE '2026-09-01'
GROUP BY 1, 2
ORDER BY 1, 2;
-- Expected: 2026-08-31 · Inp 19,200 / 0.000960 · Outp 1,403,791 / 0.280758.
-- CSV side: 19,200 + 1,403,791 = 1,422,991 tokens · $0.281718 → EXACT tie.

SELECT '=== C2b · TOKEN RECONCILIATION — batch 2 (September file) ===' AS section;
SELECT CAST(ChargePeriodStart AS DATE) AS charge_date,
       x_SkuMeterName                  AS meter,
       SUM(ConsumedQuantity)           AS tokens,
       SUM(PricingQuantity)            AS pricing_qty_1k,
       ROUND(SUM(BilledCost), 6)       AS billed_usd
FROM sep_focus
WHERE ResourceId ILIKE '%nakitameiring-6066-resource%'
  AND ChargeCategory = 'Usage'
  AND BillingCurrency = 'USD'
  AND ChargePeriodStart >= DATE '2026-09-01'
  AND ChargePeriodStart <  DATE '2026-10-01'
GROUP BY 1, 2
ORDER BY 1, 2;
-- Expected: 2026-09-07 · Inp 19,200 / 0.000960 · Outp 1,397,963 / 0.279593.
-- CSV side: 1,417,163 tokens · $0.280553 → second EXACT tie (verified 8 Sep).

-- ============================================================================
SELECT '=== C3 · UNIT ECONOMICS — Finance vs Engineering view + interactive counterfactual ===' AS section;
-- ============================================================================
-- Interactive (Global Standard) rates used for the counterfactual column:
-- $0.10 per 1M input tokens, $0.40 per 1M output tokens — the Global Standard
-- list rate as displayed on the Azure OpenAI deployment blade, 31 Aug 2026
-- (screenshots/stage7-kickoff/01-openai-deploy-blade-batch-50pct-quota-2m.png), where
-- Global Batch is described as "50% less cost than Global Standard". The
-- measured batch rates ($0.05 / $0.20) are consistent with that.
WITH ai AS (
  SELECT x_SkuMeterName AS meter,
         SUM(ConsumedQuantity) AS tokens,
         SUM(PricingQuantity)  AS qty_1k,
         SUM(BilledCost)       AS billed
  FROM ai_rows_aug
  WHERE ChargePeriodStart >= DATE '2026-08-01'
    AND ChargePeriodStart <  DATE '2026-09-01'
  GROUP BY 1
)
SELECT meter, tokens,
       ROUND(billed, 6)                 AS billed_usd,
       ROUND(billed / qty_1k, 6)        AS finance_usd_per_1k,     -- PricingQuantity denominator
       ROUND(billed / tokens * 1000, 6) AS engineering_usd_per_1k, -- consumption denominator
       CASE WHEN qty_1k * 1000 = tokens THEN 'coincide (no block rounding)'
            ELSE 'DIVERGE - pricing structure' END AS views,
       ROUND(tokens / 1000000.0 *
         CASE WHEN meter ILIKE '%Inp%' THEN 0.10 ELSE 0.40 END, 6) AS interactive_counterfactual_usd
FROM ai
UNION ALL
SELECT 'TOTAL', SUM(tokens), ROUND(SUM(billed),6),
       ROUND(SUM(billed)/SUM(qty_1k),6),
       ROUND(SUM(billed)/SUM(tokens)*1000,6),
       'blended = mix statement (98.65% output)',
       ROUND(SUM(tokens / 1000000.0 *
         CASE WHEN meter ILIKE '%Inp%' THEN 0.10 ELSE 0.40 END),6)
FROM ai
ORDER BY meter;
-- Counterfactual caveats travel with any use of the last column: rate
-- comparison only (interactive quota was zero — F-K3); batch completed in
-- 6–9 min against the 24h window; batch is a buying mode, not just a discount.

-- ============================================================================
SELECT '=== C4a · SCHEDULING — baseline vs scheduled, billed per day ===' AS section;
-- ============================================================================
-- Per-day divisor = days actually present in the data, not a hard-coded
-- calendar count: missing days are not zero days (F-K1 lesson). The days
-- column is shown so the reader can see the divisor.
SELECT 'Aug 1-21 baseline (24/7)'                      AS period,
       COUNT(DISTINCT CAST(ChargePeriodStart AS DATE)) AS days_in_data,
       ROUND(SUM(BilledCost),4)                        AS total_usd,
       ROUND(SUM(BilledCost)
             / COUNT(DISTINCT CAST(ChargePeriodStart AS DATE)),4) AS per_day
FROM aug_focus
WHERE ChargePeriodStart >= DATE '2026-08-01' AND ChargePeriodStart < DATE '2026-08-22'
  AND BillingCurrency='USD' AND ChargeCategory='Usage'
UNION ALL
SELECT 'Sep 1-6 scheduled (PAYG)',
       COUNT(DISTINCT CAST(ChargePeriodStart AS DATE)),
       ROUND(SUM(BilledCost),4),
       ROUND(SUM(BilledCost)
             / COUNT(DISTINCT CAST(ChargePeriodStart AS DATE)),4)
FROM vm_rows_sep;
-- Expected: 0.3275/day vs 0.3344/day — the schedule moved billed cost ~nothing.
-- If days_in_data is not 21 and 6, the per-day figure changes and that is a
-- finding to record, not a divisor to force.

-- ============================================================================
SELECT '=== C4b · SCHEDULING — the Fri/Sat exhibit + daily detail ===' AS section;
-- ============================================================================
SELECT CAST(ChargePeriodStart AS DATE) AS d,                      -- civil date, S7
       CASE WHEN dayofweek(ChargePeriodStart) IN (0,6) THEN 'weekend (VM off all day)'
            ELSE 'weekday' END          AS day_type,
       COUNT(*)                          AS rows_emitted,
       ROUND(SUM(BilledCost),4)          AS billed_usd
FROM vm_rows_sep
GROUP BY 1,2 ORDER BY 1;
-- Expected: Fri 4 Sep 0.3344 vs Sat 5 Sep 0.3344 — identical to the cent with
-- the VM deallocated all Saturday. Row counts DO drop (13-14 -> 10): activity
-- changed, money didn't. Sep 6 read 0.2837 on the 7 Sep pull (last-day
-- provisionality) and settled to 0.3344 on the 8 Sep pull — flagged then,
-- resolved now, both kept on the record.

-- ============================================================================
SELECT '=== C4c · SCHEDULING — meter anatomy: the floor is 100% of cost ===' AS section;
-- ============================================================================
-- No HAVING filter: every meter is listed, including the ones that bill 0.0000.
-- The $0.00 compute meter appearing on its own line IS the exhibit — and a
-- HAVING on the sign of BilledCost would breach §5.1 (never reason from sign).
SELECT src.period, ServiceName, ChargeDescription,
       COUNT(*)                 AS rows_,
       ROUND(SUM(BilledCost),4) AS billed_usd
FROM (SELECT 'aug' AS period, * FROM aug_focus
      WHERE ChargePeriodStart >= DATE '2026-08-01' AND ChargePeriodStart < DATE '2026-08-22'
        AND BillingCurrency='USD' AND ChargeCategory='Usage'
      UNION ALL
      SELECT 'sep', * FROM vm_rows_sep) src
GROUP BY 1,2,3
ORDER BY 1, billed_usd DESC, 2, 3;
-- Expected: Premium SSD Managed Disks + IP Address carry all the cost in both
-- periods; the B-series compute meter and any other free-grain meters show at
-- 0.0000. Verified 9 Sep: Basv2 rows 21 of 21 Aug days but 4 of 6 Sep days —
-- the compute meter is not emitted at all on deallocated days; and the
-- Automation account's own meter (Process Automation) bills 0.0000. No compute meter bills: the 12-month free 750 B-series hrs/mo absorbs
-- it (independent of the expired $200 credit). Scheduling is a compute lever;
-- compute costs $0.00 today -> measured saving $0.00. Counterfactual: 70.2% of
-- compute-hours off (118 of 168 per week), ≈70% of compute cost at PAYG rates;
-- disk and IP untouched in every scenario.

-- ============================================================================
-- C5 · (autoscale — screenshot deliverable, no SQL)
-- C6 · (governance note — no SQL)
-- ============================================================================
