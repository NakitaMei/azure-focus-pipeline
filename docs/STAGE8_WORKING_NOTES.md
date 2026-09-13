# Stage 8 — Publication Working Notes

**Project:** Azure Cost Management → FOCUS Pipeline (Portfolio Project 1) · repo `azure-focus-pipeline` under `github.com/NakitaMei`
**Opened:** Wednesday 9 September 2026 · **Driver:** P1_PREPUBLICATION_REVIEW_AND_STAGE8_PLAN.md, Part C order
**Calendar binds (review):** private repo committed Sat 12 · checker clean + cold read Sun 13 · buffer Mon 14 · **public Tue 15** · post Wed 16 · Story Thu 17 · Henrique Fri 18 · fly Sun 20 16:35
**Re-plan 13 Sep (work paused 9–13 Sep for family; one step ticked):** *(end of day: Steps 1–5, 7, 8, 9 and the checker half of 10 done; 6 out by default; open: 10b private repo + cold read (yours), 11 teardown, 12 public)* Sun 13 = Steps 2–6 + README draft · Mon 14 = README review, Step 8, Step 9, Step 10 (checker, private repo, cold read) · Tue 15 = Step 11 then Step 12. The Monday buffer is now a working day. Fallback if Tuesday runs short: publish Tuesday, tear down Wednesday — the final-cost screenshot simply captures a later total; the publication date is what the Story and the Henrique message depend on.

This is the one working file for Stage 8. It is updated in place; nothing is written twice. Each step has a "run this" block, a "done when", and a ledger line that is filled after your screenshot confirms it.

**Standing rules for this stage**
- One step at a time. You run, you screenshot, I read the screenshot, then the ledger line is ticked and the next step opens.
- Claims not yet true get **removed**, not softened. If a sentence describes something that is not built, the sentence goes.
- Verify against the files, not memory. A number is only carried into a published document once the file that produced it has been seen in this session.
- Sanitisation is a control, not a checklist item: sweep → `publication_check.py` → private repo → cold read → public. Nothing skips the checker.
- UK English throughout (`optimise`, `sanitise`), except Framework capability names, which are proper nouns.

---

## 0. Inputs — what has landed and what has not

The review's C1 checklist names the files Stage 8 needs. Status as of the opening turn:

| File | Needed for | Landed? |
|---|---|---|
| P1_PREPUBLICATION_REVIEW_AND_STAGE8_PLAN.md | everything | ✅ read in full |
| STAGE7_ANALYSIS_WORKING_NOTES.md | F4 (§10.3), case study (§4.5, 8.5, 9.5, 10.5, 11.3, 12), closure §13 | ✅ |
| STAGE7_KICKOFF_WORKING_NOTES.md | F4 (F-K6 basis), F5 pending lines | ✅ (first time — the review never received it) |
| STAGE6_WORKING_NOTES.md · READINESS_MEMO_1_2_to_1_4.md | case study, README version paragraph | ✅ |
| STAGE5_WORKING_NOTES.md · queries.sql (Stage 5 query layer, Q1–Q6) | case study, sql/ folder | ✅ |
| stage6_reconciliation.sql · stage6_coverage.sql | sql/ folder, README links | ✅ |
| **stage7_queries.sql** | **F2 — the first step** | ❌ not attached. The file named `queries.sql` is the Stage 5 layer, not Stage 7 |
| README.md · conformance-report.md | F1, F3 | ❌ |
| STAGE7_KICKOFF_LOG.md (the timestamp log, distinct from the working notes) | F5 | ❌ |
| token_generation_log.csv (clean copy) | F5 note, data/ | ❌ |
| AWS_SETUP_LOG.md | F11 | ❌ |
| Screenshot folder | C4 filing, sanitisation | ❌ Drive link cannot be opened by the connector (see §1) |
| STAGE5_WORKING_NOTES.textClipping | — | Apple clipping artefact (247 bytes), not a document; ignore, do not commit |

Missing files are requested at the step that needs them, not all at once.

## 1. Screenshot folder — the Drive link, and the way round it

**What happened.** The Drive connector was queried three ways on 9 Sep: by the folder's id (`parentId = '1hQOr8xWoOafZLSEy7nrp5WAJntKG9_CU'`), by image type since July, and by "Screenshot" in the title. All three returned nothing. The connector does see your Google-native files (the thirteen `P1S5 query_*` sheets, Master v2/v3), so the account is connected; it simply does not surface the image files in that folder. Same limitation the review recorded on 7 Sep.

**What we do instead — a manifest, not the images.** A *manifest* here means a plain-text list of every screenshot with its creation date, time and size — a few kilobytes, however large the folder is. That is enough to order the files by name and time, match each one to the review's C4 index (the SAST timestamps in the stage7-kickoff table were written for exactly this), and decide keep / rename / drop. The images themselves are only needed one at a time, later, for the blur check.

**Sanitisation note for this step.** A file listing contains filenames, times and sizes only — no secrets, no identifiers. It is safe to upload as-is. Do not paste any screenshot *content* into chat during filing; the blur check is a separate, later step where each image is looked at individually.

Run block is in Step 1 below.

## 2. Verified in advance (from the files that did land)

These are not executed yet — they are facts checked now so the step that uses them does not stall.

- **F4 — the 65% figure has no derivation.** Stage 7 analysis notes §10.3 say "~65% of the VM's would-be compute spend (F-K6's estimate, basis in the kick-off notes)". The kick-off notes' F-K6 (item 6) states "~65% of compute" with no arithmetic behind it. 70.2% *is* derived: off 118 of 168 weekly hours (18:00–08:00 weekdays = 70 h, plus 48 h weekend). At pay-as-you-go compute rates, hours off ≈ cost off, so **70.2% of compute-hours, ≈70% of compute cost at PAYG rates, disk and IP untouched** is the one number. 65% is removed wherever it appears (analysis notes §10.3, §10.5, §13 item 4; kick-off notes item 6 and the §B/closing lines). *Executed at Step 4.*
- **F5 — pending lines in the kick-off working notes** (the LOG is still to come): line 211 "Autoscale screenshot + paragraph (scale-set) — untouched, still owed" is closed by analysis notes §11 and §13. *Executed at Step 5.*
- **Repo-relative paths (F2, A3-7).** `queries.sql` (Stage 5) already reads `data/unified/...` and `./data/supplemental/...` — clean. `stage6_*.sql` read `data/unified/` and `data/supplemental/` — clean. Only `stage7_queries.sql` is known to carry `~/...`. *Executed at Step 1.*
- **Sanitisation grep targets seen in the attached notes** (for the C3 sweep, Step 8): the Stage 7 notes carry the resource name `nakitameiring-6066-resource`, a batch id, a file id, and the deployment name. Per the review's C3 decision these are provenance, not secrets — keep, allow-list in the checker. No subscription id, account id, email or key string was found in the attached notes on a first read; the sweep at Step 8 greps properly rather than trusting this read.

