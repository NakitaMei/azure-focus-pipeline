# Stage 7 — Kick-off Working Notes

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 7 (kick-off only — analysis remains) · **Kick-off status: COMPLETE**
**Date:** 31 August 2026 · All times UTC unless marked SAST (SAST = UTC+2)
**Written so nothing is lost. Stage 6 proceeds in parallel; Stage 7 analysis
resumes days 4–5 once billing data has landed.**

---

## Plain-English summary

Stage 7 has one external dependency nothing can compress: Azure billing
latency (8–24h, sometimes 48h, before spend appears in the FOCUS export).
Today we started every clock. In one afternoon: the subscription was found
**disabled** (free credit expired) and reactivated to pay-as-you-go; both
FOCUS exports were rebuilt from scratch (1.0r2 into the loader's original
path, plus a separated 1.2-preview comparison export); an Azure OpenAI
deployment was stood up after a quota-and-deprecation gauntlet and **800
requests of token spend were generated and billed via Global Batch at half
price, with a local CSV audit trail**; and the VM start/stop automation was
built, round-trip tested, and armed — first unattended stop fires tonight
18:00 SAST, weekends off for free.

The gauntlet itself produced more findings than the plan expected: a
disabled-subscription export gap, a model-lifecycle ladder crossed in one
afternoon, quota as the real constraint on model choice, batch-vs-interactive
as a pricing lever, resource sprawl from a quick-create wizard, and a
free-tier wrinkle that reframes (improves) the scheduling-saving story.

---

## What Stage 7 wants to achieve (unchanged from master v3 / completion plan)

1. **Scheduling extension** — Automation start/stop 18:00–08:00 + weekends;
   the off-hours saving (70.2% of compute-hours) calculated with an explicit
   counterfactual;
   scale-set autoscale screenshot + paragraph.
2. **AI-cost extension** — token costs as the virtual PricingCurrency pair +
   `x_` token columns, framed as the **v1.5 on-ramp**; **cost per 1K tokens**
   with the PricingQuantity denominator (Finance view) and the
   consumption-efficiency variant (Engineering view); 300 words on AI cost
   governance.
3. **The latency finding** — documented gap between spend generation and its
   appearance in the FOCUS export, with exact UTC timestamps.

Today delivered the *inputs* to all three. The *analysis* is days 4–5 work.

---

## Timeline of actions (UTC)

