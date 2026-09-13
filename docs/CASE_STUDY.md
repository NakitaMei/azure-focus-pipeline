# Reading a cloud bill the way an accountant reads a ledger

## An Azure Cost Management to FOCUS pipeline, built from a finance seat

*Portfolio Project 1. July to September 2026. Cape Town.*

---

### Abstract

Cloud bills are among the fastest-growing lines in a technology budget and
among the least well controlled. They arrive as millions of rows in a format
each provider invents for itself, they are read by engineers rather than
accountants, and the numbers on the dashboard are rarely reconciled to the
invoice. FOCUS, the FinOps Open Cost and Usage Specification, is the
industry's attempt to fix the first of those problems by giving every
provider's bill the same columns and the same rules. This project asks
whether the other two can be fixed with the discipline finance already has.

Over nine weeks, one person built a working pipeline on a Microsoft Azure
sandbox that cost $14.95 in total. It takes a real Azure export, merges it
with engineered data that reproduces the situations a small sandbox cannot,
validates the result against the FOCUS specification's own rule sentences,
ties invoices out to the cent, reconciles real AI token spend to the bill,
and states every saving against what it was measured against. Along the way
it found that the provider's export was a version behind the one announced,
that one formatting habit in the export broke 236 rules and disabled a
mandatory reconciliation, that a wizard placed real spend outside the
governed part of the estate, and that a scheduling exercise that removed
seventy per cent of a machine's running hours saved nothing at all. Each of
those has a twin in ordinary accounting practice, and the paper closes with
the controls an organisation should put in place because of them.

---

### 1. Why this project exists

Finance functions have spent a century learning how to trust a number. It is
reconciled to a source document, it is prepared under a stated version of a
standard, it separates cash from accrual, and a saving is always measured
against something. Cloud cost management, the practice the industry calls
FinOps, is roughly ten years old and has not yet inherited all of that. Bills
are consumed as data rather than as invoices. Dashboards show spend without
saying which cost they are showing. Savings are quoted without a
counterfactual. Most of the tooling that checks a cloud bill against a
standard encodes what its author believes the standard says, and nobody
reading the code can tell whether the belief is right.

The author has run the finance function of a South African media and
analytics group for several years: the reconciliations, the cut-off testing,
the audit, and the statutory versions of the numbers. The question this
project sets out to answer is practical. If those habits are applied to a
cloud bill, using the standard the industry is converging on, what do they
find, and what is different? The answer matters to anyone who signs a cloud
budget, because the controls that turn out to be missing are the cheap ones.

A second reason is honesty about scale. A sandbox with one virtual machine
and a few hundred AI requests does not look like an enterprise estate. It was
chosen deliberately, because a method that only works on large numbers is not
a method. Everything in this project is written so that the same queries,
checks and controls would run unchanged on a bill a million times larger.

---

### 2. Background: what FOCUS is, and what the words mean

FOCUS is an open specification maintained by the FinOps Foundation. It
defines a table: a fixed set of column names, what each column means, and
rules about what may and may not appear in them. A provider that supports
FOCUS lets a customer export their bill in that shape, so that an Azure bill,
an AWS bill and a Google bill can be read with the same query. The
specification is versioned. This project works with versions 1.0, 1.2 and
1.4.

Three terms recur throughout and are defined here once.

**Requirement keywords.** The specification writes its rules using a
convention borrowed from internet standards, known as RFC 2119. Under that
convention a capitalised MUST is a hard requirement, a capitalised SHOULD is
a strong recommendation that may be departed from for good reason, and a MAY
is optional. The difference matters. A bill that breaks a MUST is not
conformant; a bill that ignores a SHOULD is conformant but could be better. A
validator that treats the two alike is a bad auditor, because it either fails
good bills or passes bad ones.

**Billed cost and effective cost.** FOCUS carries two cost columns on every
row. `BilledCost` is what the invoice says: the cash. `EffectiveCost` is the
cost after a prepaid commitment has been spread across the usage it pays for:
the accrual. An accountant recognises the pair at once. A commitment purchase
is a prepayment, the usage it covers is the amortisation, and the two columns
are not expected to agree in any single period.

**Conditional rules.** Many of the specification's rules take the form "this
column MUST be empty when the charge is not related to a resource". The
condition refers to a fact about the world, not to anything in the row. A
program reading the data cannot know whether a charge is "related to a
resource"; it can only see whether a column is filled. Deciding what to do
with such rules is one of the central design problems in this project.

---

### 3. Method

The pipeline has three layers of data and one validator, and every design
decision follows from a rule a finance function would recognise.

