# FOCUS Conformance Report

**Generated:** 13 September 2026 by `validate.py` — every figure below comes from that run.  
**Specification:** cost and usage at **v1.2**; the supplemental datasets at **v1.4**, since they do not exist before v1.3.  
**Method:** rules are parsed from the specification's own requirement sentences at a pinned tag, not transcribed. Severity is taken from the RFC 2119 keyword in the sentence each check cites.

Reproduce with:

```
python3 spec_source.py       # fetch and parse the specification at 5 tags
python3 seed_data.py         # synthetic fixtures across three schema eras
python3 self_test.py         # generator self-test
python3 build_unified.py     # sanitise the real export, merge the layers
python3 generate_layer_c.py  # the v1.4 supplemental datasets
python3 validate.py --report # validate, and write this report
```

## Verdict

| Dataset | Rows | MUST (FAIL) | SHOULD (WARN) | Observations |
|---|---:|---:|---:|---:|
| `real:31 July 2026` | 118 | **236** | 1170 | 3 |
| `synthetic-v1.2` | 76 | **0** | 1 | 0 |
| `synthetic-legacy` | 10 | **0** | 1 | 1 |
| `unified` | 204 | **0** | 2 | 2 |
| `layerC:billing_period` | 3 | **0** | 0 | 0 |
| `layerC:contract_commitment` | 2 | **0** | 0 | 1 |
| `layerC:invoice_detail` | 2 | **0** | 0 | 1 |
| cross-dataset | — | **0** | 0 | 10 |

## Does the harness detect anything?

**14 of 14 planted violations caught by the check that names the rule.**

A validator that has only ever seen valid data has never been shown to detect anything. `data/negative/` holds deliberately broken rows, one fault each, every row declaring what it breaks. A violation counts only when the check that fires is the check implementing the rule the row names — anything else is a hit on the right row for the wrong reason, which is how an earlier version of this report claimed full coverage it did not have.

| Planted violation | Caught by |
|---|---|
| `NULL_IN_MANDATORY_COLUMN` | `NULL-ServiceCategory-notnull56` |
| `EMPTY_STRING_PLACEHOLDER` | `EMPTY-STRING-focus-columns` |
| `INVALID_ENUM_VALUE` | `AV-ChargeCategory` |
| `INVALID_CHARGECLASS_VALUE` | `XCOL-ChargeClass-Correction` |
| `SATELLITE_WITHOUT_ANCHOR` | `NULL-ResourceName-null53` |
| `TAX_WITH_PRICING_CATEGORY` | `NULL-PricingCategory-null37` |
| `PURCHASE_WITH_USAGE_BASED_FREQUENCY` | `XCOL-ChargeFrequency-Usage-Based` |
| `NEGATIVE_UNIT_PRICE` | `METRIC-nonneg-ListUnitPrice` |
| `UNIT_PRICE_COST_MISMATCH` | `METRIC-product-ContractedCost` |
| `ORPHAN_COMMITMENT_STATUS` | `NULL-CommitmentDiscountStatus-null19` |
| `ORPHAN_CAPACITY_RESERVATION_STATUS` | `NULL-CapacityReservationStatus-null7` |
| `SKU_PRICE_DETAILS_BAD_KEYS` | `SKU-key-prefix` |
| `CURRENCY_NOT_ISO_4217` | `FMT-ISO4217-BillingCurrency` |
| `CHARGE_PERIOD_INVERTED` | `PERIOD-ordering` |

## What was checked

**166 checks.** 165 cite a specification sentence; 1 is *derived* — it follows from the specification without being stated in it, and is labelled as such because a derived rule filed quietly among quoted ones devalues every quoted one beside it.

| Family | Checks |
|---|---:|
| Nullability (parsed) | 70 |
| Layer C (v1.4) | 69 |
| Allowed values | 7 |
| Metric validation | 6 |
| Commitment aggregates | 2 |
| Cross-column value rules | 2 |
| SkuPriceDetails keys and types | 2 |
| Empty strings standing in for null | 2 |
| Schema observations | 1 |
| Mandatory column presence | 1 |
| Service taxonomy | 1 |
| Advisory | 1 |
| Value format | 1 |
| Charge period ordering *(derived)* | 1 |
| cross-dataset | 7 |

## What the harness cannot check, and why

Of **88** nullability statements at v1.2, **70** are implemented and **18** are not machine-checkable.

