-- ============================================================================
-- STAGE 6 · CHUNK 1 — THREE-WAY RECONCILIATION
-- Cost & Usage  <->  Invoice Detail  <->  Billing Period
--
-- Standing rules honoured: S1 (bill questions filter BillingPeriodStart),
-- S3 (round for display only), S5 (join on Ids), §5.1 (group by
-- BillingCurrency before aggregating; never reason from sign).
-- Amendment A3.2 assertions 1, 2, 3 are exercised here.
-- ============================================================================

-- ---- Source registration (adjust paths if `find` shows different ones) ----
CREATE OR REPLACE VIEW cu AS
  SELECT * FROM read_parquet('data/unified/focus_unified.snappy.parquet');
CREATE OR REPLACE VIEW inv AS
  SELECT * FROM read_csv_auto('data/supplemental/invoice_detail.csv');
-- billing_period.csv carries timezone-aware timestamps (+02:00) while the
-- cost data's period columns are timezone-naive (finding S7). Any comparison
-- that lets the session timezone interpret either side gives verdicts that
-- depend on the analyst's laptop: raw equality fails on SAST and passes on
-- UTC; even CAST(tz AS DATE) shifts a day west of Greenwich. The invariant
-- read: take the period columns as TEXT and keep the civil date AS WRITTEN -
-- no timezone arithmetic anywhere. Same answer in Cape Town, Berlin, Sydney
-- and New York. (Roadmap: generate_layer_c should write plain dates.)
CREATE OR REPLACE VIEW bp AS
  SELECT CAST(substr(BillingPeriodStart, 1, 10) AS DATE) AS BillingPeriodStart,
         CAST(substr(BillingPeriodEnd,   1, 10) AS DATE) AS BillingPeriodEnd,
         BillingPeriodStatus, InvoiceIssuerName
  FROM read_csv_auto('data/supplemental/billing_period.csv',
                     types={'BillingPeriodStart': 'VARCHAR',
                            'BillingPeriodEnd':   'VARCHAR'});

-- ============================================================================
-- Q1 · THE TIE-OUT — A3.2 assertion 1 (HARD)
-- Per invoice, per currency: SUM(BilledCost) in Cost & Usage must equal the
-- invoice total in invoice_detail, to the cent. Sum first, round for display.
-- ============================================================================
WITH cu_by_invoice AS (
  SELECT InvoiceId, BillingCurrency,
         SUM(BilledCost)  AS cu_billed_total,
         COUNT(*)         AS cu_row_count
  FROM cu
  WHERE InvoiceId IS NOT NULL
  GROUP BY InvoiceId, BillingCurrency
),
inv_totals AS (
  SELECT InvoiceId, BillingCurrency,
         SUM(BilledCost)  AS invoice_total,
         COUNT(*)         AS invoice_line_count
  FROM inv
  GROUP BY InvoiceId, BillingCurrency
)
SELECT
  COALESCE(c.InvoiceId, i.InvoiceId)              AS InvoiceId,
  COALESCE(c.BillingCurrency, i.BillingCurrency)  AS Currency,
  ROUND(i.invoice_total, 2)                       AS InvoiceTotal,
  ROUND(c.cu_billed_total, 2)                     AS CostUsageBilled,
  c.cu_row_count                                  AS CU_Rows,
  i.invoice_line_count                            AS InvoiceLines,
  ROUND(COALESCE(c.cu_billed_total,0) - COALESCE(i.invoice_total,0), 2)
                                                  AS Difference,
  CASE
    WHEN c.InvoiceId IS NULL THEN 'FAIL — invoice has no Cost & Usage rows'
    WHEN i.InvoiceId IS NULL THEN 'FAIL — InvoiceId absent from invoice_detail'
    WHEN ABS(c.cu_billed_total - i.invoice_total) < 0.005 THEN 'TIES TO THE CENT'
    ELSE 'FAIL — does not tie'
  END                                             AS Verdict
FROM cu_by_invoice c
FULL OUTER JOIN inv_totals i
  ON c.InvoiceId = i.InvoiceId AND c.BillingCurrency = i.BillingCurrency
ORDER BY 1;