**Real data, engineered data, and the honest label.** The Azure sandbox
produced a genuine export: one virtual machine, a storage account, an
Automation account and, later, an AI deployment. A $20-a-month sandbox never
generates a reserved-instance purchase, a tax line, a credit, a second
currency, a correction to a prior invoice, or block-priced usage, and those
are precisely the situations a finance reader cares about. So a second layer
was engineered to produce them, conformant by construction, with every row
carrying a flag that says it is synthetic. A third layer holds the three
supplemental datasets that FOCUS 1.4 introduces for invoice reconciliation,
built to that shape before Azure ships it. Every number in every document in
this project says which layer it came from.

**A validator that reads the specification rather than remembering it.** The
script `spec_source.py` fetches the specification text at five pinned
versions and parses every requirement sentence into a machine-readable rule,
recording the sentence, the file it came from and its keyword. The script
`validate.py` registers one check for each rule it can express, 166 in all,
and runs them against every dataset. Because each check cites the sentence it
enforces, a reader can trace any finding to the exact text it was derived
from. Because the severity comes from the keyword in that sentence, a MUST
produces a failure and a SHOULD produces a warning, and no one can change
that by hand.

Seven of the 166 checks cannot be expressed against a single table, because
they join the cost data to the supplemental datasets. They ask: does every
invoice identifier on a cost row exist in the invoice file; does the billed
cost per invoice sum to the invoice total; does every billing period
referenced in the cost data exist in the billing-period file; does a
commitment's amortised usage sum back to its purchase over the term the
contract file states; does a correction row refer to a closed period; is the
billing-period geometry internally consistent; and does every row land in
exactly one bucket of the coverage analysis. Those seven are the finance
bridge, and they are the reason the supplemental datasets exist.

**Refusing rules honestly.** Of the specification's 88 rules about when a
column may be empty, 70 are implemented. The remaining 18 are conditional
rules whose condition refers to a fact the row does not carry, such as
"MUST be empty when a charge is not related to a resource" or "MUST NOT be
empty when the provider supports assigning a display name". The validator
lists each of the 18 with the reason it cannot be checked. This is not a gap
in the harness. It is a gap in what any program reading a dataset can know,
and naming it is worth more than a coverage percentage that hides it. Where a
condition mixes a checkable part with an unknowable part, the harness
narrows the rule and never broadens it, because broadening fails conformant
data.

**Proving the validator detects anything.** A validator that has only ever
seen valid data has never been shown to work. A fourteen-row file of
deliberately broken records was built, each row breaking exactly one rule
and declaring which. A detection counts only when the check that fires is
the check implementing the rule the row names. All fourteen are caught that
way, and the count of incidental hits, zero, is kept as a regression signal.

**Standing rules for every query.** Six rules bind every piece of SQL in the
project, and all six are finance rules in disguise: filter on the start of a
period and never on the end; keep currencies apart in every aggregation;
never reason from the sign of a number; use billed cost for invoice questions
and effective cost for consumption questions, and say which; join on
identifiers, never on names; and compare dates as written, never through a
timezone conversion.

---

### 4. What was found

**4.1 The export was a version behind, and then it moved.** The first export
Azure delivered declared FOCUS version `1.0r2` with 96 columns, not the 1.2
the announcement implied. When the 1.2-preview export became available it
declared 105 columns and could only be created at billing-account scope, not
at subscription scope. Three columns that the older export carries as
provider extensions, prefixed `x_`, arrive as standard columns in the newer
one. A pipeline written to the announced version would have read columns
that were not there, silently. A finance reader will recognise the question
asked of every set of accounts: under which version of the standard were
these prepared? The answer sits in the export's manifest, the small JSON
document Azure writes beside each export, and the rule that followed is to
read it before reading any data.

**4.2 One habit, 236 failures, and a reconciliation that could not run.** In
the real export, the column that identifies a commitment discount holds an
empty text string on every row where it should be empty in the proper
sense, that is, null. FOCUS requires null. The validator reports this as 236
MUST failures, one per row, which sounds like a broken export and is in fact
a single habit counted 236 times. What the count does not show is worse. An
empty string is a value, so every conditional rule that asks "is this column
filled?" sees a filled column and demands values on rows that legitimately
have none, producing 354 phantom failures three columns away. And the
invoice-identifier column has the same habit, which means the reconciliation
the specification mandates, joining cost rows to invoices on that identifier,
cannot run at all, because nothing joins on a blank. The accounting twin is
posting a zero instead of leaving a line out: a placeholder that looks like a
value breaks every rule that keys on the value.

