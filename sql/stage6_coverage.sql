-- ============================================================================
-- STAGE 6 · CHUNK 2 — ELIGIBILITY-AWARE COVERAGE  (Q7–Q11)
-- Coverage of COVERABLE spend, not of all spend — Amendment A3.3, using the
-- x_CommitmentEligible flag seeded in Stage 3 (three-valued; the NULL matters).
-- S-rules honoured: currency separation (§5.1), round for display only (S3),
-- EffectiveCost basis throughout, Unused excluded from demand (flag design).
-- ============================================================================

CREATE OR REPLACE VIEW cu AS
  SELECT * FROM read_parquet('data/unified/focus_unified.snappy.parquet');
CREATE OR REPLACE VIEW contract AS
  SELECT * FROM read_csv_auto('data/supplemental/contract_commitment.csv');

-- ============================================================================
-- Q7 · COVERAGE OF COVERABLE SPEND — the headline, per currency, with the
-- naive all-spend figure beside it to show WHY eligibility-awareness matters.
-- Denominator: eligible usage demand (flag TRUE). Numerator: the covered part
-- (PricingCategory = 'Committed'). Unused commitment is NOT demand.
-- ============================================================================
SELECT
  BillingCurrency,
  ROUND(COALESCE(SUM(CASE WHEN x_CommitmentEligible AND PricingCategory = 'Committed'
                 THEN EffectiveCost END), 0), 2)            AS covered_eligible,
  ROUND(SUM(CASE WHEN x_CommitmentEligible
                 THEN EffectiveCost END), 2)                AS total_eligible,
  ROUND(100 * COALESCE(SUM(CASE WHEN x_CommitmentEligible AND PricingCategory = 'Committed'
                       THEN EffectiveCost END), 0)
            / SUM(CASE WHEN x_CommitmentEligible
                       THEN EffectiveCost END), 1)          AS coverage_of_coverable_pct,
  ROUND(100 * COALESCE(SUM(CASE WHEN x_CommitmentEligible AND PricingCategory = 'Committed'
                       THEN EffectiveCost END), 0)
            / SUM(CASE WHEN ChargeCategory = 'Usage'
                        AND COALESCE(CommitmentDiscountStatus,'') <> 'Unused'
                       THEN EffectiveCost END), 1)          AS naive_coverage_of_all_usage_pct
FROM cu
WHERE ChargeCategory = 'Usage'
GROUP BY BillingCurrency
HAVING SUM(CASE WHEN x_CommitmentEligible THEN EffectiveCost END) IS NOT NULL
ORDER BY BillingCurrency;

-- ============================================================================
-- Q8 · THE ACTION LIST — eligible but UNCOVERED demand (flag TRUE, priced
-- Standard). This is what a commitment purchase would actually address.
-- Group on ResourceId, display the name (S5).
-- ============================================================================
SELECT
  BillingCurrency,
  ANY_VALUE(ResourceName)                 AS resource,
  COUNT(*)                                AS rows_,
  ROUND(SUM(EffectiveCost), 2)            AS uncovered_eligible_effective
FROM cu
WHERE ChargeCategory = 'Usage'
  AND x_CommitmentEligible
  AND PricingCategory = 'Standard'
GROUP BY BillingCurrency, ResourceId
ORDER BY BillingCurrency, uncovered_eligible_effective DESC;