| Time (UTC) | Action |
| --- | --- |
| ~11:05 | Subscription found **Disabled** (free credit expired). Banner + Status confirmed on Overview. |
| ~11:10 | Upgraded to pay-as-you-go (Azure Plan, no support plan). Status → Active. Card now billed for real. |
| ~11:15 | Post-reactivation checks: VM Running; budget `budget-p1-sandbox-20usd` intact ($20/mo, billing-account scope, alerts 50/80/100% actual + 100% forecast, recipient confirmed). |
| 11:59 | **1.0r2 FOCUS export recreated and run.** Name `focus-export-p1-sandbox-focus-cost` (identical to Stage 1 name — the name is part of the blob path, so new runs land where loader.py already globs). Container `focus-exports`, directory `exports`, Parquet/Snappy, daily MTD, overwrite ON. |
| 12:02 | **1.2-preview export created and run** — only selectable at **billing-account scope** (blocked at subscription scope). Name `focus-export-p1-sandbox-12preview`, directory `exports-12-preview` (deliberately separated). |
| ~12:45–13:10 | Azure OpenAI resource hunt: third-party marketplace near-miss ("Azure OpenAI Monitor", ECF Data LLC — NOT created); first-party resource `oai-p1-sandbox` created in rg-p1-sandbox (Sweden Central); Foundry quick-create then produced a SECOND resource `nakitameiring-6066-resource` outside the sandbox RG. The batch ran on the latter. |
| ~13:00–13:15 | Model selection gauntlet: gpt-4o-mini **Deprecated** → gpt-4.1-nano **Legacy** → gpt-5-nano current but **insufficient quota** (Global Standard, all versions) → gpt-4.1-nano also quota-blocked on Global Standard → **Global Batch had quota**. |
| 13:16 | **Deployment created:** `gpt-4.1-nano-1`, model gpt-4.1-nano v2025-04-14, type **GlobalBatch**, enqueued-token limit 2,000,000, dynamic quota off, guardrails DefaultV2, on `nakitameiring-6066-resource`. |
| **13:28:28** | **Token batch submitted.** 800 chat-completion requests (~1500-word essays, max_completion_tokens 2000). Input file `file-d65ac7e5a72f4b4284b6b526a5ffb887`. **Batch id `batch_128040f3-3a41-41da-a291-b30561680e2f`** (saved to batch_id.txt). ← **The billing-latency clock starts here.** |
| ~13:34 | Batch **completed** (validating → in_progress → finalizing → completed in ~6 minutes against a 24h window). Totals to be pulled with the `check` command (see Open items). |
| ~13:50 | Automation account `auto-p1-sandbox`: system-assigned managed identity ON; role **Virtual Machine Contributor** (near-miss: dropdown first offered "Classic Virtual Machine Contributor" — wrong, legacy-VM-only) scoped to rg-p1-sandbox. |
| 13:57 / 14:02 | Runbooks **Stop-SandboxVM** / **Start-SandboxVM** created (PowerShell, runtime 7.2), code pasted via Edit-in-portal (creation flow lands on Overview with an EMPTY draft — easy trap), Published. |
| 14:05:31–14:06:32 | **Test stop:** job Completed, operation Succeeded 14:06:18–14:06:32 (14 seconds). VM verified Stopped (deallocated). |
| 14:10:18–14:11:32 | **Test start:** job Completed, Succeeded. VM verified Running. Round trip proven. |
| ~14:20 | Schedules created and linked: **Nightly-Stop** (daily 18:00 SAST, no expiry) → Stop-SandboxVM; **Weekday-Start** (weekly Mon–Fri 08:00 SAST, from 01/09) → Start-SandboxVM. Both showing Status On with correct Next run. First unattended stop: **tonight 18:00 SAST**. |

---

## Key findings (banked for the case study / governance note)

1. **F-K1 · Disabled-subscription export gap.** Free credit expired → Azure
   disabled the subscription (~21 Aug) → no metering and no export runs until
   reactivation (31 Aug). The Aug 21–31 hole is caused by *subscription
   state*, not workload. Real-world S6: zero-cost days exist and must be
   handled, never treated as the baseline. MTD rerun backfills the period as
   true zero-usage days.
2. **F-K2 · Model lifecycle ladder, crossed in one afternoon.** The July
   master spec chose gpt-4o-mini; by execution day (six weeks later) it was
   **Deprecated**, its successor gpt-4.1-nano already **Legacy**, and the
   current tier (gpt-5-nano) inaccessible for quota reasons. AI unit-economics
   baselines can be obsolete within a quarter. Core exhibit for the 300-word
   governance note.
3. **F-K3 · Quota, not price, decided the model.** Fresh pay-as-you-go
   subscription had zero Global Standard TPM for both nano models (all
   versions). Access to AI capacity is *provisioned, not assumed* — model
   choice on day one is a provisioning exercise before it is a cost exercise.
   Enterprises end up on older/other models for exactly this reason.
4. **F-K4 · Batch as a pricing lever.** The only deployment type with quota
   (Global Batch) bills at **50% of interactive** for a 24h turnaround —
   which actually completed in ~6 minutes. Same tokens, two prices:
   PricingCategory thinking applied to AI. Also note: file-in/file-out is a
   different *buying mode*, not just a discount.
5. **F-K5 · Resource sprawl from a quick-create wizard.** Two Azure OpenAI
   resources now exist: `oai-p1-sandbox` (rg-p1-sandbox, Sweden Central,
   idle, $0 while unused) and `nakitameiring-6066-resource` (created by
   Foundry quick-create OUTSIDE the sandbox RG — location to confirm, URL
   suggested NetworkWatcherRG). All token spend lands on the second, in a
   different resource group and region than the rest of the estate → the
   showback/allocation queries will surface it. Organic shadow-IT in a
   one-person sandbox, same afternoon it was warned about (the ECF Data
   third-party marketplace near-miss is part of the same finding).