**4.3 The invoice ties to the cent, on the layer that can support it.** The
three-way reconciliation, cost rows to invoice lines to billing periods, is
the control a finance team calls a three-way match: the receipt, the invoice
and the purchase-order window. It closes to the cent on the engineered
layer. Tax, credit and purchase rows are shown as reconciling items rather
than netted away, a correction is proven to restate a closed period, and
periods are matched by their civil date. It cannot yet run on Azure's real
data as delivered, for the reason in 4.2, and the project says so rather than
implying otherwise.

**4.4 Coverage measured against the right base.** Commitment coverage, the
share of usage paid for by prepaid commitments, is 63.4 per cent on this data
if the denominator is all usage. It is 85.5 per cent if the denominator is
only the usage a commitment could cover. The naive figure would send a buyer
shopping for commitments to cover demand that is not eligible. The correct
one produces a short action list: $10.80 of eligible but uncovered demand in
dollars, and €6.62 in euros where nothing is covered at all. Utilisation is
reported separately, and the three-year reservation's utilisation is
reported as not evaluable rather than as 0.09 per cent, because the export
covers one day of a 1,096-day term and the number would measure the export,
not the commitment.

**4.5 A join that only fails outside London.** The billing-period file
carries timestamps with a timezone offset; the cost data carries timestamps
without one. A straightforward equality join between them passes on a
machine set to UTC and fails on one set to South African time; converting
both to dates fails instead for anyone west of Greenwich. It was caught by
asking whether a colleague in Germany would get the same answer. The fix
reads the calendar date as written and never converts it, and the proof is
the same set of verdicts produced under four session timezones.

**4.6 Real AI spend, reconciled to the token.** The project spent 28 cents on
a real AI workload so that the reconciliation could be real. Eight hundred
batched requests produced 1,422,991 tokens and $0.281718 in the local usage
log; the FOCUS export carried exactly the same counts and the same cost. A
second batch a week later, with identical input, tied again at 1,417,163
tokens and $0.280553. The 0.4 per cent difference in output tokens between
the two runs is the model's own nondeterminism, visible only because the
reconciliation is at the token. Two lessons for pricing followed. Every row
carries two quantities, the priced unit that finance quotes a rate on and the
consumed unit that engineering measures efficiency on, and they coincide here
only because Azure prices in fractional blocks; where a provider rounds to
whole blocks they diverge, and the gap is invisible in the cost columns. And
the batch buying mode, verified from billing, costs half the interactive
rate in exchange for a 24-hour promise that was kept in under ten minutes,
twice.

**4.7 Spend in the wrong place on day one.** The AI resource was created by a
quick-start wizard, which placed it in a resource group called
`NetworkWatcherRG`, outside the governed group, with the platform's own tags
and none of the organisation's. The spend was real and reconciled, and it was
invisible to team showback. In a one-person sandbox, on the first day of
using AI, shadow spend had already appeared. The allocation queries caught it
after the fact, because surfacing an untagged bucket is what allocation is
for. A policy restricting where AI resources may be created would have
prevented it. In an enterprise this finding scales worst of all, because
every team has a wizard.

**4.8 A schedule that saved nothing, reported as saving nothing.** An
Automation schedule switched the virtual machine off at six every evening and
at weekends, removing 118 of 168 weekly hours, or 70.2 per cent of its running
time. The bill did not move. Every cent the machine cost, before and after,
came from two meters a schedule cannot touch: the managed disk and the
reserved IP address. Compute billed zero, because a twelve-month free
allowance absorbed it. Friday and Saturday billed identically to the cent
with the machine off all Saturday. The saving is therefore $0.00, and the
project reports it as $0.00, with the counterfactual stated: the same
schedule is worth roughly seventy per cent of the machine's compute cost the
day compute starts to bill. A figure of 65 per cent that had appeared in
earlier notes without a derivation was withdrawn. A finance reader will see
fixed and variable cost, and a variance that must be measured against a
standard.

---

### 5. What the finance lens adds

None of these findings is a new idea to a finance team. Each has a twin that
has been audited for decades. The work of this project was recognising the
twin and applying it to a bill that arrives as a data file.

