# Azure Cost Management to FOCUS: a pipeline that reads the specification

This repository holds a working pipeline that takes a real Microsoft Azure
bill, exported in the FOCUS format, and treats it the way a finance team
treats a ledger. It validates the bill against the specification's own rule
sentences, ties invoices out to the cent, reconciles real AI token spend to
what Microsoft charged, and states every saving against what it was measured
against.

It was built from a CFO's seat, so the bridge to finance is the point rather
than a feature. Every number in this repository says whether it is real or
engineered, and the mistakes made along the way are kept on the record,
because a method that hides its failures cannot be trusted with anyone
else's bill.

If you have ten minutes, read [the case study](docs/CASE_STUDY.md). If you
have two, read the five results below.

---

## Five results

| | Result | Data | Where |
|---|---|---|---|
| 1 | **The export was a version behind the announcement, and then it moved.** Azure's native FOCUS export declares version `1.0r2` with 96 columns; the newer `1.2-preview` export declares 105 and can only be created at billing-account scope. Three columns that the older export ships as provider extensions become standard columns one version later. A pipeline written to the announced version would read columns that are not there. | real | [`docs/READINESS_MEMO_1_2_to_1_4.md`](docs/READINESS_MEMO_1_2_to_1_4.md) |
| 2 | **236 hard-rule failures from one formatting habit.** The column that identifies a commitment discount holds an empty text string where the specification requires a proper empty value (null), on every row. That single habit produces 354 further phantom failures three columns away and disables the invoice reconciliation the specification mandates, because nothing can be joined on a blank. | real | [`docs/conformance-report.md`](docs/conformance-report.md) |
| 3 | **A three-way invoice tie-out to the cent.** Cost rows, invoice lines and billing periods are matched the way a finance team matches a purchase order, an invoice and a delivery note. Tax, credit and purchase rows are shown as reconciling items rather than netted away. | synthetic, built to FOCUS 1.4 shapes | [`sql/stage6_reconciliation.sql`](sql/stage6_reconciliation.sql) and [`docs/STAGE6_WORKING_NOTES.md`](docs/STAGE6_WORKING_NOTES.md) |
| 4 | **Real AI token spend reconciled to the bill, twice, exactly.** Eight hundred batched requests, 1,422,991 tokens, $0.281718 in the usage log and the same figures on Microsoft's export. Run again a week later with identical input: 1,417,163 tokens, $0.280553, another exact tie. The 0.4 per cent difference in output between the runs is the model's own nondeterminism, measured. | real | [`sql/stage7_queries.sql`](sql/stage7_queries.sql) and [`docs/STAGE7_KICKOFF_LOG.md`](docs/STAGE7_KICKOFF_LOG.md) |
| 5 | **A schedule that removed 70 per cent of a machine's running hours and saved $0.00.** Compute on the sandbox machine is covered by a free allowance and bills nothing; the managed disk and reserved IP address are the whole bill, and a schedule cannot touch them. The saving is reported as zero, with the counterfactual stated: roughly 70 per cent of compute cost at pay-as-you-go rates, the day compute starts to bill. | real | [`docs/STAGE7_ANALYSIS_WORKING_NOTES.md`](docs/STAGE7_ANALYSIS_WORKING_NOTES.md), section 10 |

---

## The validator, in numbers

The FOCUS specification writes its rules using a convention borrowed from
internet standards (RFC 2119): a capitalised **MUST** is a hard requirement,
a **SHOULD** is a strong recommendation, and a **MAY** is optional. This
validator parses the specification's own sentences at a pinned version and
turns each into a check, so the rule and its severity come from the text
rather than from anyone's memory of it.

| | |
|---|---|
| Checks | **166** |
| Of which citing a specification sentence | **165** |
| Of which derived from the specification without being stated in it | **1**, labelled as such |
| Of which cross-dataset, joining the bill to the supplemental datasets | **7** |
| Rules about when a column may be empty, at version 1.2 | 88, of which **70 implemented** and **18 not machine-checkable** |
| Datasets validated | **7**, across two specification versions |
| Deliberately broken rows detected | **14 of 14**, each by the check that names its rule |

The seven cross-dataset checks are the finance bridge. They ask whether every
invoice identifier on a cost row exists in the invoice file, whether billed
cost sums to the invoice total per invoice, whether every billing period the
bill refers to exists, whether a commitment's amortised usage sums back to
its purchase over the contracted term, whether a correction refers to a
closed period, whether the billing periods are internally consistent, and
whether every row lands in exactly one bucket of the coverage analysis.

