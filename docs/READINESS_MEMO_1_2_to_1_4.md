# Readiness memo: from FOCUS 1.2 to FOCUS 1.4

*Portfolio Project 1. Written 2 September 2026 at the close of Stage 6;
revised 13 September 2026 for publication. Inputs: the specification diff
produced by `version_diff.py` between the 1.2 and 1.4 tags, the validator as
it actually runs, and the project's findings ledger.*

---

## The verdict in one paragraph

This pipeline is substantially ready for FOCUS 1.4 today, because it chose to
build the 1.4 shape before Azure ships it. The three supplemental datasets
that 1.4 introduces exist and reconcile to the cent. The checks that join the
bill to them run on every build. And the eligibility flag the coverage
analysis depends on turns out to anticipate a column that 1.4 actually adds.
On the day Azure's export moves, the work is not a migration but a
re-pointing: two checks rewritten against renamed columns, five citations
re-read and re-bound, one detection mechanism re-keyed, and one interim
column retired in favour of its native successor. The validator can name
every one of those items before the move happens, because every check cites
the sentence it enforces. That is the whole point of building it that way.

## What the words mean

FOCUS describes each column with a feature level. A **Mandatory** column
must be present in every dataset. A **Recommended** column should be. A
**Conditional** column must be present when a stated condition holds, for
example when the provider supports the feature the column describes. A
column moving from Recommended to Conditional is therefore not a loosening;
it replaces a preference with a rule that has a trigger.

The **supplemental datasets** are three tables 1.4 defines alongside the
main cost and usage table: `invoice_detail` (one row per invoice line),
`billing_period` (one row per billing period, with its status) and
`contract_commitment` (one row per commitment, with its term and cost). They
exist so that the cost data can be reconciled to invoices and commitments,
which the cost table alone cannot support.

**Covered and covering charges** are 1.4's names for the two halves of a
prepaid commitment: the purchase row that carries the cash (covering) and the
usage rows it pays for (covered). The 1.4 text states plainly that billed
cost on a covered row must not include any amount the covering row already
carried.

## What this pipeline already satisfies

**The supplemental datasets, and their reconciliation.** All three exist,
built to the 1.4 shape: 18, 6 and 28 columns respectively. The three-way
reconciliation ties the sum of billed cost per invoice identifier to the
invoice total to the cent, shows the rows that carry no invoice as
reconciling items rather than hiding them, checks for orphans in both
directions, matches billing periods at civil-date grain, and enforces that a
correction refers to a closed period. All of it is promoted into the
validator, and all of it runs green.

**The invoice-detail identifier.** 1.4 adds `InvoiceDetailId` as a
Conditional column. The join architecture it formalises is the one already
built here.

**Eligibility-aware coverage.** 1.4 adds a Conditional column,
`CommitmentProgramEligibilityDetails`, that says whether a charge could have
been covered by a commitment. This project's interim column,
`x_CommitmentEligible`, is that column's anticipation: three-valued,
disclosed, and seeded in the engineered data. Coverage of coverable spend
(85.5 per cent in dollars) against naive coverage (63.4 per cent) already
reports on every run.

**The covered and covering rule, already respected.** 1.4's rewritten billed
cost sentences formalise behaviour this dataset already exhibits. Committed
usage bills zero because the purchase carried the cash; the marketplace
appliance bills zero because a third party invoices it. The note at the end
of this memo explains why an accountant will find that rule familiar.

**Resilience to drift, by construction.** The loader falls back gracefully
when a column is absent under an older name, and the unified dataset is
built by column name rather than by position, so the ten columns 1.4 adds
land as empty values until they are populated, not as failures.

## What changes when Azure ships 1.4

From the diff, 57 columns become 65. In order of work:

1. **Two checks cannot be expressed at 1.4** because the columns
   `ProviderName` and `PublisherName` are removed. The diff, correctly,
   reports no named successor; reading the added columns, the successors are
   plainly `HostProviderName` and `ServiceProviderName`, both Mandatory,
   which is firmer footing than the columns they replace. Action: rewrite
   the two nullability checks against the new pair. Both become simpler.

2. **The marketplace detection re-keys.** The current mechanism, that a
   marketplace charge is one where the publisher differs from the provider,
   loses both its columns. Action: re-derive it from the new provider pair.
   The new billed cost sentence about third-party charges gives the rule
   better footing in the text than it had.