| FinOps finding | Its finance twin | In one line |
|---|---|---|
| Token reconciliation, usage log against bill | Control-account tie-out; supplier statement reconciliation | The subledger agrees to the control account, twice, to the token. |
| Three-way invoice tie-out | Three-way match: purchase order, invoice, goods received | Cost and Usage is the receipt, Invoice Detail the invoice, Billing Period the order window. Tie all three or you tie nothing. |
| Effective cost against billed cost | Accrual against cash; prepayment amortisation | Purchases are the prepayment; usage is the amortisation; never expect the two to agree in one period. |
| Commitment closure | Amortisation must sum back to the invoice over the term | Over one day of a three-year term it cannot. Reporting 0.09 per cent utilisation reports the length of the export. |
| Covered and covering charges (FOCUS 1.4) | Intercompany elimination in consolidation | Two views of one economic event; letting both carry cash counts the money twice. |
| Billing latency | Cut-off testing; period-end close timing | A transaction takes time to reach the ledger. I know which of my measurements is a bound and which is a fact. |
| Absent dates in the export | Completeness assertion; a gap in the bank statement | Missing days are not zero days. An average over the days present silently excludes the outage. |
| Fixed floor against compute | Fixed against variable cost | Scheduling is a variable-cost lever. The floor does not move when the machine is switched off. |
| Counterfactual savings | Variance against standard | A saving states what it is measured against. List price less contracted is procurement's number; contracted less effective is FinOps' number. |
| Blended cost per thousand tokens | Product-mix variance | A blended rate is a mix statement, 98.65 per cent output at four times the input rate, not a price. |
| Quota | Delegation-of-authority limits | Capacity is provisioned, not assumed. The model on day one is decided by quota before it is decided by price. |
| Shadow resource | Procurement bypass; an off-system purchase order | Money flowed through a resource nobody set up on purpose. Allocation caught it because that is what allocation is for. |
| Version drift | Which version of the standard the numbers are prepared under | Read the manifest the way you read the accounting-policies note. |
| MUST against SHOULD | Statutory requirement against best-practice guidance | One is a breach and one is a warning. A validator that treats them alike is a bad auditor. |
| Empty string instead of null | Posting 0.00 instead of leaving the line out | A placeholder that looks like a value breaks every rule that keys on the value. |
| Key rotation | Changing the bank token after a lost card | Exposure logged three times; the credential regenerated before anything went public. |

---

### 6. Safeguards: what to put in place because of this

Findings are only useful if they change what an organisation does. These are
the controls the project recommends, in the order they should be adopted,
each with the finding that earned it.

**Before ingesting any bill, read the manifest and gate on the version.**
Every rule that depends on a specification version should be gated on the
version the export actually declares, row by row, and the specification diff
should be re-run at every new tag. The readiness memo in this repository does
that for the move to FOCUS 1.4: it lists, mechanically, the two checks to
rewrite, the five citations to re-read, the one detection mechanism to
re-key and the one interim column to retire. A version upgrade should be an
afternoon, not an archaeology project. (Finding 4.1.)

**Normalise placeholders at ingestion.** One line that turns empty strings
into nulls is the difference between a reconciliation that runs and one that
cannot. It should live at the point of ingestion, and the placeholder sweep
that detects the habit should run only on the raw layer, never on the
normalised one, where it would report zero and read as a pass. (Finding
4.2.)

**Make allocation a policy, not a report.** Restrict where AI and other
high-variance resources may be created, require the organisation's tags at
creation, and surface the untagged bucket as its own line in every showback
view. A dashboard that drops untagged spend is a dashboard that hides the
finding. (Finding 4.7.)

**Report coverage against coverable spend, and publish the action list.**
The naive coverage figure should be treated as a data-quality check on the
eligibility flag, not as a KPI. FOCUS 1.4 adds a native column for
eligibility; until a provider ships it, derive the flag from documented rules
and disclose the rows where it does not apply. (Finding 4.4.)

**Compare periods by civil date.** Never let a session timezone touch a
billing period. Generate plain dates at source where possible, and prove any
period logic under more than one timezone before it ships. (Finding 4.5.)

**Keep a usage subledger for every AI workload, and reconcile it monthly.**
The provider's export is the control account; the application's own log is
the subledger. Reconcile at the token, not at the dollar, so that
nondeterminism and rounding show up as what they are. (Finding 4.6.)

**Treat quota, buying mode, placement and credentials as budget controls.**
The enqueued-token limit on a batch deployment is the only AI-native budget
that exists today; set it deliberately. Default latency-tolerant work to
batch. Rotate a credential on every logged exposure and screen every
published artefact for the class. (Findings 4.6 and 4.7, and the governance
note.)

**Log first-seen timestamps, forward, every time.** Observability that was
not logged cannot be recovered. The cheapest control in this list, and the
one the project got wrong first. (Section 7.)

**State every saving against its counterfactual, and report zero as zero.**
Attribute rate savings and usage savings separately; never take credit for
both. When a lever moves a meter that bills nothing, say so. (Finding 4.8.)

