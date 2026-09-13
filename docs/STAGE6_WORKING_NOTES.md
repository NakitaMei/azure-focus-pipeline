# Stage 6 — Working Notes (full detail)

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1)
**Stage:** 6 — v1.4 alignment layer
**Status:** Chunks 1–3 COMPLETE and verified locally · Chunk 4 (readiness
memo) pending one input (version_diff.py output)
**Sessions:** 31 Aug 2026 (pre-flight, eligibility decision), 1 Sep 2026
(regeneration, Chunks 1–2), 2 Sep 2026 (Chunk 3)
**Binding throughout:** master v3 §2.1 + §5.1, Amendment 1 (A3.2, A3.3,
A4), Stage 5 findings S1–S6, and — from this stage — S7.

---

## Plain-English summary

Stage 6 proves the pipeline behaves like a v1.4 pipeline before Azure ships
v1.4: the money ties to the cent across Cost & Usage, Invoice Detail and
Billing Period; commitment coverage is measured against coverable spend
only; and the guarantees were then promoted from queries-run-once into
harness checks that run on every build. Along the way the stage produced
one new binding finding (S7 — period comparisons must be done at
civil-date grain, never through timezone conversion), demonstrated
generator determinism across machines, caught its own splitter bug class
three times in three costumes, and accidentally demonstrated the
absent-authority behaviour of the new checks in a live run. Every anomaly
found was documented, not fixed.

---

## 0 · Pre-flight (31 Aug, before any chunk ran)

Performed in-session against the uploaded `focus_unified` (204 × 114, the
pre-fix build) and the three Layer C CSVs, so Chunk 1 shipped pre-verified:

- Tie-out: invoice INV-2026-07-0001 total in invoice_detail = 0.24 (usage
  line) + (−1.85) (correction line) = **−1.61 USD**; the 2 CU rows carrying
  that InvoiceId sum BilledCost to **−1.61** exactly. Ties to the cent.
- Row accounting: 204 = 2 invoiced + 10 legacy-era + 192 July
  not-yet-invoiced (of which 3 Tax/Credit/Adjustment, 2 Purchases, 187
  usage; EUR usage 2 rows kept separate).
- Legacy era: the 10 pre-1.2 rows carry **x_InvoiceId = INV-2024-03-0001**
  with root InvoiceId correctly null by era. **No invoice_detail
  counterpart exists** for that invoice — the v1.4 supplemental datasets do
  not reach back into the pre-1.2 era. Documented reconciling item; feeds
  the readiness memo.
- Interim-invoice inconsistency: INV-2026-07-0001 is **Issued (9 Aug)**
  against billing period 2026-07 whose status in billing_period is
  **Open** (LastUpdated 2026-08-01). One sentence for the memo; not fixed.
- Third CommitmentDiscountId `res-basv2-legacy-2023`: one legacy Used row,
  **no contract_commitment record** — era-boundary orphan.
- Term closure, 1yr: Used 61.80 + Unused 12.60 = 74.40 = purchase
  BilledCost = contract cost. Exact. Known quirk stands: description says
  "1-year", recorded term 2026-07-01→2026-08-01 (31 days) — trust the
  period columns.
- 3yr all-upfront: purchase 2,628.00 vs 2.40 amortised in one observed day
  of a 1,096-day term — closure holds only over the full term; report
  in-progress, never failure.