6. **F-K6 · Free-tier reframe of the scheduling saving.** The B2ats v2 VM's
   compute bills $0 inside the 12-month free 750 hrs/month grant. The real
   August bill is entirely the **OS disk ($4.36) + public IP ($2.52)** —
   precisely the components a start/stop schedule cannot touch. Honest Stage
   7 framing: *capability demonstrated and elapsed days measured; monetary
   saving $0.00 during the free-tier window; at pay-as-you-go rates the same
   schedule would save ≈70% of compute cost (70.2% of compute-hours) — and
   disks/IPs are the floor no
   schedule reaches.* Stronger than the naive claim (claims not yet true get
   removed, not softened). Also: stop = **deallocate** (billing stops); an
   in-guest OS shutdown does not deallocate and saves nothing.
7. **F-K7 · 1.2-preview export scope + hollowness.** Selectable only at
   billing-account scope, not subscription scope, weeks after announcement —
   live illustration of the adoption guidance the whole version strategy
   rests on. Microsoft's own note: several 1.2-required columns are exported
   as null until supporting capabilities ship. Both facts → readiness memo.
8. **F-K8 · RBAC one-word near-miss.** "Classic Virtual Machine Contributor"
   sits beside "Virtual Machine Contributor" in the dropdown; the Classic
   role cannot act on ARM VMs, and the failure mode is a silently failing
   scheduled job at 18:00, not an error at assignment time.
9. **F-K9 · Month-boundary export behaviour (to verify).** Batch spend from
   31 Aug will mostly land as August charges; the daily MTD export re-runs
   prior-month files in early September to catch late-arriving charges. The
   OpenAI cost is expected to appear in the *August* files via those runs —
   do not panic on 1 Sep when MTD rolls to September.
10. **F-K10 · Key exposure → rotation trigger.** The API key was pasted into
    chat during setup. Treated as leaked-adjacent: **regenerate Key 1 before
    Stage 8 publication** (resource → Keys → Regenerate), then re-export the
    new value. publication_check.py exists for exactly this class of risk;
    the key was never written into any project file (env vars only).

---

## Configuration record (verbatim, for reproduction)