---

### 7. What did not work, kept on the record

A method is only trustworthy if its failures are visible. Five are recorded
here because they changed how the project was done.

The kick-off log template for the AI work was left blank on the day, so the
time at which the first batch's charges became visible in the portal and in
the export was never captured, and the export's overwrite mode then destroyed
the evidence. The first billing-latency sample is therefore a bound, roughly
four and a half days, rather than a measurement. The second sample was
forward-measured from a hand-logged submission time and landed on the first
export run after the usage, within eleven hours.

The usage log's clock was misread as local time when it was in fact UTC; the
file viewer had rendered it locally. The reading was retracted in writing.

The API key for the AI deployment was exposed three times in one week,
through a chat paste, a screenshot and a second paste, despite a design that
keeps values in the environment rather than in files. It was regenerated
before publication and the exposures are logged.

After the September export was overwritten with new rows, a scheduling query
that had filtered only on currency and charge type silently absorbed the AI
token spend into the virtual machine's figures. It was found in review and
fixed with a date ceiling and a resource exclusion; the output that shows the
error is kept as an exhibit.

And the sanitiser that removes identifiers before publication verified the
data file it wrote but not the manifest beside it, which still carried the
subscription identifier. The publication checker caught it on the first run
against the folder that was about to ship, which is exactly why a checker
runs last.

---

### 8. Limitations

This is a sandbox, not a production estate, and the volumes are small by
design. The analytical richness of the reconciliation and coverage work sits
on engineered data, because the real sandbox could not produce the
situations; every such number is labelled. The anomaly baseline is weeks
long, not months, and is stated as a crawl-stage capability. The token spend
was measured at two points a week apart rather than daily. The official FOCUS
validator was run alongside and catches two recommendation-level rules this
harness does not; both are implementable and neither is implemented. The
three-year reservation's closure cannot be evaluated on this export, and is
reported as such.

---

### 9. Where it sits in the FinOps Framework

| Capability or concept | Demonstrated by | Data |
|---|---|---|
| Data ingestion and normalisation | Three-layer build; placeholder normalisation; row-level version gating; the specification-parsing validator | real and synthetic |
| Reporting and analytics | Thirteen queries; a four-page dashboard where every chart names its cost metric | synthetic and real |
| Allocation and showback | Team showback with the untagged bucket as its own line; the shadow-resource finding | real |
| Invoicing and chargeback | Three-way tie-out to the cent; reconciling items; correction cut-off | synthetic, FOCUS 1.4 shapes |
| Anomaly management | A detector on effective cost that saw an incident a cash detector would have missed; baseline stated as crawl | synthetic |
| Budgeting and forecasting | A $20 budget with straight-line pace; the enqueued-token limit as the AI budget; absent dates as a forecasting hazard | real |
| Rate optimisation | Batch at half the interactive rate, verified in billing; a savings ladder with each rung's counterfactual; coverage of coverable spend | real and synthetic |
| Workload optimisation | Start/stop schedule with $0.00 measured and the counterfactual stated; autoscale configured and deliberately not deployed | real |
| Unit economics | Two quantities on every AI row; rate stable, job cost variable | real |
| The FOCUS specification | 166 checks parsed from the text at pinned versions; 18 refused with reasons; the 1.2 to 1.4 move itemised; the promotion of provider columns observed live | real |
| AI value | Buying mode, quota, placement and credentials treated as controls; token-level reconciliation; provisioned throughput mapped to the commitment columns but not measured | real |
| Governance | A four-control governance note; a publication checker that runs last | |

---

### 10. Conclusion

The question was whether finance discipline, applied to a cloud bill under
the standard the industry is adopting, finds things that engineering-led
tooling does not. It does, and the things it finds are not exotic. A bill
prepared under a different version of the standard than the one expected. A
placeholder that breaks the rules that key on it. A reconciliation that
cannot run until the placeholder is fixed. A coverage ratio on the wrong
base. A join that depends on where the analyst is sitting. Spend that landed
outside the governed estate on the first day. A saving that was really zero.
Each has a name in accounting, and each has a control that costs almost
nothing to put in place.

The project's own bill was $14.95. Its most useful output is not the
pipeline. It is the list of controls in section 6, and the habit that
produced them: reconcile to a source document, state the version, separate
cash from accrual, measure savings against a standard, and keep the mistakes
on the record.

---

*Project 2 applies the same method to an AWS Cost and Usage Report, where the
provider's export and its invoice are known not to match. Two issues for the
FinOps Foundation, one specification omission and one defect in the reference
validator, are documented and waiting to be raised.*
