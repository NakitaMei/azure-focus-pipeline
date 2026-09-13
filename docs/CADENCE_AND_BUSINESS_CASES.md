# Operating cadence and two business cases

A pipeline that runs once is a demonstration. This document describes what
this one looks like as a routine, and then makes two spending cases the way a
finance pack makes them: what it costs, what it returns, what the return is
measured against, and when the answer changes.

## Part 1. The operating cadence

Every rhythm below exercises a control, and every control was earned by a
finding in this project. The numbers in brackets refer to the findings
document. The cadence is deliberately light. Most of it is a glance and a
question, and the heavy items, the monthly tie-out and the specification
diff, are the ones a finance function already runs in some form.

| Rhythm | Do | Control | Why (finding) |
|---|---|---|---|
| **Every export tick** (daily, ~01:56 UTC for 1.0r2, ~16:08 UTC for 1.2-preview) | Log the run id and the first-seen date of any new resource or meter. Compare row count to yesterday. | Observability; presence latency | First-seen timestamps cannot be recovered after the fact (F&R #12); an outage shows as absent dates, not zero rows (#11). |
| **Daily** | Glance at the untagged line in the showback query. Any new resource outside the governed group is a same-day conversation. | Allocation | The shadow AI resource (#6). |
| **Weekly** | Run `validate.py`. A new MUST failure is a provider change or a pipeline change: find out which before Friday. Run the anomaly query; the baseline is short, so read it, do not tune it. | Data quality; anomaly management | 236 failures from one habit (#2); crawl-stage anomaly baseline. |
| **Monthly, on invoice** | Three-way tie-out per `InvoiceId` to the cent. Reconciling items (tax, credit, purchase) listed, never netted. Token subledger reconciled to the export for every AI workload. Coverage of coverable spend, with the uncovered-eligible action list. | Invoicing & chargeback; rate optimisation | The tie-out (#3); exact token ties (#4); coverage vs naive (#8). |
| **Monthly, after close** | Re-run the scheduling meter anatomy: is compute still $0.00? The day it is not, the schedule's saving switches on and is reported against the compute meter only. | Workload optimisation | $0.00 saving with a stated counterfactual (#7). |
| **On every specification tag** | `python3 spec_source.py` at the new tag; `version_diff.py` against the pinned one. Re-cite any check whose sentence moved. Retire any community issue already fixed upstream before raising it. | Version management | Drift observed twice (#1); two issues retired before raising (Stage 4 §31.2). |
| **On every provider change** (new dataset version, new scope, new export) | Read the manifest before the data. Confirm `dataVersion`; run the loader's schema check; do not migrate on announcement. | Data ingestion | 1.0r2 vs 1.2-preview (#1). |
| **Before anything publishes** | `publication_check.py`, last, against the tree that ships. Screenshots by hand. | Governance | The manifest leak the checker caught (#15); three key exposures (#14). |
| **Quarterly** | Re-read the readiness memo against what Azure now ships. Review AI quotas and enqueued-token limits as budget lines. | Budgeting; planning | 1.4 readiness itemised; quota as the first control. |

Three things about the cadence are worth saying in words.

The daily export tick is the heartbeat, and the only thing to do at each
tick is to write down what arrived and when. This project lost its first
billing-latency measurement because nobody wrote that down on the day, and
the export's overwrite mode then removed the evidence. The cost of the
control is one line in a log; the cost of not having it is a fact that
becomes a bound forever.

The monthly items are the finance function's own month-end, applied to the
cloud bill. The three-way tie-out is a three-way match. The token subledger
reconciled to the export is a supplier-statement reconciliation. Coverage of
coverable spend is a ratio on the right base. None of these needs a new
skill; they need the existing skill pointed at a new ledger.

The version items are the ones most often missing from cloud cost
programmes, and they are the ones this project found the most surprising.
The specification moves; the provider moves separately, and later; and the
only defence is to read the manifest before the data and to re-run the diff
every time the standard changes.

---

## Part 2. Two business cases

### Business case A. Scheduling the development machine

**The proposal.** Keep the Automation schedule that switches the sandbox
virtual machine off at six every evening and at weekends, and apply the same
pattern to any non-production machine.

**What it costs to implement.** One Automation account, two runbooks, two
schedules and one role assignment. Setting it up took under an hour. The
Automation service itself billed nothing across the measured period, and the
job history is the audit trail, so there is no ongoing effort.

**What it saved, measured: $0.00.** The machine's bill in the August baseline,
running around the clock, was $0.3275 a day. In the scheduled September
period it was $0.3344 a day. Every cent in both periods came from the managed
disk and the reserved IP address. Compute billed nothing, because a
twelve-month free allowance of 750 hours a month absorbs it. Friday and
Saturday billed identically to the cent with the machine switched off all
Saturday. The schedule works; it simply has nothing to save yet.

**The counterfactual, stated.** The schedule removes 118 of 168 weekly hours,
which is 70.2 per cent of the machine's running time. At pay-as-you-go rates
for this machine class, hours off are cost off, so the same schedule is worth
roughly seventy per cent of the machine's compute cost from the day compute
starts to bill. The disk and the IP address are untouched in every scenario. A
schedule is a lever on variable cost only; the fixed floor does not move.

**When the answer changes.** When the free allowance ends, which for this
subscription is around July 2027. Or when the machine is resized beyond the
class the allowance covers. Or for any machine that never had an allowance.
On the sandbox machine's own list price of $8.91 a month, seventy per cent is
about six dollars, and nobody would write a business case for it. On a fleet
of fifty development machines at a few hundred dollars each, the same seventy
per cent is the business case, and the schedule is already written.

**Recommendation.** Approve, at no cost, as a capability with a conditional
return. Report the saving against the compute meter only, and report zero as
zero until it is not.

**What this is not.** It is not autoscaling. Autoscaling responds to demand
rather than to the clock, and every instance it adds multiplies the fixed
per-instance meters that this project showed dominate small workloads. The
autoscale configuration was captured and deliberately not deployed for that
reason.

### Business case B. Coverage measured against coverable spend

**The proposal.** Replace the headline "commitment coverage" figure with
coverage of coverable spend, and publish the list of eligible but uncovered
demand beside it.

**The two numbers.** Commitment coverage is the share of usage that prepaid
commitments pay for. On the July dataset, measured against all usage, it is
63.4 per cent. Measured against only the usage a commitment could cover, with
unused commitment excluded from the demand, it is 85.5 per cent. Same
numerator, two denominators, and only the second respects eligibility.

**Why the gap is money.** The naive figure implies that roughly a third of
usage is uncovered, and it would send a buyer looking for a commitment to
cover it. The demand a purchase could actually address is $10.80 in dollars,
on one resource, and €6.62 in euros, where nothing is covered at all. The rest
of the apparent gap is demand that no commitment can cover. Buying against it
is money spent for nothing, and it is exactly what the naive figure invites.

**What it costs to implement.** One flag per row, with three values:
eligible, ineligible, and not applicable. The third value matters and is
disclosed rather than folded into ineligible, because a row where the concept
does not apply is a different thing from a row that fails it. FOCUS 1.4 adds
a native column for this; until a provider ships it, the flag is derived from
documented rules. The query change is one column reference.

**What it returns.** A correct purchase decision, or, as here, the knowledge
that the next purchase should be small and specific. Utilisation is reported
separately so that unused commitment is not counted twice: 83.1 per cent on
the one-year reservation whose term was fully observed, and not evaluable on
the three-year reservation, of which the export saw one day in 1,096.

**Recommendation.** Adopt the coverable denominator as the reported figure.
Keep the naive figure only as a data-quality check on the flag itself, never
as a performance indicator.