These are not gaps in this harness. They are conditions the row does not carry — facts about the world that no validator reading a dataset can evaluate. **Naming them, with reasons, is worth more than a coverage percentage**, and it is a claim the reference FOCUS Validator cannot make at all, because it does not evaluate conditional requirements.

| Column | Requirement | Why not |
|---|---|---|
| `AvailabilityZone` | AvailabilityZone MUST be null when a charge is not specific to an availability zone | condition turns on a fact the row does not carry |
| `BillingAccountName` | BillingAccountName MUST NOT be null when the provider supports assigning a display name for the… | condition turns on a fact the row does not carry |
| `CapacityReservationId` | CapacityReservationId MUST be null when a charge is not related to a capacity reservation | condition turns on a fact the row does not carry |
| `CapacityReservationId` | CapacityReservationId MUST NOT be null when a charge represents the unused portion of a capacit… | condition turns on a fact the row does not carry |
| `CapacityReservationId` | CapacityReservationId SHOULD NOT be null when a charge is related to a capacity reservation | condition turns on a fact the row does not carry |
| `ChargeClass` | ChargeClass MUST be null when the row does not represent a correction or when it represents a c… | condition mixes a checkable term with a fact the row does not carry, joined by AND — dropping the unknown conjunct would broaden the rule and fail good data |
| `ChargeClass` | ChargeClass MUST NOT be null when the row represents a correction to a previously invoiced bill… | condition turns on a fact the row does not carry |
| `CommitmentDiscountId` | CommitmentDiscountId MUST be null when a charge is not related to a commitment discount | condition turns on a fact the row does not carry |
| `CommitmentDiscountId` | CommitmentDiscountId MUST NOT be null when a charge is related to a commitment discount | condition turns on a fact the row does not carry |
| `CommitmentDiscountName` | CommitmentDiscountName MUST NOT be null when a display name can be assigned to a commitment dis… | condition turns on a fact the row does not carry |
| `InvoiceId` | InvoiceId MUST be null when the charge is not associated either with an invoice or with a pre-g… | condition turns on a fact the row does not carry |
| `InvoiceId` | InvoiceId MUST NOT be null when the charge is associated with either an issued invoice or a pre… | condition turns on a fact the row does not carry |
| `RegionId` | RegionId MUST NOT be null when a resource or service is operated in or managed from a distinct … | condition turns on a fact the row does not carry |
| `ResourceId` | ResourceId MUST be null when a charge is not related to a resource | condition turns on a fact the row does not carry |
| `ResourceId` | ResourceId MUST NOT be null when a charge is related to a resource | condition turns on a fact the row does not carry |
| `ResourceName` | ResourceName MUST NOT be null when ResourceId is not null and the resource has an assigned disp… | condition mixes a checkable term with a fact the row does not carry, joined by AND — dropping the unknown conjunct would broaden the rule and fail good data |
| `SubAccountId` | SubAccountId MUST be null when a charge is not related to a sub account | condition turns on a fact the row does not carry |
| `SubAccountId` | SubAccountId MUST NOT be null when a charge is related to a sub account | condition turns on a fact the row does not carry |

## Findings

### `real:31 July 2026`

**FAIL — `EMPTY-STRING-focus-columns` — 236 violation(s)**

> Columns MUST NOT use empty strings or placeholder values such as 0 for numeric columns or "Not Applicable" for string columns to represent a null or not having a value, regardless of whether the column allows nulls or not
>
> — [NullHandling, v1.2](https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/v1.2/specification/attributes/null_handling.md)

CommitmentDiscountId holds an empty string where the value is absent

**WARN — `EMPTY-STRING-custom-columns` — 1170 violation(s)**

> Empty strings and strings consisting solely of spaces SHOULD NOT be used in not-nullable string columns
>
> — [StringHandling, v1.2](https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/v1.2/specification/attributes/string_handling.md)

x_CostAllocationRuleName holds an empty string where the value is absent (custom column — a SHOULD here, a MUST for FOCUS-defined columns)

**354 findings suppressed** on this dataset because the column they depend on holds `''` rather than NULL. The rule they name is not the rule that is broken; the placeholder itself is reported above.

### `synthetic-v1.2`

**WARN — `COMMIT-closure-F10` — 1 violation(s)**

> The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the sum of BilledCost where ChargeCategory is "Purchase"
>
> — [EffectiveCost, v1.2](https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/v1.2/specification/columns/effectivecost.md)