-- ============================================================================
-- Q9 · THE ELIGIBILITY UNIVERSE, DISCLOSED — every row lands in exactly one
-- bucket, and NULL is never silently treated as ineligible. The two NULL
-- buckets have different meanings and are labelled apart:
-- era-NULL (the flag postdates the row's era) vs concept-NULL (not demand).
-- ============================================================================
SELECT
  CASE
    WHEN x_CommitmentEligible = TRUE  THEN '1 · eligible (coverable demand)'
    WHEN x_CommitmentEligible = FALSE THEN '2 · ineligible usage (documented rule)'
    WHEN ChargeCategory = 'Usage'
     AND COALESCE(CommitmentDiscountStatus,'') = 'Unused'
                                      THEN '3 · NULL — unused commitment (not demand)'
    WHEN ChargeCategory <> 'Usage'    THEN '4 · NULL — concept n/a (non-usage row)'
    WHEN x_SchemaEra <> '1.2'         THEN '5 · NULL — era predates the flag (' || x_SchemaEra || ')'
    ELSE                                   '6 · NULL — unexplained (should be empty)'
  END                                     AS eligibility_bucket,
  BillingCurrency,
  COUNT(*)                                AS rows_,
  ROUND(SUM(EffectiveCost), 2)            AS effective_cost
FROM cu
GROUP BY 1, 2
ORDER BY 1, 2;

-- ============================================================================
-- Q10 · TERM CLOSURE vs THE CONTRACT — Cost & Usage meets contract_commitment
-- (join: CommitmentDiscountId = ContractCommitmentId). Verdicts, not numbers
-- alone: exact closure / in-progress (short export ≠ shortfall) / orphan.
-- Trust the period columns over the description (known 1yr quirk).
-- ============================================================================
WITH usage_side AS (
  SELECT CommitmentDiscountId,
         BillingCurrency,
         SUM(CASE WHEN ChargeCategory = 'Usage' THEN EffectiveCost END) AS amortised_effective,
         SUM(CASE WHEN ChargeCategory = 'Purchase' THEN BilledCost END) AS purchase_billed,
         MIN(CAST(ChargePeriodStart AS DATE))                           AS first_seen,
         MAX(CAST(ChargePeriodStart AS DATE))                           AS last_seen
  FROM cu
  WHERE CommitmentDiscountId IS NOT NULL
  GROUP BY 1, 2
)
SELECT
  u.CommitmentDiscountId,
  u.BillingCurrency,
  ROUND(u.purchase_billed, 2)                       AS purchase_billed,
  ROUND(u.amortised_effective, 2)                   AS amortised_effective,
  ROUND(c.ContractCommitmentCost, 2)                AS contract_cost,
  CAST(substr(CAST(c.ContractCommitmentPeriodStart AS VARCHAR),1,10) AS DATE) AS term_start,
  CAST(substr(CAST(c.ContractCommitmentPeriodEnd   AS VARCHAR),1,10) AS DATE) AS term_end,
  CASE
    WHEN c.ContractCommitmentId IS NULL
      THEN 'ORPHAN — cost rows but no contract record; term unknown, closure not evaluable'
    WHEN u.last_seen <  CAST(substr(CAST(c.ContractCommitmentPeriodEnd AS VARCHAR),1,10) AS DATE)
     AND ABS(COALESCE(u.amortised_effective,0) - c.ContractCommitmentCost) >= 0.005
      THEN 'IN PROGRESS — export covers part of the term; short export, not shortfall'
    WHEN ABS(COALESCE(u.amortised_effective,0) - c.ContractCommitmentCost) < 0.005
     AND ABS(COALESCE(u.purchase_billed,0)     - c.ContractCommitmentCost) < 0.005
      THEN 'CLOSES EXACTLY — amortised = purchased = contract, to the cent'
    ELSE 'REVIEW — amounts do not reconcile within the observed term'
  END                                               AS verdict
FROM usage_side u
LEFT JOIN contract c ON u.CommitmentDiscountId = c.ContractCommitmentId
ORDER BY u.CommitmentDiscountId;

-- ============================================================================
-- Q11 · UNUSED COMMITMENT — the waste panel, deliberately SEPARATE from
-- coverage: it is utilisation's problem, and mixing it into the coverage
-- denominator would double-punish. Per commitment, per currency.
-- ============================================================================
SELECT
  CommitmentDiscountId,
  BillingCurrency,
  ROUND(SUM(CASE WHEN CommitmentDiscountStatus = 'Used'
                 THEN EffectiveCost END), 2)         AS used_effective,
  ROUND(SUM(CASE WHEN CommitmentDiscountStatus = 'Unused'
                 THEN EffectiveCost END), 2)         AS unused_effective,
  ROUND(100 * SUM(CASE WHEN CommitmentDiscountStatus = 'Used'
                       THEN EffectiveCost END)
            / SUM(CASE WHEN CommitmentDiscountStatus IN ('Used','Unused')
                       THEN EffectiveCost END), 1)   AS utilisation_pct
FROM cu
WHERE ChargeCategory = 'Usage' AND CommitmentDiscountStatus IS NOT NULL
GROUP BY 1, 2
ORDER BY 1;