-- ============================================================================
-- Q2 · RECONCILING ITEMS — the rows the invoice does NOT carry, shown, never
-- hidden. Null InvoiceId is conformant information ("not yet invoiced"), not
-- a defect. Legacy-era rows carry x_InvoiceId only (root field null by era).
-- ============================================================================
SELECT
  CASE
    WHEN InvoiceId IS NOT NULL                          THEN '1 · Invoiced (ties in Q1)'
    WHEN x_InvoiceId IS NOT NULL                        THEN '2 · Legacy era — x_InvoiceId only, no v1.4 invoice_detail row'
    WHEN ChargeCategory IN ('Tax','Credit','Adjustment') THEN '3 · Not yet invoiced — account-level (Tax/Credit/Adjustment)'
    WHEN ChargeCategory = 'Purchase'                    THEN '4 · Not yet invoiced — commitment purchases'
    ELSE                                                     '5 · Not yet invoiced — usage (open period)'
  END                                     AS ReconcilingPanel,
  BillingCurrency,
  strftime(BillingPeriodStart, '%Y-%m')   AS BillingPeriod,
  COUNT(*)                                AS Rows,
  ROUND(SUM(BilledCost), 2)               AS BilledCost
FROM cu
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ============================================================================
-- Q3 · GRAND PROOF — invoiced + reconciling items = the whole dataset,
-- per currency. Nothing dropped, nothing double-counted.
-- ============================================================================
SELECT '1 · Invoiced total'            AS Panel, BillingCurrency,
       ROUND(SUM(BilledCost),2) AS BilledCost, COUNT(*) AS Rows
FROM cu WHERE InvoiceId IS NOT NULL GROUP BY 2
UNION ALL
SELECT '2 · Reconciling items total', BillingCurrency,
       ROUND(SUM(BilledCost),2), COUNT(*)
FROM cu WHERE InvoiceId IS NULL GROUP BY 2
UNION ALL
SELECT '3 · = Dataset total', BillingCurrency,
       ROUND(SUM(BilledCost),2), COUNT(*)
FROM cu GROUP BY 2
ORDER BY 2, 1;

-- ============================================================================
-- Q4 · ORPHANS, BOTH DIRECTIONS — A3.2 assertion 2 (HARD)
-- ============================================================================
SELECT 'CU InvoiceId missing from invoice_detail' AS Direction,
       c.InvoiceId, COUNT(*) AS Rows
FROM cu c LEFT JOIN inv i ON c.InvoiceId = i.InvoiceId
WHERE c.InvoiceId IS NOT NULL AND i.InvoiceId IS NULL
GROUP BY 2
UNION ALL
SELECT 'Issued invoice with no CU rows', i.InvoiceId, COUNT(*)
FROM inv i LEFT JOIN cu c ON i.InvoiceId = c.InvoiceId
WHERE i.InvoiceIssueStatus = 'Issued' AND c.InvoiceId IS NULL
GROUP BY 2;

-- ============================================================================
-- Q5 · PERIOD MATCH — A3.2 assertion 3 (HARD)
-- Every BillingPeriodStart/End pair in Cost & Usage must exist in
-- billing_period. Asserted against the dataset, not inferred.
-- ============================================================================
SELECT
  strftime(c.BillingPeriodStart, '%Y-%m-%d') AS PeriodStart,
  strftime(c.BillingPeriodEnd,   '%Y-%m-%d') AS PeriodEnd,
  COUNT(*)                                   AS CU_Rows,
  MAX(b.BillingPeriodStatus)                 AS PeriodStatus,
  CASE WHEN MAX(b.BillingPeriodStart) IS NULL
       THEN 'FAIL — period pair not in billing_period'
       ELSE 'MATCHED' END                    AS Verdict
FROM cu c
LEFT JOIN bp b
  ON CAST(c.BillingPeriodStart AS DATE) = b.BillingPeriodStart
 AND CAST(c.BillingPeriodEnd   AS DATE) = b.BillingPeriodEnd
GROUP BY 1, 2
ORDER BY 1;

-- ============================================================================
-- Q6 · CORRECTION DISCIPLINE — the one row type permitted to speak about the
-- past: the Correction must reference a CLOSED billing period (S1 in action:
-- June consumption, July bill; invoice line carries ReferenceInvoiceId).
-- ============================================================================
SELECT
  c.ResourceName,
  strftime(c.ChargePeriodStart,  '%Y-%m-%d') AS ConsumptionDate,
  strftime(c.BillingPeriodStart, '%Y-%m')    AS BilledInPeriod,
  ROUND(c.BilledCost, 2)                     AS BilledCost,
  i.ReferenceInvoiceId,
  b.BillingPeriodStatus                      AS ReferencedPeriodStatus,
  CASE WHEN b.BillingPeriodStatus = 'Closed' THEN 'PASS — restates a closed period'
       ELSE 'FAIL' END                       AS Verdict
FROM cu c
JOIN inv i ON c.InvoiceId = i.InvoiceId AND i.ReferenceInvoiceId <> i.InvoiceId
LEFT JOIN bp b
  ON CAST(c.ChargePeriodStart AS DATE) >= b.BillingPeriodStart
 AND CAST(c.ChargePeriodStart AS DATE) <  b.BillingPeriodEnd
WHERE c.ChargeClass = 'Correction';