---

## 3. Step ledger

Terms, first time used: **date ceiling** — a `WHERE ... < DATE` line that stops a query reading rows newer than a chosen day, so a later file overwrite cannot change an already-published number. **Repo-relative path** — a file path written from the repository's root (`data/...`) instead of from your laptop's root (`/Users/...`), so the query runs on anyone's machine.

### Step 1 — F2: fix `stage7_queries.sql` · OPEN

**Why first.** The review found a real correctness bug, not style: sections C4a (September), C4b and C4c filter the September file on currency and `ChargeCategory = 'Usage'` only. After the file overwrite on 8 Sep that file also holds the batch-2 token rows (7 Sep, $0.28), so "scheduled per day", the Fri/Sat exhibit and the meter anatomy would silently absorb token spend, and the hard-coded `/6` divisor is wrong once September has more than six days.

**Blocked on:** `stage7_queries.sql` — not attached. The edits are known (below); they are applied to the actual file, line by line, once it lands, so nothing is patched from memory.

**The five edits, in plain English (the review's A3-5, 6, 7, 9, 18):**
1. C4a-Sep, C4b, C4c: add a date ceiling `AND ChargePeriodStart < DATE '2026-09-07'` (or exclude the AI resource by `ResourceId`), so the scheduling figures stay VM-only.
2. Same sections: replace the hard-coded `/6` with `COUNT(DISTINCT CAST(ChargePeriodStart AS DATE))` — count the days in the data instead of assuming six.
3. C4c: `HAVING SUM(BilledCost) > 0` → `<> 0` with a comment, **or** drop the HAVING so the $0.00 compute meter shows as its own line. The review prefers the second — the free-tier compute meter appearing at $0.00 is the stronger exhibit. Decision taken at edit time when the section is visible.
4. Header: replace `~/...` with `data/...` repo-relative paths (the "edit paths HERE ONLY" block).
5. C3: cite the interactive rate — `-- Global Standard list rate as displayed on the Azure deployment blade, 31 Aug 2026 (screenshot stage7-kickoff/01)`. Add the S7 civil-date comment next to the `CAST(... AS DATE)` / `dayofweek()` lines so a reader knows timezone was considered.

**Run this (two items, both local, no dependencies between them):**

(a) Upload `stage7_queries.sql` to this chat.

(b) Build the screenshot manifest. **Decision 9 Sep:** download the Drive folder to the Mac, folder by folder, into one parent folder **keeping the per-stage sub-folders** (they already mirror the C2 layout). The Drive copy stays as the untouched original and is never edited or published; the Mac copy is the working copy that gets renamed, blurred and committed.

A Drive download arrives as a zip, and unzipping resets every file's creation time to today — so the manifest sorts by **path**, not by created time. Within each sub-folder that is by filename, and the macOS names (`Screenshot 2026-08-31 at 15.13.41.png`) carry the real clock the C4 index was written against. In Terminal, with `<main folder>` replaced by the parent folder:

```bash
cd "<main folder>" && find . -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) -exec stat -f '%N%t%z' {} \; | sort > ~/Desktop/screenshot_manifest.txt && wc -l ~/Desktop/screenshot_manifest.txt
```

That writes one line per image — sub-folder/filename, then size in bytes — sorted by path, to `screenshot_manifest.txt` on the Desktop, and prints the line count. Upload that text file. Files that don't follow the macOS name pattern (Stage 1's numbered names, `Governance_key_regeneration_pnp.png`) are matched by name, not time.