commitment rs/res-basv2-3yr-upfront-001 [USD]: Usage EffectiveCost 2.400000000000000000 vs Purchase BilledCost 2628.000000000000000000, out by -2625.600000000000000000. Scoped per F10; a gap here may mean the dataset does not span the commitment term, which the rows cannot confirm

### `synthetic-legacy`

**WARN — `COMMIT-closure-F10` — 1 violation(s)**

> The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the sum of BilledCost where ChargeCategory is "Purchase"
>
> — [EffectiveCost, v1.2](https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/v1.2/specification/columns/effectivecost.md)

commitment Orders/res-basv2-legacy-2023 [USD]: 0.100000000000000000 of Usage EffectiveCost with NO Purchase row in this dataset. Closure is not evaluable — the purchase falls outside the export window. Not an imbalance

### `unified`

**WARN — `COMMIT-closure-F10` — 2 violation(s)**

> The sum of EffectiveCost where ChargeCategory is "Usage" MUST equal the sum of BilledCost where ChargeCategory is "Purchase"
>
> — [EffectiveCost, v1.2](https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/v1.2/specification/columns/effectivecost.md)

commitment rs/res-basv2-3yr-upfront-001 [USD]: Usage EffectiveCost 2.400000000000000000 vs Purchase BilledCost 2628.000000000000000000, out by -2625.600000000000000000. Scoped per F10; a gap here may mean the dataset does not span the commitment term, which the rows cannot confirm

## Cross-dataset

Rules spanning cost and usage and the supplemental datasets. These cannot be expressed against a single table — the commitment term and the invoice total live in Layer C, which is why Layer C exists.

- **INFO** `XDS-invoice-reconciliation` — 202 of 204 cost rows (99%) carry no InvoiceId and are outside invoice reconciliation entirely
- **INFO** `XDS-invoice-reconciliation` — 1 invoice(s) reconciled on the key the spec names
- **INFO** `XDS-commitment-closure` — commitment tionOrders/res-basv2-1yr-001 [USD]: term fully covered and closure holds exactly at 74.400000000000000000. F10 asserted, not merely warned — the term came from Layer C
- **INFO** `XDS-commitment-closure` — commitment rs/res-basv2-3yr-upfront-001 [USD]: dataset covers 1 of 1096 days of the term 2026-07-31 to 2029-07-31, so closure is NOT EVALUABLE. Usage 2.400000000000000000 against a 2628.000000000000000000 purchase is a short export, not a shortfall
- **INFO** `XDS-commitment-closure` — commitment Orders/res-basv2-legacy-2023 has cost rows but no contract_commitment record — its term is unknown, so closure stays not evaluable
- **INFO** `XDS-invoice-orphan-cost-side` — every InvoiceId on a cost row exists in invoice_detail
- **INFO** `XDS-period-pair-match` — every cost-row period pair exists in billing_period (3 period(s) declared) — compared at civil-date grain (S7)
- **INFO** `XDS-correction-discipline` — Correction restates a Closed period (consumption 2026-06-14) and its invoice names the reference — cut-off discipline holds
- **INFO** `XDS-eligibility-universe` — [EUR] coverage of coverable 0.0% vs naive all-usage 0.0% — same numerator, two denominators; only the first respects eligibility
- **INFO** `XDS-eligibility-universe` — [USD] coverage of coverable 85.5% vs naive all-usage 63.4% — same numerator, two denominators; only the first respects eligibility

## Limitations

A conformance report listing only what passed invites the reading that everything else was checked and found clean. It was not.

- **18 conditional requirements are not machine-checkable** and are listed above with reasons.
- **Numeric tolerance is a harness policy, not a specification requirement.** `numeric_format.md` states that the specification does not require a specific level of precision and leaves it to the provider. The tolerance used here is `0.000001`.
- **Presence and nullability are separate questions** and are reported separately. A Conditional column being absent is not a defect unless its condition holds, and whether it holds is usually not in the data.
- **Checks are era-aware at row level.** A rule about a column introduced later is not applied to earlier rows. Value constraints are not gated this way: a value that is present is checked regardless of the version a row declares, because the declared version is a floor rather than a description.
- **The empty-string sweep never runs against the merged view**, which normalises `''` to NULL. Run there it would report zero and read as a pass. It binds only to datasets holding values as the producer wrote them.
- **Two invariants presuppose full-term coverage of a commitment.** Where the supplemental dataset supplies the term, this is decided; where it does not, closure is reported as not evaluable rather than as balanced.