The eighteen rules that are not checked are the interesting number. Each is
a conditional rule whose condition refers to a fact the data does not carry,
such as *"MUST be empty when a charge is not related to a resource"* or
*"MUST NOT be empty when the provider supports assigning a display name"*. A
program reading the bill cannot know either of those things. The conformance
report lists all eighteen with the reason. They are not gaps in this
validator; they are gaps in what any validator reading a dataset can know,
and naming them is worth more than a coverage percentage that hides them.

---

## What makes it different from the reference validator

**Two severities, taken from the specification's wording.** Each check
inherits the keyword of the sentence it cites, so a MUST is a failure and a
SHOULD is a warning, and no one can promote one into the other by hand. At
version 1.2 the specification contains 349 MUST-level statements, 30
SHOULD and 30 MAY.

**Conditional rules are evaluated.** A sentence like *"X MUST be empty when Y
is empty"* becomes an executable condition, including conditions inherited
from a parent clause. Where a condition mixes a part that can be checked with
a part that cannot, the validator narrows the rule and never broadens it,
because broadening fails good data.

**Version awareness at row level.** The merged dataset spans three revisions
of the specification. A rule about a column introduced in a later version is
not applied to earlier rows. Value constraints are not gated that way, on
purpose: a value that is present is checked regardless of the version the
row declares, because the declared version turns out to be a floor rather
than a description. Azure declares 1.0r2 and ships two columns from 1.2.

**Proven against broken data.** The folder `data/negative/` holds fourteen
rows, each breaking exactly one rule and declaring which. A detection counts
only when the check that fires is the check implementing that rule.

**Run alongside the official validator.** The FinOps Foundation's own
validator cannot evaluate conditional rules and treats SHOULD and MUST alike.
It does catch two recommendation-level rules this one does not: that a
service name maps to one sub-category, and that a pricing unit follows the
unit format. Both are implementable and neither is implemented yet. Its run
log is in [`docs/reference-validator-run.log`](docs/reference-validator-run.log).

---

## Version strategy: validated at 1.2, built for 1.4

The cost and usage data is validated at version 1.2, the version the parsed
rules are pinned to. The three supplemental datasets that 1.4 introduces for
invoice reconciliation, `invoice_detail`, `billing_period` and
`contract_commitment`, are built to the 1.4 shape now, because they do not
exist before 1.3 and the reconciliation that depends on them runs on every
build. The readiness memo lists, mechanically, what changes on the day Azure
ships 1.4: rewrite two checks, re-cite five, re-key one detection, retire one
interim column. It also records that the specification moved in three places
in the direction this project had already argued from first principles. The
posture throughout is to implement against what the provider ships today and
hold the list of what breaks tomorrow.

---

## Reproducing it

Python 3.11 or later, plus the DuckDB command-line tool for the query layer.
Python dependencies are in `requirements.txt`.

```bash
python3 spec_source.py       # fetch and parse the specification at 5 tags
python3 seed_data.py         # synthetic fixtures across three schema eras
python3 self_test.py         # generator self-test
python3 build_unified.py     # sanitise the real export, merge the layers
python3 generate_layer_c.py  # the v1.4 supplemental datasets
python3 validate.py --report # validate, and write docs/conformance-report.md
```

`spec_source.py` is the only script that touches the network. Everything
after it reads the parsed specification from `docs/spec/`, so the pipeline
runs offline and gives the same answer on any machine.

`validate.py` accepts `--list` to show every check and the version window it
applies to, `--negative` to run only the broken-data proof, and `--report`
to write the conformance report. It exits with a non-zero code when a MUST is
broken. It currently exits 1, because one is.

The query layer runs from the repository root: `duckdb < sql/queries.sql`
for showback, budget, anomaly, the savings ladder, block pricing and
commitment utilisation; `duckdb < sql/stage6_reconciliation.sql` and
`sql/stage6_coverage.sql` for the three-way tie-out and eligibility-aware
coverage; `duckdb < sql/stage7_queries.sql` for the token reconciliation,
unit economics and scheduling analysis.

---

## Layout

```
*.py           the scripts, one job each: spec_source, rules, validate,
               version_diff, seed_data, self_test, build_unified,
               generate_layer_c, check_files, publication_check,
               sanitise_stage7, and the Stage 5 to 7 tooling
sql/           the query layer, Stages 5 to 7
docs/          case study, findings, governance note, cadence and business
               cases, conformance report, readiness memo, working notes,
               and the parsed specification in docs/spec/
data/          synthetic layers, negative fixtures, supplemental datasets,
               the unified dataset, sanitised real exports, query outputs
screenshots/   redacted run output and portal evidence, one folder per stage
```