**Edits applied 9 Sep** (file delivered as `stage7_queries.sql`; the eight changes, each against a line that was visible):
1. Paths → `data/raw-sanitised/ai.aug…` and `…ai.sept…`; the old path also carried the retired repo name `<working-folder>` — gone.
2. New view `vm_rows_sep`: USD · Usage · AI resource excluded · `>= 01 Sep AND < 07 Sep`. One place, so C4a/C4b/C4c cannot drift apart. (Both guards used — the date ceiling keeps the documented 1–6 Sep window; the resource exclusion catches any AI row inside it.)
3. C4a: `/21` and `/6` → `COUNT(DISTINCT CAST(ChargePeriodStart AS DATE))`, with a visible `days_in_data` column. **If August shows fewer than 21 days present, the 0.3275 figure changes and is recorded as a finding** (F-K1: missing days are not zero days). The `/21` was not in the review's list; changing it follows the same rule as `/6`.
4. C4c: `HAVING SUM(BilledCost) > 0` removed entirely (the review's preferred option) — the $0.00 compute meter now appears as its own line; row count added.
5. C3: the $0.10 / $0.40 Global Standard rates cited to the deployment blade, 31 Aug 2026, `screenshots/stage7-kickoff/01-openai-deploy-blade-batch-50pct.png`.
6. S7 comment added at the source block: naive UTC timestamps, so `CAST(… AS DATE)` / `dayofweek()` read the civil date as written.
7. 65% removed from the C4c comment → "70.2% of compute-hours off (118 of 168 per week), ≈70% of compute cost at PAYG rates".
8. Stale "re-download tomorrow" comment and the "supersedes chunk2/chunk3 … delete those" housekeeping line removed (they name files that will not be in the repo). Run line now reads `duckdb < sql/stage7_queries.sql` from the repo root.

**Two decisions surfaced by the edit (not in the review):**
- **D-S8-1 · The August and September real exports need a committed, sanitised home.** The review's layout only lists the July export under `data/raw-sanitised/`. C2/C2b/C3/C4 read the Aug and Sep files, so sanitised copies (subscription id replaced, same treatment as July) must be committed or the queries are unreproducible from the repo. **Home: `data/stage7/`** — not `data/raw-sanitised/`, because `validate.py` discovers that folder sub-folder by sub-folder as the validated real layer and the report would widen (found at Step 2). Executed at Step 9, where `build_unified.py`'s sanitising step is pointed at the two files.
- **D-S8-2 · Resource name kept.** `nakitameiring-6066-resource` stays in the SQL as provenance (review C3 decision); allow-listed in `publication_check.py` at Step 10.

**Path correction 9 Sep (F-S8-4):** the first delivered file pointed at `data/raw-sanitised/`, which does not exist yet; the two exports sit in the project-folder root, and the file was overwritten there before the run. Redelivered with the "edit paths HERE ONLY" block set to the bare filenames (no username, no absolute path) and a comment carrying the Step 9 target paths. The original file is preserved in the Stage 8 chat.

**Run this (from the project folder, where the two parquet files and `stage7_queries.sql` sit):**

```bash
cd <working-folder> && duckdb < stage7_queries.sql
```

Screenshot the C4a, C4b and C4c output blocks (C2/C2b/C3 unchanged — glance that C2 still says 0.280758 and C2b 0.279593, no screenshot needed).

**Done when:** three screenshots show — C4a: `days_in_data` 21 and 6, per_day 0.3275 and 0.3344 · C4b: Fri 4 Sep = Sat 5 Sep = 0.3344, no 07 Sep row · C4c: disk + IP carry the cost, compute meter present at 0.0000, no AI meter. Ledger line then reads: `F2 ✅ <date> — C4a/b/c re-run on the overwritten Sep file, VM-only figures held`.

**Ledger:** `F2 ✅ 9 Sep — C4a/b/c re-run on the overwritten Sep file, VM-only figures held: 21/6 days, 0.3275/0.3344 per day, Fri 4 = Sat 5 = 0.3344, compute meter at 0.0000, no AI meter. C4c ties to C4a (6.8769 / 2.0065). Screenshot: stage7-analysis/06-scheduling-c4abc-fri-sat-identical-meter-anatomy.png (parked in the stage 8 folder until Step 9; index item 07 folds into it).` Manifest still to come.

**Queued for Step 4 from this run:** analysis notes §10.1 "Sep 6 provisional $0.2837" → settled to 0.3344 on the 8 Sep pull; §10.1/§10.5 gain two lines — compute meter absent (not zero) on deallocated days (4 rows in 6 days vs 21 in 21), and the Automation meter itself bills $0.00.

### Step 2 — F3: regenerate `conformance-report.md` from the current `validate.py --report` · OPEN
Files received 9 Sep: README.md, conformance-report.md (19 Aug), validate.py (3,033 lines).

**Read before running — two facts from the code:**
- The report's "Reproduce with" block is written by `write_report()` inside `validate.py`, so the A3-17 fix (no `src/` prefix, `self_test.py` missing) is a code edit, not a markdown edit. Patched, with the `1 are derived` grammar made number-aware. Delivered as `validate.py` — drop it over `src/validate.py`. Nothing else in the file changed (diff: the reproduce block and the two grammar lines).
- **The validator discovers the real layer from every sub-folder of `data/raw-sanitised/`** and labels each `real:<folder name>`. Adding the August and September exports there would widen the published report by two real datasets on publication week (A3-3: do not). **D-S8-1 amended:** the sanitised Stage 7 exports live in `data/stage7/`, outside the validator's search path; SQL comment updated. The report keeps `real:31 July 2026` as the validated real layer, and the README says in one line that the Stage 7 real rows were reconciled separately in `sql/stage7_queries.sql`.

**Run this, from the repo root (the folder that contains `src/` and `data/`):**

```bash
python3 src/validate.py --report
```

It validates every dataset it finds, prints the summary to the terminal, and rewrites `docs/conformance-report.md` with today's date. Screenshot (1) the terminal summary — the line with the check count and the per-dataset verdict table — and (2) the top of the new `docs/conformance-report.md` down to the end of the Verdict table. Then upload the regenerated `conformance-report.md`.

**Done when:** the report header says Generated 9 September 2026 with the `src/` reproduce block; Verdict still shows `real:31 July 2026` (118 rows, 236 / 1170 / 3) and the synthetic layers at 0 MUST; the cross-dataset line reflects seven XDS checks; the "What was checked" count is whatever the run prints — that number is then the one number used in the README (Step 7). Screenshots file as `stage4/01-validate-report-run.png` (replacing the 19 Aug run — the index name is kept, the image is the 9 Sep run).

**Ledger:** `F3 ✅ 13 Sep — report regenerated: Generated 13 September 2026, src/ reproduce block, real:31 July 2026 118/236/1170/3, synthetic 0 MUST, 7 cross-dataset checks / 10 observations, 14 of 14 planted caught. THE ONE NUMBER: 166 checks (165 cite a sentence, 1 derived; 7 of the 166 are cross-dataset). Run from the project root with validate.py at root — valid (ROOT resolves either way); publication-day cold run must use src/validate.py so the README is literally true.` Screenshot: the first terminal image, **cropped to start at the "validate.py — FOCUS conformance harness" header** (the prompt line above it shows username, machine name and the old folder name) → `stage4/01-validate-report-run.png`. Terminal-only footer "1 are DERIVED" patched in validate.py (second delivery, 13 Sep); the report text was already correct.

**README numbers to replace at Step 7 (from this run):** 100 + 3 → **166 checks (7 cross-dataset)**; 99 cite → **165**; 1 derived (unchanged); 88 / 70 / 18 (unchanged); 7 datasets validated (unchanged — negative is the proving set, not a validated dataset); 14 of 14 (unchanged); real export columns 99 as discovered.
Needs: README.md, conformance-report.md (current), and a screenshot of the `--report` run. Decision already taken (review A3-3): keep `real:31 July 2026` as the validated real layer; one line saying Stage 7's real rows were reconciled separately in `stage7_queries.sql`. Take the check count the run prints and use it everywhere.

### Step 3 — F6: repo name and handle · OPEN
Grep every doc for `azure-cost-management-finops`, `<working-folder>`, `/Users/`, and the account username (the GitHub handle is `NakitaMei`). Case-study URL: **omitted** unless the Notion site is live on 15 Sep — a decision, not a task.

**Pre-grep 13 Sep on every file received:** README, conformance report, Stage 5/6 notes, readiness memo, queries.sql, stage6_*.sql, stage7_queries.sql (delivered version) — **0 hits**. Stage 7 analysis notes — 3 hits, all the resource name (keep). Stage 7 kick-off working notes — 7 hits: 6 resource-name/endpoint (keep; the endpoint hostname *is* the resource name), **1 to fix: line 163 `<working-folder>/` → repo-relative**. Fixed at Step 4/5 when those notes are edited anyway.

**Run this, from the repo root** — it lists every remaining hit outside the resource name, the data folders and the virtual environment, and writes them to a text file (paths and matched lines only — safe to upload):

```bash
grep -rn -i -E "<old-repo-names>|/Users/|<username>|<machine>" . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=data --exclude-dir=screenshots | grep -v "<resource-name>" > ~/Desktop/f6_hits.txt; wc -l ~/Desktop/f6_hits.txt
```

Upload `f6_hits.txt`. I classify each line as fix / keep, and the fixes go into the files as each is edited.

**Local grep result (f6_hits.txt, 13 Sep) — six lines, no documents:**
| Hit | Decision |
|---|---|
| `build_unified.py:59 SALT = "<working-folder>"` | **Keep** (D-S8-4). The salt seeds every pseudonym; changing it re-keys the sanitised layer and unified dataset. One comment line added at Step 9 when build_unified.py is in hand. |
| `spec_cache/v1.4/.ai/normalize_invoice_detail.py` — a third party's `/Users/…` path inside a fetched spec file | **Not committed** (D-S8-5). `spec_cache/` is re-fetchable by `spec_source.py` and is not in the README layout → `.gitignore`. |
| Four parquet binary matches at the project root (`ai.aug`, `ai.aug.pre.1.2`, `ai.sept`, `ai.sept.pre.1.2`) | **Move to `data/raw/stage7/`** (D-S8-6) — unsanitised real exports, same rule as `data/raw/`; sanitised copies built into `data/stage7/` at Step 9. |
| `f6_hits.txt` itself | Stays on the Desktop, never inside the repo folder. |

**Ledger:** `F6 ✅ 13 Sep — docs clean; kick-off path line fixed (Step 5 edit); three repo-hygiene actions queued in the 13 Sep run block below.`

### Step 4 — F4: one scheduling counterfactual number · DONE
**Ledger:** `F4 ✅ 13 Sep — 65% removed in five places (analysis §5 chunk-4 summary, §10.3, §10.5, §13; kick-off §A item 1 and F-K6); the one number is 70.2% of compute-hours off ≈ 70% of compute cost at PAYG, hours-proportional; §10.3 states the withdrawal explicitly. Sep 6 provisional line resolved (§10.1 table and text). §10.6 addendum added for the re-run facts (F-S8-5/6). Files delivered: STAGE7_ANALYSIS_WORKING_NOTES.md, STAGE7_KICKOFF_WORKING_NOTES.md — overwrite docs/ copies.`

### Step 5 — F5: close every "pending"/"owed"; CSV rename note; community-issue count · DONE
**Ledger:** `F5 ✅ 13 Sep — 0 open checkboxes remain in the Stage 7 analysis notes (7 closed with how/when) and kick-off notes (9 closed); kick-off LOG: autoscale line closed, key line reads "Regenerated 07 Sep", teardown decision recorded, CSV note carries the rename to est_cost_usd_batch. Token CSV confirmed clean (2 rows, one per batch). Community issues = TWO (Stage 4 notes §31.2: two live, two retired at v1.4) — README's "three" is replaced at Step 7. AWS S3 peek item marked carried to P2. Files delivered: STAGE7_KICKOFF_LOG.md (+ the two notes files above).`

### Step 6 — F11: AWS_SETUP_LOG · DECISION PENDING (D-S8-3)
Received 13 Sep: 12 `[fill]` fields, the account id in four places, the alert email in two. Nothing in P1 references the document; it is Project 2 groundwork.
**Recommendation:** take AWS_SETUP_LOG.md and the `aws/` screenshots **out of the P1 repo** — P2's opening document — and mention P2 in one line under the README's "what next". Removes twelve not-yet-true fields and two redaction classes from publication week. Alternative if kept: fill-or-delete the twelve, account id → `xxxxxxxxxxxx` ×4, sign-in URL removed, email → `<alert-recipient>` ×2, and the `aws/` screenshots need the console corner blurred on every one.
**Ledger:** ⏳ deferred by decision 13 Sep — **default: if Step 6 is not reached by end of Monday 14 Sep, the AWS log and `aws/` screenshots are out of P1** and P2 opens with them.

### Step 7 — F1: README rewrite (A4 shape) · DRAFTED 13 Sep, awaiting your read
Delivered as `README.md`. A4 order: what · who/why · five results (real/synthetic + link) · validator numbers (166/165/1/88-70-18/7/14) · reference-Validator comparison incl. L2 · version paragraph with the honest phrase · reproduce (root layout, `sql/` paths) · layout · read next · honest scope (L1, L3, L7, L9, L10, F3 decision, S7 German-colleague line, EUR sentence, two community issues, P2 one-liner). Removed: "100 + 3", "99 cite", "three candidate issues", `src/`, the STAGE4-only "read next".
**Dependencies this README creates:** it links `docs/READINESS_MEMO_1_2_to_1_4.md`, `docs/STAGE6_WORKING_NOTES.md`, `docs/STAGE7_KICKOFF_LOG.md`, `docs/STAGE7_ANALYSIS_WORKING_NOTES.md`, `sql/queries.sql`, `sql/stage6_*.sql`, `sql/stage7_queries.sql`, `requirements.txt`, `screenshots/stage5/`. The publish-tree script places every one of them; if any is missing on the day, the link comes out. It does **not** yet link a case study, governance note or findings file — those links are added at Step 8 only if the files exist.
**Answered 13 Sep:** (a) dashboard is **public** (share dialog: Anyone on the internet with the link, Viewer) — README now links it (URL from `p1s5-dashboard-url.md`); the report id is GUID-shaped, so expect one *advisory* "review" line for README.md from publication_check.py — not a block. (b) **no `requirements.txt` in the project folder**; the one-line file uploaded (`sqlglot>=20.0.0`) is a stray. Built from the import grep at the next run; until it exists the README line is a dependency, not a fact.
**Ledger:** ⏳ drafted 13 Sep.

### Step 8 — F8/F9: case study, findings & recommendations, cadence, two business cases, governance note · DONE 13 Sep
**Ledger:** `F8/F9 ✅ 13 Sep — four documents written into the publish tree and linked from the README's "Read next": docs/CASE_STUDY.md (1,229 words, the review's order), docs/FINDINGS_AND_RECOMMENDATIONS.md (15 findings × 6 columns + "what to do first"), docs/GOVERNANCE_NOTE.md (416 words, four controls, ends with the 7 Sep rotation as a fact), docs/CADENCE_AND_BUSINESS_CASES.md (nine-rhythm operating cadence; business case A: VM scheduling $0.00 now / ≈70 % of compute later, with the $8.91 B2ats v2 list price as the scale illustration; business case B: 85.5 % vs 63.4 %, uncovered-eligible $10.80 USD + €6.62 EUR). Every number in them was verified in this session. Checker re-run on the tree: clean, 58 text files. One old repo name found in the Stage 4 notes' target-tree diagram and fixed. Tree re-zipped: 128 files.`
**Later 13 Sep — positioning (your call):** README's second line changed from "a CFO moving into FinOps" to **"Built from a CFO's seat"** — the seat as the asset, no transition advertised. Case study gained two sections: "Read it as an accountant would" (16-row finance-twin table, from the review's B1) and "Where it sits in the Framework" (12 capabilities/concepts → where demonstrated → real/synthetic), so the FOCP / FOCUS Analyst / AI Value vocabulary is applied on the page rather than listed. Case study now 2,034 words. Checker clean; re-zipped.
**Decision on 11/12 timing (13 Sep):** nothing technical gates on Tuesday. Recommended: 10b + 11 tonight, 12 after a night's sleep and the cold read. AWS/P2: not required for P1; decide after Amsterdam.

### Step 9 — C3 sanitisation sweep + C4 screenshot filing · DONE 13 Sep (built here, from the full folder zip)
**Ledger:** `F7 (sweep) ✅ 13 Sep — publish tree azure-focus-pipeline/ built in the session from <working-folder>.zip + the stage zips + stage8-runs + the Stage 8 deliverables; delivered as azure-focus-pipeline.zip (5.8 MB, 124 files: 17 scripts, 4 sql, 16 docs, 30 data, 54 screenshots).` Method: copy-into-clean-tree, working folder untouched.
- `sanitise_stage7.py` written (imports build_unified's own rules) and run: 4 exports → `data/stage7/`, 0 residuals on two independent checks, resource name kept; every documented Stage 7 figure reproduces on the sanitised copies. Manifests not copied.
- Screenshots: 54 copied and renamed per §5; prompt lines cropped by code and checked; masks placed by coordinate and verified by eye on **ten** images — the five planned (kickoff 02/05/06/09/10) plus **Stage 1 01/02/03/06c-review/06d (F-S8-13: the "redacted" zip was not redacted)**; the Azure portal top bar carrying the directory name found on kickoff 04/05/08/13 and analysis/10 and cropped off (F-S8-14).
- Text sweep: email, tenant, machine name, `/Users/`, old repo name, AWS account id — 0 hits outside publication_check.py's own patterns.
- `requirements.txt` written from the import grep: duckdb, pyarrow, pandas, openai (no script imports sqlglot).
- Reference-validator log (19 Aug, 232 lines, 0 identifiers) added as `docs/reference-validator-run.log` — the L2 exhibit.
- Excluded from the tree: `#` (a stray DuckDB file), batch_input.jsonl, batch_id.txt, root duplicates of report/spec/lifecycle, gitignore.additions, validate_pre_stage6.py, all manifests under data/raw, AWS log (Step 6 default), STAGE8_WORKING_NOTES.md (carries command strings with the machine name; publish a scrubbed copy at Step 12 or not at all — decide then).
Sweep the C3 table item by item with grep; file screenshots per the C4 index; blur check image by image. Every doc-referenced screenshot exists under the name the doc uses; no orphan screenshots.
**Also at this step:** salt comment in build_unified.py (D-S8-4) · `.gitignore` gets `spec_cache/` and `data/raw/` confirmed (D-S8-5) · sanitised Stage 7 exports built into `data/stage7/` (D-S8-1, scope F-S8-7 incl. the `x_SkuDetails` blob) · switch the two paths in stage7_queries.sql to `data/stage7/`. Needs `build_unified.py` and `publication_check.py` uploaded.
**13 Sep run results:** `data/raw/stage7/` holds 8 files (4 parquets + 4 manifests); `.gitignore` had no content before today — now `spec_cache/`, `data/raw/` and (after the run below) `.venv/`, `__pycache__/`, `focus_validator/`, `.DS_Store`, `*.xlsx`. `stage4/02-negative-run-14-of-14.png` taken 13 Sep (crop the prompt line).

**D-S8-7 · Layout: scripts are at the project root, not `src/`.** The README and the patched reproduce block say `src/`; the folder says root. Three scripts confirmed to resolve paths from either place (`validate.py`, `build_unified.py`, `publication_check.py`). The rest are checked with a one-line grep; if all nine support `src/`, they move there in one command ; if any does not, the README and the reproduce block say root and validate.py's block is reverted. **Grep result 13 Sep:** support `src/` — build_unified, check_files, generate_layer_c, publication_check, seed_data, self_test, spec_source, validate, validate_pre_stage6. Do NOT — version_diff, rules (module), loader, run_queries, run_stage6, export_for_looker, generate_tokens_batch, sum_batch_usage. **Decided: root layout.** validate.py's reproduce block reverted to bare names (third delivery, 13 Sep — overwrite and re-run `python3 validate.py --report` once so the report text matches; no new screenshot needed). Publish-tree script list: the nine core (spec_source, rules, validate, version_diff, seed_data, self_test, build_unified, generate_layer_c, check_files) + publication_check + Stage 5/6 tooling (loader, run_queries, run_stage6, export_for_looker) + Stage 7 (generate_tokens_batch, sum_batch_usage). **Excluded:** validate_pre_stage6.py (superseded).

**publication_check.py read 13 Sep:** blocking check builds its deny-list from `data/raw/` (now including the Stage 7 exports — so a leak of the billing-account id into any `.md/.py/.sql/.json` blocks by construction); `.sql` is in scope; it does not scan parquet (the sanitiser's residual scan covers those — the Stage 7 script must run that too); it does not list `.venv` — `.gitignore` must. It expects `focus_unified.snappy.xlsx` NOT to be at the root.

**Screenshot inventory so far:** the Drive download arrives as one zip per stage and uploads fine (Stage 4: 16 MB, 38 images + 3 md copies) — so the manifest is simply each stage's zip, listed here as received. Stage 4: 38 images; the index needs at most two (`02-negative-run-14-of-14` — re-run fresh instead; `03-reference-validator-run` — if it exists, else omitted and said so in L2). The other 36 stay unpublished. Still to receive: stage1, stage5, stage6, stage7-kickoff, stage7-analysis zips.

### Step 10 — `publication_check.py` clean run, private repo, cold read · CHECKER CLEAN 13 Sep; repo + cold read are yours
**Checker run in the tree with data/raw present as the deny-list:** first run **blocked** — `data/raw-sanitised/31 July 2026/manifest.json` carried the subscription id inside `exportConfig.resourceId` (F-S8-12: build_unified.py verified the parquet, not the manifest). Fixed at source (`_sanitise_tree` on the carried-over config) and in the delivered manifest; second run: **47 real identifiers checked against every publishable file — none appear — exit 0**. Advisory tier lists README (dashboard id), token log (batch ids), synthetic CSVs/scripts (all-zero ids), Stage 7 notes (job/batch ids) — all expected. publication_check.py patched: `.csv`/`.log` scanned, `.venv` in the ignore list.
**validate.py run inside the tree:** 166 checks, same 8 datasets, report identical to the 13 Sep one except the reproduce block (root layout), exit 1 as documented, `--negative` 14 of 14.
**Yours (Mon 14):** unzip to `~/Documents/azure-focus-pipeline/` · visual pass over `screenshots/` (54 images, open each once) · in Terminal: `cd ~/Documents/azure-focus-pipeline && python3 publication_check.py` (expect "CANNOT RUN" on the blocking tier — data/raw is not in the zip by design; the clean run above is the record, or copy `data/raw` in from the working folder first for a full re-run) · screenshot → `stage8/03-publication-check-clean.png` · `git init && git add -A && git commit -m "P1: Azure → FOCUS pipeline"` · create the **private** repo `NakitaMei/azure-focus-pipeline` on GitHub, push · cold read of README on GitHub.

### Step 11 — C6 teardown · DONE 13 Sep
**Ledger:** `C6 ✅ 13 Sep — final bill captured first: $14.95 (22 Jul–13 Sep; disk 9.14, IP 5.24, tokens 0.56, bandwidth <0.01, Automation 0.00; rg-p1-sandbox 14.39 / networkwatcherrg 0.56). Deleted in order: oai-p1-sandbox (dialog screenshot, id masked) → gpt-4.1-nano-1 deployment (resource kept) → vm-web-01 (OS disk went with it) → stragglers found in the RG list: vm-web-01-ip (the $5.24 meter — the delete pane had not offered it), NIC, NSG, SSH key, vnet, free App Service + plan → auto-p1-sandbox with its two runbooks. End state: rg-p1-sandbox holds stp1sandbox only; NetworkWatcherRG keeps the idle AI resource; budget, alerts, exports and AWS untouched. Screenshots filed: stage8/01, 02, 05; stage7-analysis/18 (NetworkWatcherRG $0.56). README gained the final-bill paragraph. Checker clean; zip re-cut.`
**Lesson kept:** the VM delete pane offered the disk but not the public IP; the IP would have billed on. Always finish teardown from the resource-group list, not the VM blade.
*(original plan)* **Order matters:** (1) Cost Management → Cost analysis, scope = subscription, date range = 22 Jul → today, accumulated view — screenshot the total: `stage8/01-final-cost-analysis-total.png`. Nothing is deleted before this exists. (2) Delete `oai-p1-sandbox` (rg-p1-sandbox; the idle twin) — screenshot the confirmation → `stage8/02-teardown-oai-p1-sandbox-deleted.png`. (3) Delete the `gpt-4.1-nano-1` deployment on `nakitameiring-6066-resource`; the resource itself: your call (it bills nothing idle; deleting it also deletes the reconciled history in the portal — keep is fine). (4) `vm-web-01`: it is already deallocated on the schedule; delete the VM, then its disk and public IP. (5) Delete the Automation account `auto-p1-sandbox` **after** the VM. (6) Keep: storage account + both exports (the daily tick is the pipeline), budget + alerts, AWS. Sanitisation on all four stage8 shots: crop the portal top bar; blur any subscription id.
`stage8/01-final-cost-analysis-total.png` **before** anything is deleted. Then: delete `oai-p1-sandbox`; delete the `gpt-4.1-nano-1` deployment (resource: your call); deallocate `vm-web-01` after final screenshots, delete disk + IP; delete Automation account after the VM; keep storage account + both exports; keep budget + alert; keep AWS.

### Writing pass (13 Sep, after Nakita's read of the case study and README)
Feedback: too mechanical, em-dash punctuation, terms undefined (RFC 2119, "7 checks", "18 rules"), no "why", no safeguards section, folder instructions in prose read cold; wants a short-paper register. Rewritten: **CASE_STUDY.md** as a ten-section paper (abstract · why · background with the three terms defined · method incl. the seven cross-dataset checks and the eighteen refused rules named · eight findings · finance-twin table · **safeguards section, nine controls each tied to a finding** · what did not work · limitations · Framework table · conclusion), 4,700 words with tables. **README.md** rewritten in sentences with the seven checks and eighteen rules spelled out where mentioned, "Honest scope" replaced by "What this is, and what it is not", final bill included, 2,400 words. **GOVERNANCE_NOTE.md** rewritten in a warmer register, 660 words, still four controls, still ends with the rotation as a fact. Findings and cadence documents: dashes replaced, content unchanged. Zero em dashes across all five documents. Checker clean; zip re-cut (**the local commit predates this: rebuild from the newest zip before pushing**).

**Second writing pass (13 Sep):** FINDINGS_AND_RECOMMENDATIONS (prose rewritten around the table: how to read it, what real/synthetic means, why the order; "what to do first" as five paragraphs), CADENCE_AND_BUSINESS_CASES (prose rewritten around the cadence table; both business cases in full sentences), READINESS_MEMO (fully rewritten: verdict, terms defined incl. Mandatory/Recommended/Conditional and covered/covering, what is satisfied, the eight-item change list, adoption guidance, the consolidation-entry note, bottom line). Conformance report left as generated on purpose; working notes left as written. All six reading-list documents: zero em dashes. Checker clean. Zip re-cut: **`azure-focus-pipeline (3).zip`** is the one to rebuild from. Nakita: "happy for this to go live" once the reading list is at this standard.

### Step 10b + 12 — runbook issued 13 Sep evening
**F-S8-15 (13 Sep):** the first local commit was made from the previous zip (128 files, no `stage8/`) and with no git identity — author stamped `<<user>@<machine>.local>`, the machine name, which would have been published in the commit history. Caught before push. Fix: set `user.name` / `user.email` (GitHub no-reply address) globally, rebuild from the 132-file zip, verify with `git log -1 --format="%an <%ae>"`.
**Order:** A set identity → B find newest zip → C rebuild + commit + verify (132 files, `stage8/`, no `.local`) → D read README + CASE_STUDY (edit locally + commit, or hand words to me — not both) → E private repo, push, verify author on GitHub → sleep → G: cold read on GitHub · checker with `data/raw` copied in → screenshot → remove `data/raw` · Danger Zone → Public · screenshot · description + topics (`finops focus azure cost-management duckdb`) + pin · send both screenshots → filed → one commit-and-push closes P1 · LinkedIn separately.

**10b ✅ 13 Sep 17:00 SAST** — private repo `github.com/NakitaMei/azure-focus-pipeline` live: commit 484424c, 132 files, 5.89 MiB, author NakitaMei (no-reply address; no `.local`), README renders in full. Three empty Finder duplicates (`data 2`, `docs 2`, `screenshots 2`, `.git 2`) removed locally; never in the commit. Stage 1 screenshots re-checked by Nakita on the Mac: no ids. Key-shaped-string scan across the tree: none. Remaining: About description + topics + pin; then Step 12.

### Step 12 — C7 publication day (Mon 14 or Tue 15 Sep) · runbook above
Cold pull → checker screenshot → visibility Public → `stage8/04-repo-public.png` → pin + description + topics → LinkedIn headline/about/featured → update the portfolio notes: P1 LIVE, date, URL.

---

## 4. Findings log (Stage 8's own)

| # | Finding | Where | Action |
|---|---|---|---|
| F-S8-1 | Drive screenshot folder not reachable by the connector (third time: 7 Sep, 8 Sep review, 9 Sep) | §1 | Manifest workaround; images reviewed one at a time later |
| F-S8-2 | `queries.sql` uploaded as the Stage 7 file is the Stage 5 file | §0 | stage7_queries.sql requested at Step 1 |
| F-S8-3 | 65% counterfactual has no arithmetic behind it anywhere in the notes | §2 | Removed at Step 4; 70.2% / ≈70% at PAYG is the one number |
| F-S8-4 | Delivered SQL pointed at `data/raw-sanitised/` before that folder exists; local run failed | Step 1 | Paths set to bare filenames for now; repo target noted in the file and re-set at Step 9 |
| F-S8-5 | Sep 6 provisional 0.2837 (7 Sep pull) settled to 0.3344 (8 Sep pull) | Step 1 | Comment fixed in SQL; notes §10.1 at Step 4; keep both readings on the record |
| F-S8-6 | Compute meter absent on deallocated days (Basv2 4 rows / 6 days); Automation meter bills 0.0000 | Step 1 | Case-study chunk 4 paragraph, Step 8 |
| F-S8-7 | September parquets (1.0r2, 95 rows × 96 cols; 1.2-preview, 95 rows × 105 cols) carry the subscription id in `ResourceId`, `SubAccountId` and 7 rows of the `x_SkuDetails` JSON blob, and the billing-account id in `BillingAccountId` / `x_BillingAccountId`; no email | 13 Sep scan | Sanitisation scope for `data/stage7/` at Step 9 — the blob needs a string replace, not a column replace |
| F-S8-8 | Azure export manifests (`*.manifest.json`) carry subscription and billing-account ids in plain text | 13 Sep | Never committed; the parquet copies are the reproducible input, manifests stay in your records |
| F-S8-12 | Sanitised July manifest carried the subscription id in `exportConfig.resourceId`; build_unified verified the parquet only | checker, 13 Sep | Fixed at source (`_sanitise_tree`) and in the delivered file; checker clean |
| F-S8-13 | Stage 1 "redacted" zip was not redacted: tenant domain (01), email (02, 03), subscription id (06c-review, 06d) | visual, 13 Sep | Five masks placed and verified |
| F-S8-14 | Azure portal top bar shows the directory name in a thin strip on kickoff 04/05/08/13 and analysis/10 | visual, 13 Sep | Cropped off |
| F-S8-11 | `.gitignore` was empty/absent until 13 Sep; scripts live at the project root while the README says `src/` | 13 Sep run | `.gitignore` populated (run block); layout decision D-S8-7 |
| F-S8-10 | Real Aug/Sep exports (4 parquets + 2 manifests) sat at the project root, inside the repo folder | f6 grep | Moved to `data/raw/stage7/` (D-S8-6) |
| F-S8-9 | 1.2-preview export exists at billing-account scope (105 columns) beside the 1.0r2 subscription-scope export (96 columns), same period | 13 Sep | README version paragraph: the "1.2 only at billing-account scope" claim is backed by a live file |

---

## 5. Screenshot filing plan (13 Sep) — every published image, by source name

Legend: **blur** = a value to mask before copy (done in Preview: rectangle + fill) · **crop** = remove the terminal prompt line (username, machine, folder name). Sources are paths inside the Drive stage folders as downloaded. Nothing not listed here is published.

### stage1/ — strip the `screenshots_` prefix, keep the names
All 14 files (`01-billing-account-type` … `06d-focus-export-list`, incl. `05-VM-1/2/3`, `05a1/05a2-storage-config`, both `06c-…`). Zip is labelled "redacted" — spot-check two at Step 9 for subscription id and email.

### stage4/ — from the 13 Sep runs (not the Drive folder; its 67 images stay unpublished)
| New name | Source | Treatment |
|---|---|---|
| `01-validate-report-run.png` | 13 Sep 12:46:24 (`--report`, header + datasets discovered) | crop |
| `02-negative-run-14-of-14.png` | 13 Sep 13:07:25 (`--negative`) | crop |
| `03-reference-validator-run.png` | not located — omitted; L2 says so | — |

### stage5/ — fresh runs 13 Sep (3 terminal shots) + Looker (5)
Source folder for all 13 Sep shots: `stage8-runs/` on the Mac.
| New name | Source | Treatment |
|---|---|---|
| `01-showback-reconciling-tieout-bridge-budget-burndown.png` | 13 Sep 13:21:46 (queries 1a–2b) | crop |
| `02-outofscope-anomaly-incident-savings-blockpricing.png` | 13 Sep 13:22:25 (queries 2c–5) | none |
| `03-commitment-utilisation.png` | re-take with `.maxwidth 0` (13:22:07 is cut to 5 of 14 columns) | crop |
Looker, all from `Stage 5/Looker /Display/`:
| New name | Source | Treatment |
|---|---|---|
| `14-looker-executive.png` | USD/ 12.06.48 | none |
| `15-looker-team-showback.png` | USD/ 12.05.46 | none |
| `16-looker-anomaly.png` | USD/ 12.06.10 | none |
| `17-looker-budget-vs-actual.png` | USD/ 12.06.31 | none |
| `18-looker-eur-filter-currency-separation.png` | EUR/ 12.10.28 (the §5.1 exhibit: same page, EUR only, 6.62) | none |

### stage6/ — fresh runs 13 Sep (4 shots)
| New name | Source | Treatment |
|---|---|---|
| `01-reconciliation-q1-q6.png` | 13 Sep 13:23:12 (Q1 ties, Q3 grand proof, Q4 empty, Q5 matched, Q6 pass) | crop |
| `02-coverage-q7-q11.png` | 13 Sep 13:23:28 (85.5 vs 63.4; EUR gap; buckets; utilisation) | crop |
| `03-four-timezone-proof.png` | **to take**: the `for tz in …` loop (run block, 13 Sep) | crop |
| `04-validate-cross-dataset-ten-info.png` | 13 Sep 12:47:04 (the 6e-bis panel) | crop |
The 38 old stage 6 images stay unpublished.

### stage7-kickoff/ — `Stage 7 /setup/` (13 files → 14 names)
| New name | Source (SAST) | Shows | Treatment |
|---|---|---|---|
| `01-openai-deploy-blade-batch-50pct-quota-2m.png` | 15.13.41 | Global Batch "50% less cost"; enqueued tokens 2,000,000 / 50,000,000 (covers index 18) | none |
| `02-openai-deployment-created.png` | 15.16.59 | gpt-4.1-nano-1, GlobalBatch, 3:16 PM | **blur** "Create By" and "Modified by" emails |
| `03-rbac-classic-near-miss.png` | 15.50.09 | Role = Classic Virtual Machine Contributor (F-K8) | none |
| `04-rbac-vm-contributor-corrected.png` | 15.51.37 | Role = Virtual Machine Contributor | none |
| `05-runbook-stop-created.png` | 15.57.15 | Stop-SandboxVM, status New, 15:55 | **blur** Subscription ID |
| `06-runbook-start-published.png` | 16.03.20 | Start-SandboxVM Published 16:02 | **blur** Subscription ID |
| `07-manual-stop-job-succeeded.png` | 16.08.39 | job 16:05:31, op 2:06:18–32 PM UTC (14 s) | none |
| `08-manual-start-job-succeeded.png` | 16.12.24 | job 16:10:18, op 2:11:03–32 PM UTC | none |
| `09-schedule-nightly-stop.png` | 16.14.14 | daily 18:00 SAST, no expiry | **blur** directory label (tenant `…onmicrosoft.com`) top-left |
| `10-schedule-weekday-start.png` | 16.16.53 | Mon–Fri 08:00 SAST from 01/09 | **blur** directory label |
| `11-schedules-both-on.png` | 16.19.49 | both schedules On, next runs | none |
| `12-schedule-linked-stop.png` | 16.24.15 | Stop-SandboxVM ← Nightly-Stop | none |
| `13-schedule-linked-start.png` | 16.24.48 | Start-SandboxVM ← Weekday-Start | none |
Index items 14–17 (budget confirmed, subscription disabled, export rebuilds) — **no screenshot exists**; omitted, stated in the kick-off LOG as not captured. 18 covered by 01; 19 covered by stage7-analysis/02.

### stage7-analysis/ — `Stage 7 /Open AI/` + the two later shots
| New name | Source | Treatment |
|---|---|---|
| `01-job-history-through-6-sep.png` | `A1-runbook-job-history.png` | none |
| `02-cost-analysis-openai-line.png` | `A4-cost-analysis-openai.png` (scope NetworkWatcherRG, resource name, $0.28 — covers kickoff 19) | none |
| `03-token-reconciliation-c2-c2b.png` | `Screenshot 2026-09-08 at 08.19.54.png` (C2 + C2b, both exact ties; folds index 04) | none (no prompt) |
| `05-unit-economics-c3.png` | **re-run** C3 from today's stage7_queries.sql — the two old C3 shots are truncated to 5 of 7 columns | crop |
| `06-scheduling-c4abc-fri-sat-identical-meter-anatomy.png` | `Screenshot 2026-09-09 at 08.54.39.png` (folds index 07) | none |
| `08-autoscale-provider-unregistered.png` | `Before exibit 1 Screenshot 2026-09-07 at 09.48.05.png` (Autoscaling greyed: "needs Microsoft.Insights registration") | none |
| `09-autoscale-provider-registered.png` | `chunk5-insights-registered.png` | none |
| `10-autoscale-rule-configured-min2-max20.png` | `chunk5-autoscale-blade_4.png` (2, 20, 2; 80%/20%) | none |
| `11-key-regeneration-confirm.png` | `Governance_key_regeneration.pnp.png` (keys already masked) | none |
| `14-promotion-trio-columns.png` | **take now**: `DESCRIBE` of the 1.2-preview file (column names only — run block) | crop |
| `15-batch1-portal-timeline.png` | `A2-batch1-detail.png` (created 3:28 → completed 3:36 PM: the 6–8 min) | none |
| `16-batch-jobs-both-completed.png` | `Batch 2 png.png` (Sep 7 6:49 AM local; Aug 31 3:28 PM) | none |
| `17-scheduling-before-fix-token-rows-absorbed.png` | `Screenshot 2026-09-08 at 08.20.22.png` — the pre-F2 query absorbing the OpenAI line into C4c (the "what didn't work" exhibit) | none |
Index 12/13 (manifest shots) — none exist; facts are in the notes and the manifests carry ids → omitted. **Not published:** `A6-openai-resource.png` (subscription id, idle twin), `Before exibit 2`, `chunk5-autoscale-blade_1/2/3`, 07 Sep 08.16/09.42 terminal shots, 08 Sep 08.20.10.

### stage8/ — taken on the day (Step 11/12): `01-final-cost-analysis-total` · `02-teardown-oai-p1-sandbox-deleted` · `03-publication-check-clean` · `04-repo-public`.
### aws/ — see Step 6 (default: out).

**Totals:** stage1 14 · stage4 2 · stage5 8 · stage6 4 · stage7-kickoff 13 · stage7-analysis 13 · stage8 4 = **58 published**, from 220 in Drive plus the 13 Sep runs. Blur list: kickoff 02, 05, 06, 09, 10 (five images). Crop list: every terminal shot.

---

## 6. Closed: P1 live, 13 September 2026, 17:23 SAST

`github.com/NakitaMei/azure-focus-pipeline` was made public on the evening of
13 September, two days ahead of the planned date, on the decision that the
working week ahead would leave no room for it. The private push had gone up
at 17:00 the same day; the About panel carries the description and nine
topics; the publication checker's clean run (screenshot 03) and this note
went into the closing commit with the public-page screenshot (04).

Stage 8 closed with all twelve steps accounted for: nine done as planned,
the AWS log taken out of scope by default, the private-repo and cold-read
step done as one, and publication brought forward. Fifteen Stage 8 findings
are logged above. The three that mattered most were found by the controls
rather than by luck: the manifest leak by the checker, the unredacted Stage 1
screenshots by the visual pass, and the machine name in the first commit's
author line by the check before the push.

The sandbox is torn down to a single storage account with its exports,
budget and alerts intact. The final bill for the project was $14.95.

What comes next is the launch, not the project: the LinkedIn post, the
FinOps Story on version drift, and the message to Henrique, all before
flying on the 20th.
