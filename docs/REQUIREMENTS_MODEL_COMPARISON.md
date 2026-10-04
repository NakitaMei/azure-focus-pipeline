# The validator against the FOCUS Requirements Model

**Date:** 4 October 2026. **Prompted by:** Michael Flanakin, in the FOCUS channel of the FinOps Foundation Slack, who pointed out that the specification ships a machine-readable model of its rules and suggested it might simplify this project.
**Scope:** every check in `validate.py` (166 per-dataset checks and 7 cross-dataset checks) against the Requirements Model at release 1.2 for the cost and usage data, and at release 1.4 for the three supplemental datasets. Evidence files: [`requirements_model_map.csv`](requirements_model_map.csv) (one row per check, with the model rule it maps to) and [`requirements_model_gaps.csv`](requirements_model_gaps.csv) (every MUST-level model rule this validator does not cover).

## What the Requirements Model is

The FOCUS Working Group maintains two outputs: the specification, which is English prose, and the Requirements Model, which is the same normative content expressed as JSON. It lives at `specification/requirements_model/` in the FOCUS_Spec repository, one folder per release. Each rule records the sentence it comes from (`MustSatisfy`), the RFC 2119 keyword of that sentence (`Keyword`), the version it was introduced in and, where relevant, removed, an optional `Condition` for conditional requirements, optional `ApplicabilityCriteria` (flags a provider declares, such as "this provider supports availability zones"), and a `CheckFunction` that says how to test it. Rules are either atomic (one test) or composite (an AND of child rules). The official `focus_validator` consumes this model directly: the copy it ships, `model-1.2.0.1.json`, is the built 1.2 model, and it can download newer releases from GitHub.

At release 1.2 the model holds 621 rules: 143 composite and 478 atomic. Of the atomic rules, 400 are MUST-level (MUST or MUST NOT), 43 are SHOULD-level and 35 are MAY. The model's own README says the extraction was AI-assisted and that member review is still needed; one consequence is visible in the data, which is that 201 of the 478 atomic rules (42 percent) have no `CheckFunction` yet. They record the sentence but cannot be executed.

## Method

The validator's checks were built in memory by calling `build_registry()`, which yields each check with the specification sentence it cites. The model was flattened to one row per rule. Each check was matched to model rules by column, then by similarity of the normalised sentence text (markdown links, quotes and emphasis stripped, case folded). A similarity of 0.90 or above was treated as the same sentence. The reverse pass took every MUST-level atomic model rule and asked whether any check cites it; presence rules for Mandatory columns were counted as covered by the single `PRESENCE-mandatory` check, which iterates over all of them. Figures below come from that run and nothing else.

## Finding 1. The two readings of the specification agree

Of 173 checks, 164 match a model rule sentence at 0.90 or better (163 of them at 0.95 or better, which in practice means the same sentence with formatting differences). Where this validator and the Foundation's model both read a sentence, they read the same sentence. The other nine are expected: four are the Stage 6 cross-dataset checks that are labelled *derived* in this repository, meaning they follow from the specification but are not stated in it, and the model, correctly, has no rule for them; one is the declaration-drift check, which tests the version a file declares rather than any requirement; and four are presence checks that cover many model rules each (one check per dataset, one model rule per column), so they match no single sentence.