The unsanitised exports live in `data/raw/` and are never committed. The
sanitised copies in `data/raw-sanitised/` (validated) and `data/stage7/`
(reconciled) are committed only after an independent scan confirms that no
identifier from the real export survives in them.

---

## Read next

- [**The case study**](docs/CASE_STUDY.md). Why the project exists, what the
  terms mean, what was found, what each finding is in accounting language,
  and the controls an organisation should put in place because of it. About
  4,500 words with its tables; a twenty-minute read.
- [**Findings and recommendations**](docs/FINDINGS_AND_RECOMMENDATIONS.md).
  Fifteen findings, each with its evidence and whether that evidence is real
  or engineered, the FinOps Framework capability it belongs to, its impact,
  the recommendation, and where it stands. Ends with the five things to do
  first in an enterprise.
- [**Governing AI spend**](docs/GOVERNANCE_NOTE.md). Four controls in four
  paragraphs, written for the people who sign the budget.
- [**Operating cadence and business cases**](docs/CADENCE_AND_BUSINESS_CASES.md).
  What running this pipeline looks like as a routine, and two business cases
  stated the way a finance pack states them.
- [**The conformance report**](docs/conformance-report.md), generated by the
  validator on 13 September 2026. Every finding quotes its rule and links
  the specification file it came from. Its final section says what a green
  result does not mean.
- [**The readiness memo**](docs/READINESS_MEMO_1_2_to_1_4.md). What is ready
  for FOCUS 1.4 today, the itemised list of what changes when Azure ships
  it, and why the 1.4 rule on covered charges is a consolidation entry an
  accountant already knows.
- **The working notes**, Stages 4 to 8, in `docs/`. The build log: every
  finding, every decision, and the reasoning behind each, including the ones
  that were wrong first.

---

## What this is, and what it is not

This is a sandbox with one virtual machine, a storage account and a small AI
deployment, not a production estate. The total bill for the project was
$14.95 over eight weeks: $9.14 for the managed disk, $5.24 for the reserved
IP address, $0.56 for AI tokens, less than a cent of bandwidth, and nothing
for the Automation account. The volumes are small on purpose. A method that
only works at scale is not a method, and every query and check here would run
unchanged on a bill a million times larger.

Some things could not be done on the real data, and the repository says so
rather than implying otherwise.

The invoice tie-out the specification mandates cannot run on Azure's real
export as delivered, because the invoice identifier is an empty string on the
older export and the newer export's rows are not yet invoiced. It runs to the
cent on the engineered layer, which was built to the 1.4 shape for that
reason.

The validated real dataset is the 31 July 2026 export. The August and
September real rows, which carry the AI and scheduling work, were reconciled
separately in `sql/stage7_queries.sql` and are not part of the conformance
report.

The Looker Studio dashboard is public: four pages, one for each of team
showback, anomaly, budget against actual and the executive view, with every
chart naming its cost metric and one currency per view.
[Open it here](https://datastudio.google.com/reporting/18a3daeb-1c93-4f83-a24b-1a019e9465a2).
Its data is the July 2026 billing period.

Anomaly alerting was configured before the first resource existed and one
detection was exercised, but the baseline is weeks rather than months, which
makes it a crawl-stage capability and it is described as one.

The closure of the three-year reservation cannot be evaluated because the
export covers one day of its 1,096-day term. That is a short export, not a
shortfall, and the validator reports it as such.

The first billing-latency measurement is a bound rather than a fact, because
the timestamps that would have made it a fact were not logged. The second was
measured properly. Token spend was sampled at two points a week apart rather
than daily.

A timezone fault that only fails outside UTC was found by asking whether a
colleague in Germany would get the same answer. She would not have. The
comparison now reads calendar dates as written, and the proof is four
timezones producing identical results. The engineered data includes a euro
billing currency for the same reason: every aggregation keeps currencies
apart, and the coverage analysis reports a separate euro gap.

Several defects in the project's own engineered data were found by the
validator after that data had passed a fifteen-check self-test. They are
recorded rather than quietly fixed, because the validator catching them is
the evidence that it works.

Two issues for the FinOps Foundation, one omission in the specification and
one defect in the reference validator, are documented in the Stage 4 working
notes and have not yet been raised. Two others were retired before raising,
because the version diff showed them already fixed in 1.4.

Project 2 applies the same method to an AWS Cost and Usage Report and opens
next.