- **x_CommitmentEligible absent from all 114 columns** — the one genuine
  Stage 3 gap. Blocked D2 (coverage). Two remedies offered: (a) seed-data
  fix (spec-correct per Amendment A4: "derive eligibility from an
  x_CommitmentEligible flag in the seed data and say so"), or (b) a
  clearly-labelled SQL view deriving eligibility at query time with a
  README disclosure. **Nakita chose (a), explicitly preferring the whole
  file fixed properly over patchwork.** (b) recorded here for completeness:
  it would have faked the flag at query time from documented rules instead
  of placing it in the data; moot after the decision.

---

## 1 · The seed_data.py fix (31 Aug / run locally 1 Sep)

### 1.1 What was added

`x_CommitmentEligible` (Boolean, nullable) joined `COLUMNS_X_FIXTURE`
alongside x_TokenCount / x_TokenModel, with a documentation block defining
**three-valued semantics in which the NULL carries meaning**:

- **True** — a Usage row a commitment discount could cover under the
  dataset's documented rule: compute (Virtual Machines service) that is
  not spot. Committed usage is trivially True — it IS covered.
- **False** — Usage nothing could cover here: storage, network, tokens,
  marketplace, App Service, and spot (Dynamic) compute. A deliberate
  simplification — real Azure sells reservations for some of these — and
  **the simplification is the disclosure**.
- **None** — concept not applicable: non-usage rows (Purchase, Tax,
  Credit, Adjustment); Unused-commitment rows (no resource demand — they
  belong to utilisation, not coverage); and every row of an era predating
  the flag (pre-1.2 legacy; real 1.0r2). The coverage query must say so,
  never silently treat null as False.

### 1.2 Row-by-row assignment (16 touch points, whole file delivered)

Chunk 1 fixtures: 31 reservation Used rows → True; 21 Unused rows → None
(by omission, per file convention: only True/False set explicitly);
purchase row → None. Chunk 2: correction row (storage usage) → False;
in-period network rebate → False; Tax/Credit/Adjustment → None. Chunk 3:
block-priced storage ops ×2 → False; OpenAI virtual-currency tokens →
False; **EUR VM compute ×2 → True** (deliberately creating an
eligible-but-uncovered pocket in a second currency, exercising §5.1);
spot VM (Dynamic) → False; marketplace appliance → False. Chunk 4:
SkuPriceDetails VM compute (Standard) → True (the main USD uncovered
demand); Premium SSD disk → False; nameless NIC → False; rename rows ×2
(VM compute) → True; capacity-reservation rows → True if status Used else
None (conditional expression in the fixture loop); 3yr upfront purchase →
None; month-boundary storage → False; App Service invoiced/uninvoiced
pair → False. Legacy era (pre-1.2 schema): column **not** added — the era
predates the flag; unified carries NULL there by construction. Negative
fixtures inherit the column via NEGATIVE_COLUMN_SPECS, default None.

### 1.3 Verification (sandbox, then Nakita's machine)

Sandbox run of the fixed generator: chunks 0–7 complete, all self-tests
pass (14/14 distinct violation labels, 13/13 confirmed present), v1.2
layer 76 rows × **67 cols** (was 66). Distribution exactly as designed:
**37 True / 12 False / 27 None = 76** (True = 31 Used + 1 CR-Used + 2 EUR
+ 1 SkuPD + 2 rename; False = 12; None = 1 purchase + 21 Unused + 3
Tax/Credit/Adj + 1 CR-Unused + 1 upfront purchase). Coverage preview on
the regenerated layer: USD coverage-of-coverable 85.5% (63.80/74.60), EUR
6.62 eligible, 0% covered.

Nakita's local run (1 Sep): identical layer table; `build_unified.py`
merged to **204 × 115** (BY-NAME union fills era gaps with NULL — the
loader printed its own explanation); DuckDB DESCRIBE confirmed 115.
Harness re-run: real target unchanged (see §1.5).

### 1.4 FINDING — determinism proven across machines (F20 vindicated)

Her v1.2 `contentSha256 = a3e2d030365e` was **identical** to the sandbox
run of the same fixed file on different hardware with different pyarrow
versions (hers 21.0.0, sandbox 25.0.1). `fileSha256` differed (7132f0954725
vs sandbox's), exactly as the two-checksum design predicts: contentSha256
is the data, stable anywhere; fileSha256 is the bytes, stable only within
one environment. *The generator is the artifact* — now demonstrated
cross-environment, not asserted.

### 1.5 Full Stage 5 regression pass on the regenerated data

Her first "Chunk 1" run accidentally re-ran the entire Stage 5 query
layer (root cause in §2.1) — which turned into recorded regression
evidence: showback identical (UNTAGGED 12.63 / 34 rows), budget 2a 15.2%
consumed / 16.97 remaining, burn-down curve unchanged, anomaly A1 still
flagged at 30.0× median (fx-appliance-01, 18.00 effective / 0.00 billed),
savings ladder unchanged (USD headline 34.62 = 23.3% of list; negotiation
3.72 + commitment 30.90), block-pricing waste unchanged (1 block, 0.05,
66.7% utilisation; token row "block size not recorded; waste not
assessable"), commitment utilisation verdicts unchanged (83.1% evaluable /
NOT EVALUABLE 1-of-1096 / TERM UNKNOWN). Harness on the regenerated
estate: real target still **236 MUST / 1,170 SHOULD**, all from the
empty-string columns; unified 0 FAIL / 2 known F10 WARNs; layer C targets
0/0. **Adding the x_ column changed nothing downstream — an additive
extension measured to be additive.**

---

## 2 · Chunk 1 — three-way reconciliation (stage6_reconciliation.sql, Q1–Q6)

### 2.1 Runner discovery: run_queries.py ignores its argument

Her `python3 run_queries.py stage6_reconciliation.sql` produced Stage 5's
thirteen queries — `run_queries.py` v2 has `queries.sql` hardcoded and
ignores argv. Rather than touch the v2 runner, a standalone
**`run_stage6.py`** was written: strips `--` comments (replacing them with
spaces so character offsets survive), splits statements, labels each
result with the `Q# ·` header it sits under, prints full frames, and
prints "(no rows — for the orphan check, empty IS the pass)" for empty
results.

### 2.2 The splitter bug class, appearances one and two

- Appearance 1 (31 Aug, in-session test): the naive test splitter broke on
  a **semicolon inside a comment** ("group by BillingCurrency before
  aggregating; never reason from sign") — the exact `run_queries.py` v1
  bug the Stage 5 notes recorded. Fixed in the runner by stripping
  comments before splitting.
- Appearance 2 (label offsets): first runner version keyed each result's
  title on the chunk's start offset, which sits *before* the Q-header
  comment, so labels ran one behind. Fixed by keying on the first
  non-space character of the statement itself; CREATE statements executed
  silently.

### 2.3 First local run (1 Sep): five of six clean, Q5 failed — FINDING S7

Q1 TIES TO THE CENT · Q2 panels · Q3 grand proof · Q4 empty · Q6 PASS —
but **Q5 reported FAIL on both period pairs** ("period pair not in
billing_period"), on the same two files that MATCHED in-session. The
internal contradiction was the clue: Q6 found the June period **Closed**
via a *range* join on the same file Q5's *equality* join couldn't match.

Diagnostic (her run): local `billing_period.csv` columns parse as
**TIMESTAMP WITH TIME ZONE** (`2026-07-01 02:00:00+02:00`) while the
parquet's period columns are timezone-naive. DuckDB compares naive vs
aware by interpreting the naive side in the **session timezone**: on her
SAST Mac, naive midnight → `00:00+02:00` ≠ the CSV's `02:00+02:00`
(equality fails by two hours); in the UTC sandbox, naive midnight →
`00:00+00:00` = `02:00+02:00` (equality holds). **Same two files, opposite
verdicts, decided by the analyst's laptop.** Q6 passed because a range
predicate absorbs a 2-hour skew that equality cannot — the perfect
illustration of why the finding matters.

First fix: normalise both sides to DATE in the view/joins. Reproduced her
failure in-session under `SET TimeZone='Africa/Johannesburg'` (0 matches
raw), proved the DATE fix (204/204).

**Her question — "will the analyst laptop zone issue persist if someone
in Germany or Australia tests my work once it's live?" — caught a
residual bug in that fix.** `CAST(timestamptz AS DATE)` converts to the
*session-local* date first: fine anywhere east of UTC (Berlin 01:00/02:00,
Sydney 10:00 — still July 1), but in any UTC-negative zone
`2026-07-01 02:00+02:00` is June 30 local → the cast yields 2026-06-30 and
the join misses again. A reviewer in the Americas would have seen Q5 fail
on a published repo.

Final fix: the `bp` view reads the period columns **as VARCHAR** and takes
the civil date exactly as written — `CAST(substr(col,1,10) AS DATE)` with
`read_csv_auto(..., types={...:'VARCHAR'})` — so no timezone
interpretation ever touches them. Proved by running the full file under
four session timezones (**UTC, Europe/Berlin, Australia/Sydney,
America/New_York**): identical verdicts in all four.

**FINDING S7 (binds all future SQL, S-series):** billing_period.csv
carries offset-aware timestamps; cost data carries naive ones. Raw
equality is session-timezone-dependent (fails SAST, passes UTC); even
CAST-to-DATE shifts a day west of Greenwich. Rule: **period comparisons
read the civil date as written — text-grain, never through timezone
conversion.** Roadmap: `generate_layer_c.py` should emit plain dates so
the hazard is removed at source rather than survived at query time; the
query-side tolerance is the interim measure and says so.

### 2.4 Clean run (1 Sep, six of six) — results verbatim

- **Q1** INV-2026-07-0001 USD: InvoiceTotal −1.61 = CostUsageBilled −1.61,
  CU_Rows 2, InvoiceLines 2, Difference 0.0, **TIES TO THE CENT**.
- **Q2** panels: 1·Invoiced USD 2026-07 2 rows −1.61 · 2·Legacy era
  (x_InvoiceId only, no v1.4 invoice_detail row) USD 2024-03 10 rows 1.44
  · 3·Not yet invoiced account-level (Tax/Credit/Adjustment) USD 3 rows
  −17.56 · 4·commitment purchases USD 2 rows 2,702.40 · 5·usage open
  period EUR 2 rows 6.62 and USD 185 rows 18.86.
- **Q3** grand proof per currency: EUR 6.62 + 0 = 6.62 (2 rows); USD
  −1.61 + 2,705.14 = **2,703.53** (202 rows). Nothing dropped, nothing
  double-counted, currencies never summed together.
- **Q4** empty — for the orphan check, empty IS the pass.
- **Q5** 2024-03-01..2024-04-01 (10 rows) Closed **MATCHED**;
  2026-07-01..2026-08-01 (194 rows) Open **MATCHED**.
- **Q6** correction: consumption 2026-06-14, billed 2026-07, −1.85,
  ReferenceInvoiceId INV-2026-06-0001, referenced period **Closed** —
  **PASS — restates a closed period**.

Amendment A3.2 assertions 1, 2, 3 all held on her machine, timezone-proof.

---

## 3 · Chunk 2 — eligibility-aware coverage (stage6_coverage.sql, Q7–Q11)

### 3.1 Design decisions (recorded because they ARE the deliverable)

- **Two denominators, same numerator (Q7).** Coverage-of-coverable =
  covered eligible ÷ eligible demand (flag TRUE); naive coverage = same
  numerator ÷ all usage demand (Unused excluded from both). The gap
  between the figures is the entire argument for eligibility-awareness.
- **Unused commitment excluded from demand everywhere** and reported in
  its own panel (Q11): it is utilisation's problem; folding it into the
  coverage denominator double-punishes. This is why the flag design left
  Unused as None.
- **Two different NULLs, labelled apart (Q9):** concept-n/a vs
  era-predates-the-flag. Bucket 6 ("NULL — unexplained") exists precisely
  so it can be asserted empty.
- **Action list groups on ResourceId, displays name (S5, Q8).**
- **Closure verdicts, not numbers alone (Q10):** CLOSES EXACTLY /
  IN PROGRESS — short export, not shortfall / ORPHAN — term unknown,
  closure not evaluable. Trust the period columns over the description
  (the 1yr quirk). Layer C join key:
  cost.CommitmentDiscountId = contract.ContractCommitmentId.

### 3.2 Verification method

Her local unified (115 cols) could not be uploaded mid-chunk, so the
verification target was reconstructed in-session: uploaded parquet's
non-1.2 rows (real 118 + legacy 10) UNION ALL BY NAME with the regenerated
flagged v1.2 layer → 204 × 115. All five queries verified against that
before delivery; her local run then matched the verification numbers
line for line.

### 3.3 The splitter bug class, appearance three

Q10's ORPHAN verdict string contains a semicolon **inside a string
literal** ("…no contract record; term unknown…") — the same bug class as
the comment semicolon, in its third costume (v1 comment → my test comment
→ string literal). `run_stage6.py` gained a quote-aware splitter (tracks
single-quote state; '' escapes toggle twice and net out). Also fixed in
the same pass: Q7's EUR percentages displayed NaN when nothing was
covered — COALESCE to 0.

One test-rig artefact worth distinguishing from a real defect: the first
in-session behavioural test showed 202 "orphans" because pandas rendered
missing InvoiceIds as float NaN rather than None; the harness's own
loaders yield None, matching its `if not invoice_id` convention. Fixed in
the test rig (astype(object) before the None substitution), not in the
checks.

### 3.4 Clean run (1 Sep) — results verbatim

- **Q7** EUR: covered 0.00, eligible 6.62, coverage-of-coverable 0.0%,
  naive 0.0%. USD: covered 63.80, eligible 74.60,
  **coverage-of-coverable 85.5% vs naive 63.4%**.
- **Q8** action list: EUR vm-web-eu-01, 2 rows, 6.62 uncovered eligible;
  USD vm-web-01, 3 rows, 10.80.
- **Q9** buckets (rows / EffectiveCost): eligible EUR 2/6.62, USD
  35/74.60; ineligible-by-rule USD 12/21.42; NULL-unused USD 22/13.00;
  NULL-concept-n/a USD 5/−17.56; NULL-era 1.0r2 USD 118/3.03;
  NULL-era pre-1.2 USD 10/1.54. **Bucket 6 absent — every row explained.**
- **Q10** 1yr: 74.4 / 74.4 / 74.4, term 2026-07-01→2026-08-01, **CLOSES
  EXACTLY**. 3yr: 2,628.0 purchase, 2.4 amortised, term →2029-07-31,
  **IN PROGRESS — short export, not shortfall**. legacy-2023: no contract
  record, **ORPHAN — closure not evaluable**.
- **Q11** utilisation: 1yr 61.8/12.6 = 83.1%; 3yr 2.0/0.4 = 83.3%;
  legacy 0.1/— = 100.0%.

Interpretive line for the case study: the naive 63.4% would trigger a
"buy more commitments" conversation the data does not support; 85.5% of
what could be covered already is, and the actual actionable gaps are two
named resources totalling 6.62 EUR + 10.80 USD.

---

## 4 · Chunk 3 — promotion into validate.py (2 Sep)

### 4.1 Decision and approach

Options were (a) fold into `validate.py` proper or (b) a standalone
assertion script with (a) as roadmap. **Nakita chose (a) — "if into
validate.py is the best proper way then let's do it properly."** The
surgery followed a full architecture read: REGISTRY vs CROSS_REGISTRY,
SpecRef with the `derived` honesty mechanism, Check severity =
strongest-ref, the register() duplicate-sentence guard (dataset-scoped),
CrossContext with cost_target(prefer="unified"), the era gate, `_ts()` /
`_dec()`, TOLERANCE = Decimal("0.000001"), and the three existing chunk-6b
checks.

### 4.2 Division of labour vs chunk 6b (deliberate, documented in-code)

Existing checks left untouched: XDS-invoice-reconciliation already FAILs
a per-invoice mismatch and WARNs an invoice no cost row cites (F38's
not-evaluable argument); XDS-commitment-closure already decides closure
where the term allows; XDS-billing-period asserts period geometry
(non-overlap) and containment. What was missing and added, new section
**6e-bis**, four checks, all citing **Amendment 1 with derived=True**
(an amendment citation cannot go stale against a FOCUS tag —
version_diff's impact half correctly skips derived refs, and the code
says so):

1. **XDS-invoice-orphan-cost-side** (FAIL per orphan id): a cost row
   citing an invoice absent from invoice_detail — a broken reference, the
   authority failing at the one thing it exists for. INFO when clean and
   evaluable.
2. **XDS-period-pair-match** (FAIL per missing pair): every cost-row
   (BillingPeriodStart, BillingPeriodEnd) pair exists in billing_period,
   compared via a new **`_civil_date()`** helper — `_ts()` already keeps
   the written clock (fromisoformat parses the offset,
   replace(tzinfo=None) drops it without converting), so `.date()` of it
   is the civil date as written; machine-invariant, S7 inherited by the
   harness. INFO names the grain: "compared at civil-date grain (S7)".
3. **XDS-correction-discipline**: a Correction row's invoice line must
   carry a ReferenceInvoiceId ≠ its own InvoiceId (FAIL if none), and the
   consumption date must fall in a **Closed** period (FAIL "must reference
   a Closed period" if Open — the backdating case; FAIL if in no declared
   period; WARN not-evaluable if the correction carries no InvoiceId;
   INFO when discipline holds).
4. **XDS-eligibility-universe**: FAIL if any v1.2-era Usage row has no
   x_CommitmentEligible verdict and is not Unused (Stage 6 disclosure
   bucket 6, which must be empty — doubles as the regression guard for
   the seed fix: wipe the flag and 49 rows land here at once); INFO per
   currency reporting **coverage of coverable vs naive** side by side.

### 4.3 Verification in-session before delivery

Syntax parse ✓ (3,033 lines, from 2,708). Behavioural test drove the four
check functions with her real data (invoice/billing CSVs + reconstructed
115-col unified) through duck-typed contexts: clean data → INFO only,
including the coverage pair. Sabotage matrix, every FAIL proven to fire:
ghost InvoiceId planted → orphan FAIL; 2024 row deleted from
billing_period → period-pair FAIL (10 rows); June period forced Open →
correction FAIL; flag wiped → eligibility FAIL (49 rows). A `rules.py`
stub (RULES_VERSION = 4) was needed to import the module in isolation —
test scaffolding only, never shipped; validate.py's version guard on
rules.py noted as a nice touch encountered.

### 4.4 Her verification run #1 (2 Sep): the accidental absent-authority demo

Result: two of four new checks reported (orphan INFO, eligibility INFO ×2
with 85.5/63.4), **period-pair and correction produced no lines** — and
Datasets discovered showed the cause:
`layerC:billing_period  absent  data/supplemental/billing_period.csv/`
(trailing slash — a *directory* of that name where the file should be;
artefact of the earlier sabotage/rename housekeeping). The two silent
checks going silent is their designed behaviour when the authority is
absent: **not-evaluable is not a pass, and they refused to report one** —
the F38 discipline inherited by the Stage 6 assertions, demonstrated live
by accident. Everything else in that run: cross-dataset 0 FAIL / 0 WARN /
8 INFO; real target 236/1,170 unchanged; unified 0 FAIL + 2 known F10
WARNs; no new failures anywhere — the surgery changed only what it meant
to.

### 4.5 Her verification run #2 (2 Sep): ten of ten

billing_period.csv restored (name fixed). Datasets discovered:
`layerC:billing_period 3 rows × 6 cols`. Cross-dataset: **0 FAIL / 0 WARN
/ 10 INFO** — the original six plus:
- XDS-invoice-orphan-cost-side — every InvoiceId on a cost row exists in
  invoice_detail
- XDS-period-pair-match — every cost-row period pair exists in
  billing_period (3 period(s) declared) — compared at civil-date grain (S7)
- XDS-correction-discipline — Correction restates a Closed period
  (consumption 2026-06-14) and its invoice names the reference — cut-off
  discipline holds
- XDS-eligibility-universe — [EUR] 0.0% vs 0.0%; [USD] **85.5% vs 63.4%**
All other targets byte-identical to pre-surgery. **Chunk 3 closed.**

### 4.6 Cosmetic footnote (roadmap, not fixed)

The run footer still reads "165 checks cite a specification sentence;
1 are DERIVED" — that counter reads the per-target REGISTRY only and has
never counted CROSS_REGISTRY (the original three chunk-6b checks were
never in it either), so the four newcomers do not move it; their INFO
lines are the proof they ran. Roadmap: summary counter should also report
CROSS_REGISTRY size and its derived split.

---

## Findings ledger (Stage 6 additions)

- **S7** (binding rule, S-series): period comparisons at civil-date grain,
  never through timezone conversion. Full mechanism in §2.3. Verified
  identical verdicts under UTC / Berlin / Sydney / New_York, in both the
  SQL and the harness (`_civil_date`). Credit where due: the
  world-portability residual (west-of-Greenwich day shift) was caught by
  Nakita's reviewer-simulation question, not by the first fix.
- **F-S6-1 · Cross-machine determinism**: identical contentSha256 across
  machines and pyarrow versions, differing fileSha256 — F20's two-checksum
  design demonstrated in the wild (§1.4).
- **F-S6-2 · Additive extension measured additive**: full Stage 5 + Stage 4
  regression pass on the regenerated 115-column estate (§1.5).
- **F-S6-3 · The splitter bug class, three costumes**: v1 comment
  semicolon → test-harness comment semicolon → Q10 string-literal
  semicolon. run_stage6.py is now comment-aware AND quote-aware; one bug
  class, three appearances, each caught at a different layer.
- **F-S6-4 · Two denominators**: 63.4% vs 85.5% on identical data —
  eligibility-awareness changes the conversation from "buy more
  commitments" to "two named resources, 6.62 EUR + 10.80 USD".
- **F-S6-5 · Absent-authority behaviour demonstrated live**: billing_period
  missing → the two dependent checks silent rather than passing (§4.4).
- **F-S6-6 · run_queries.py v2 ignores argv** (queries.sql hardcoded) —
  discovered §2.1; run_stage6.py exists because of it. Roadmap: teach v2
  to accept a filename, then retire run_stage6.py.

## Roadmap lines accumulated (honest, costs nothing)

1. generate_layer_c.py: emit plain dates in billing_period (remove S7's
   hazard at source; query-side text-grain read is the interim).
2. validate.py summary counter: include CROSS_REGISTRY count + derived
   split.
3. run_queries.py v2: accept a filename argument; retire run_stage6.py.
4. Negative fixtures for the cross-dataset checks (the sabotage matrix as
   committed test data rather than an ad-hoc proof).

## Artifacts of record (current, superseding all earlier copies)

- `seed_data.py` (2,365 lines, 16 eligibility touch points) — in repo, run.
- `stage6_reconciliation.sql` (Q1–Q6, text-grain bp view) — final version.
- `stage6_coverage.sql` (Q7–Q11, COALESCEd Q7) — final version.
- `run_stage6.py` (comment-aware + quote-aware splitter, Q-header labels).
- `validate.py` (3,033 lines, section 6e-bis, four cross checks) — in
  repo, run twice, ten INFO.
- Pre-surgery harness kept as `validate_pre_stage6.py` until this point;
  may be deleted or kept at Nakita's preference now that run #2 is clean.

## Open item — the only one

**Chunk 4, the 1.2 → 1.4 readiness memo.** Input required:
`python3 version_diff.py` output. Sources already banked for it: the
diff + harness-impact output (incl. GONE/RESTATED/RELAXED categories);
pre-established conclusions F10 and F24 fixed upstream at v1.4 as this
project derived independently, F12 likewise; the covering/covered
recognition note with the consolidation-accounting parallel; and this
week's fresh evidence — 1.2-preview export selectable at billing-account
scope only, Microsoft's hollow-preview-columns note, the era-boundary
reconciling items (§0), the interim-invoice inconsistency, and S7.