**Exports** (both daily MTD, Parquet, Snappy, overwrite ON, storage
`stp1sandbox`, container `focus-exports`):
- `focus-export-p1-sandbox-focus-cost` · dataset 1.0r2 · directory `exports`
  · created at billing scope shown as "Nakita Meiring" · first run 11:59 UTC.
  Path shape: `focus-exports/exports/focus-export-p1-sandbox-focus-cost/<YYYYMMDD-YYYYMMDD>/…`
  (existing folders 20260701-20260731, 20260801-20260831 — the new export
  writes into the same tree because the NAME matches Stage 1's).
- `focus-export-p1-sandbox-12preview` · dataset 1.2-preview · directory
  `exports-12-preview` · first run 12:02 UTC. Never mix with the 1.0r2 tree.

**Azure OpenAI**
- Active resource: `nakitameiring-6066-resource` (Foundry quick-create;
  RG/location to confirm — see Open items).
  Endpoint (base for SDK): `https://nakitameiring-6066-resource.services.ai.azure.com/`
  (portal displays it with `/openai/v1/responses` appended — strip the path;
  hostname is services.ai.azure.com, NOT openai.azure.com).
- Idle resource: `oai-p1-sandbox`, rg-p1-sandbox, Sweden Central, S0, no
  deployments, $0. Decision deferred to teardown (Stage 8).
- Deployment: `gpt-4.1-nano-1` · gpt-4.1-nano v2025-04-14 · GlobalBatch ·
  enqueued limit 2,000,000 · created 13:16 UTC.
- Assumed batch prices used for the local estimate (verify at analysis
  time): $0.05 in / $0.20 out per 1M tokens (= 50% of Global Standard
  $0.10/$0.40).

**Scripts & artifacts** (project folder)
- `generate_tokens_batch.py` — submit/check modes; env-var config
  (AZURE_OPENAI_ENDPOINT / _KEY / _DEPLOYMENT); builds `batch_input.jsonl`;
  writes `batch_id.txt`; appends completed totals to
  `token_generation_log.csv`. **The CSV + batch output are the local half of
  the token reconciliation** vs the export's x_ token columns / BilledCost.
- `generate_tokens.py` — interactive-deployment variant; unused (quota);
  keep for the day Standard quota exists.
- Env vars are session-scoped: re-export all three before any later `check`
  in a fresh terminal.

**Automation** (`auto-p1-sandbox`, North Europe — cross-region to the VM is
fine; runbooks act via the control plane)
- Identity: system-assigned, ON. Role: Virtual Machine Contributor @
  rg-p1-sandbox.
- Runbooks (PowerShell 7.2, Published):
  - Stop-SandboxVM: `Connect-AzAccount -Identity | Out-Null` +
    `Stop-AzVM -ResourceGroupName "rg-p1-sandbox" -Name "vm-web-01" -Force`
  - Start-SandboxVM: same connect + `Start-AzVM …` (no -Force)
- Schedules (SA Standard Time, no expiry): Nightly-Stop daily 18:00 →
  Stop-SandboxVM; Weekday-Start Mon–Fri 08:00 (from 01/09) →
  Start-SandboxVM. Friday's stop holds through the weekend by construction.
- Portal quirks recorded: runbook creation lands on Overview with an empty
  draft (must Edit → paste → Save → Publish); the Link-to-schedule pane
  requires opening "Parameters and run settings" (even with 0 parameters)
  before OK enables.

---

## Open items / daily cadence until Stage 7 analysis

- [x] **Pull batch totals** — done: batch 1 logged 31 Aug 13:40Z, batch 2
      07 Sep 04:58Z; recorded in STAGE7_KICKOFF_LOG §B.
- [x] **Second batch** — fired 07 Sep, not 1 Sep (6-day slip, recorded in
      the LOG); two-point daily grain, Aug 31 + Sep 7.
- [x] **Daily** glance — not executed as a cadence: batch-1 first-seen
      times are unrecoverable (stated as bounds), batch 2 forward-measured
      instead (LOG §B; analysis §4).
- [x] **First unattended round trip** — confirmed: scheduled stop 31 Aug
      16:00:08Z, start 01 Sep 06:00:09Z; all jobs Completed through 06 Sep
      (LOG §C).
- [x] **Verify manifests** — verified 13 Sep: 1.0r2 export declares 1.0r2,
      96 columns; 1.2-preview export declares 1.2-preview, 105 columns, at
      billing-account scope (Stage 8 F-S8-9).
- [x] **Confirm `nakitameiring-6066-resource` RG + region** — confirmed from
      the export ResourceId: networkwatcherrg (F-K5 stands; LOG §B).
- [x] **Rotate the OpenAI key** — rotated 07 Sep (F-K10 closed).
- [x] Autoscale screenshot + paragraph — delivered in the Stage 7 analysis
      (§11).
- [x] Budget figure $20/mo: CONFIRMED (screenshot banked); Stage 5 open item
      cleared.

## What Stage 7 analysis (days 4–5) will build on this

Latency finding with exact timestamps (F-K9 shape) · token reconciliation
(CSV ↔ x_TokenCount/x_TokenModel ↔ BilledCost) · cost per 1K tokens, Finance
(PricingQuantity denominator) and Engineering (consumption) views — with the
batch-vs-interactive price pair as a second axis (F-K4) · scheduling
saving with the free-tier counterfactual framing (F-K6) · 300-word AI
governance note drawing on F-K2/K3/K4/K5/K10 · GPU utilization only if a GPU
workload enters scope (currently none).

## Standing rules — unchanged and applied today

Claims not yet true get removed, not softened (F-K6 framing). Sandbox is a
learning tool, not portfolio data. x_Synthetic = true on every synthetic
row. Warnings ≠ failures. Working method held: one chunk at a time,
screenshots verified, errors owned (the placeholder-key 401 was ours, twice).