3. **Five citations go stale and must be re-read by a person.** The
   validator refuses to guess whether a sentence was withdrawn or rewritten,
   which is the right refusal. Two of the five are the project's own history
   arriving back: the commitment-closure check and the commitment-split
   check cite sentences that 1.4 rewrote in the direction this project
   derived independently, scoping the rule to a single commitment and making
   the covered and covering relationship explicit. Action: read the new
   effective cost text, re-cite, and fold the full-term precondition, which
   is already enforced through `contract_commitment`, into the re-bound
   checks. The other three look like rewordings; re-cite after reading, and
   raise an alert if any proves substantive.

4. **Two pricing-currency columns tighten** from nullable to not nullable.
   Today they are absent from the real export; at 1.4 they become
   not-nullable when present. Action: none until Azure populates them. The
   nullability checks regenerate from the specification at the new tag.

5. **The invoice identifier moves from Recommended to Conditional.** The
   real export's story, in which 99 per cent of rows carry no invoice
   identifier, changes character: presence becomes governed by a condition
   rather than a recommendation. The reconciliation stays keyed on the
   identifier either way, and the discipline that "not evaluable" is not the
   same as "balanced" is unchanged.

6. **The allocation family arrives.** Five new columns describe how a charge
   was allocated and to what. No current check depends on them. The untagged
   showback line, $12.63 across 34 rows, gains a native home. This is roadmap,
   not a blocker.

7. **The interim eligibility column retires** in favour of the native one,
   with a note mapping the project's three values to the native vocabulary.
   The coverage queries change one column reference; the discipline of
   disclosing where the concept does not apply carries over unchanged.

8. **The text churn is real but mostly editorial at the rule level.** Fifty-
   five columns are touched, 138 statements added and 115 withdrawn, most of
   it the removal of boilerplate "must be present" sentences and a rewording
   from "provider" to "invoice issuer". The citation-level impact is the five
   items above. Everything else re-parses at the new tag.

## Adoption guidance: what this month demonstrated live

Implement against what the provider ships today, not what the specification
announces. Azure's native export still returns version 1.0r2. The 1.2 dataset
is selectable only at billing-account scope weeks after its announcement,
and Microsoft documents that several columns 1.2 requires export as empty
until supporting capabilities arrive. A pipeline that had "migrated to 1.2"
on announcement day would today be parsing a partly hollow preview at some
scopes and nothing at others.

The right posture, and the one this project takes, is to run on the shipped
version, build the target version's shape beside it, and hold a
machine-generated list of exactly what breaks on the day of the move. Two
boundary facts, measured in this project's own data, show why the list has
to be honest about eras: the supplemental datasets do not reach back across
versions (the 2024 rows carry the old invoice identifier with no invoice
detail row to match), and one interim invoice sits issued against an open
period. Those are reconciling items to disclose, not defects to fix.

## A note for accountants: the covered and covering rule is a consolidation entry

1.4's billed cost language makes explicit a recognition rule that a finance
reader will find familiar. A commitment purchase and the usage it covers are
two views of one economic event. The purchase carries the cash: $2,702.40 on
two purchase rows in this dataset. The covered usage carries the consumption:
effective cost amortised across the term, with billed cost of zero. Letting
the covered rows also carry billed cost would recognise the same money
twice, which is exactly the double count that intercompany elimination
exists to prevent in a set of consolidated accounts.

Billed cost is the legal-entity view: who was invoiced, when, and for how
much cash. Effective cost is the group view: what consumption actually cost,
matched to the period it served. The covering and covered mechanism is the
elimination entry between them. The marketplace case is the same idea in its
agent-and-principal form: the provider bills zero for the appliance because
a third party is the principal on that invoice, so there is $18.00 of
effective cost against no cash, and only one of them belongs on the
provider's invoice.

This dataset already tells both stories and reconciles the gap between the
two cost columns to nothing unexplained: $18.00 of third-party cost and
$2,625.60 of commitment timing, and the bridge closes. 1.4 does not change
what this pipeline does. It writes what the pipeline does into the
specification.

## The bottom line

Ready now: the datasets, the reconciliation, the coverage analysis, the
discipline checks, and a loader that survives drift. Work on the day Azure
ships 1.4: rewrite two, re-cite five, re-key one, retire one. The validator
produced that list mechanically, because every check cites its sentence. That
is the difference between a version upgrade that takes an afternoon and one
that becomes an archaeology project.