Keyword agreement is 162 of 164. The two disagreements are the two deliberate severity downgrades already documented in `validate.py`: `WARN-ResourceName-duplicates-ResourceId` and `COMMIT-closure-F10`, both MUST in the specification and reported here as warnings because their preconditions (how a resource was provisioned; whether the export spans a commitment's full term) cannot be known from the rows. The model keeps both at MUST and has no `CheckFunction` for either, which is to say it records the rule and declines to execute it. That is the same judgement arrived at differently: this validator runs the test and softens the verdict; the model keeps the verdict and does not run the test.

## Finding 2. Sixteen checks here run rules the model cannot yet execute

Sixteen of the 164 matched checks correspond to model rules whose `CheckFunction` is empty. They include the cross-dataset invoice reconciliation (`BilledCost-C-007-M`, the sum of BilledCost per invoice matching the invoice total), the commitment closure and split rules (`EffectiveCost-C-012-M` and `-013-M`), the charge-period and billing-period ordering rules, the two `SkuPriceDetails` key and value rules, the empty-string rules from the NullHandling and StringHandling attributes, and three conditional nullability rules. For each of these the model has the sentence and the keyword but no executable form, and this repository has a working implementation that could be read as a proposal for one. That is the most useful thing this comparison turned up, and the list is in the map file filtered on an empty `model_check_function`.

## Finding 3. The semantic conditions: the model's own history supports the pruning rule

`rules.py` refuses 18 nullability sentences because their condition is a fact about the world rather than about the row ("when a charge is related to a resource"). The model's treatment of the same 18 is instructive.

Fourteen are left unexecutable in the model as well. Two are handled in ways this validator does not have: `BillingAccountName-C-003-C` is gated by the applicability flag `ACCOUNT_NAMING_SUPPORTED`, a declaration the data generator makes rather than something inferred from data, and `CapacityReservationId-C-005-C` uses a data proxy, treating "the unused portion of a capacity reservation" as `CapacityReservationStatus = "Unused"`. The second is a narrowing in the sense this repository uses the word (if the status says Unused, the charge is the unused portion, so the rule fires only when it should) and it is a sound improvement this validator should adopt.

The remaining two are the InvoiceId pair. At release 1.2 the model encodes `InvoiceId-C-004-C` ("MUST be null when the charge is not associated with an invoice") as an unconditional `CheckValue null` and `InvoiceId-C-005-C` ("MUST NOT be null when the charge is associated with an invoice") as an unconditional `CheckNotValue null`. The conditions were dropped, which broadens both rules until one of them must fail on every row. This is the mechanism behind the 14 false positives the official validator reported on `focus_unified` in August (Stage 4 notes, F44 and the correction that follows it). At release 1.4 both rules still exist, with the same sentences, and their `CheckFunction` has been removed: the model's maintainers reached the same conclusion this repository reached in `rules.py`, that a rule whose condition cannot be evaluated should be declined rather than asserted. That is not a contribution to claim; it is independent confirmation that the rule "you may narrow when a requirement applies, you may never broaden it" is the right one.

## Finding 4. What this validator does not check, measured

The reverse pass is where the model is unkind, and it should be. Of 400 MUST-level atomic rules at 1.2, this validator covers 115. Of the 285 it does not cover, 132 are not executable in the model either, so neither tool tests them. The 153 that the model can execute and this validator does not fall into five groups:

| Group | Rules | What they are | Testable by a data consumer? |
|---|---:|---|---|
| Type | 55 | "X MUST be of type String / Decimal / Date/Time" | Yes. Parquet carries a schema, so this is cheap, and it is simply not done here. |
| Format | 50 | "X MUST conform to StringHandling / NumericFormat / DateTimeFormat / KeyValueFormat / CurrencyFormat" | Mostly yes. The nearest existing checks (`FMT-ISO4217` and the two `SKU-` checks) cite neighbouring sentences, not these; none of the five format families is checked as such. |
| Conditional presence | 32 | "X MUST be present when the provider supports ..." | Only with the provider's applicability flags, which this validator has no concept of. |
| Validation | 12 | "valid decimal value" rules, three cardinality rules (one ServiceCategory per ServiceName; one parent ServiceCategory per ServiceSubcategory; one SkuId per SkuPriceId), three value-conditioned cost rules | Yes, all twelve. The ServiceSubcategory rule is the one the README already names as caught by the official validator and not here. |
| Nullability | 4 | The two InvoiceId rules (broadened in the model, see Finding 3), one applicability-gated rule, one with the Status proxy | Two of four, via the proxy and the flag. |

The type and format gap is the honest headline. This validator was built around the rules that are hard to get right (conditions, cross-column metrics, cross-dataset reconciliation) and skipped the rules that are easy, on the unstated assumption that a Parquet file's schema already enforces them. The model does not make that assumption and neither should this project.

## Finding 5. What the README says about the official validator is partly out of date

The README states that the Foundation's validator "cannot evaluate conditional rules and treats SHOULD and MUST alike". The Stage 4 working notes (F44) already corrected the first half on 19 August, when the reference run showed version 2.2.1 evaluating a genuine cross-column conditional; the README was not updated to match and must be. The model has 58 executable conditional atomic rules at 1.2, 50 of them nullability, and the official validator runs them.

The second half is narrower than stated. The official validator's result statuses are passed, failed, skipped and errored; a failed SHOULD and a failed MUST both report as failed, and MAY rules are skipped and say so. Its HTML output, however, groups rules into MUST, SHOULD and MAY sections, so a reader of that report can tell them apart even though the status cannot. The accurate statement is that it does not carry severity in the result, not that it ignores the keyword.

Two differences from the Stage 4 notes survive this review and remain the real ones. The official validator has no era awareness: against `focus_unified` it reported 128 violations of `ServiceSubcategory MUST NOT be null` on rows emitted before the column existed. And it asserts the two InvoiceId rules unconditionally, for the reason given in Finding 3. Both are properties of the 1.2 model it ships rather than of the validator's code, and the second is already fixed at 1.4.

One methodological note on the August run: it was made without `--applicability-criteria`, so the log records that every rule carrying applicability criteria (96 at 1.2) was skipped. A fair comparison should be re-run with the criteria Azure actually meets, or with `ALL`.

## What changes in this repository as a result

1. **README, "What makes it different" section.** Replace the sentence about conditional rules and severities with the accurate version above. Add one line saying the official validator runs on the Requirements Model and that this validator has been checked against it, with a link to this document. This is the first change to make, because it is the one a reader from the Foundation will look for.
2. **Type and format checks.** Add a type check per column from the parsed `data_type` (55 rules) and the three remaining format families (string handling, numeric, date-time). These are small and close the largest measured gap.
3. **Adopt the Status proxy** for `CapacityReservationId-C-005-C`: move the sentence from the refused list to the implemented list with the condition `CapacityReservationStatus = "Unused"`, and record the model as the source of the proxy.
4. **Read the model, do not replace the parser.** The parser's value is that every check cites a sentence at a pinned tag and refuses what it cannot express; the model's value is that it is the Foundation's own reading, maintained by the people who write the specification. The right relationship is that `spec_source.py` loads the model for the release it is pinned to and checks its own parse against it, reporting any sentence the two read differently. That makes the agreement in Finding 1 a test that runs on every build rather than a one-off.
5. **Offer the sixteen implementations.** The sixteen checks in Finding 2 are candidate `CheckFunction` definitions for rules the model has not yet made executable. Whether and how to offer them is a question for the FOCUS channel, not a decision for this repository.
6. **Re-run the official validator** with applicability criteria set, and replace `docs/reference-validator-run.log`.

## Terms used

*Requirements Model*: the JSON form of the specification's rules, described above. *Atomic rule*: one testable statement; *composite rule*: an AND of several. *CheckFunction*: the named test a rule uses, such as `CheckNotValue` or `TypeDecimal`; a rule without one is recorded but not executable. *Applicability criteria*: flags describing what a provider supports, declared by the data generator, that switch rules on or off. *Narrowing* and *broadening*: making a rule fire in fewer cases than the sentence says (safe) or more cases (unsafe), the distinction `rules.py` is built on.
