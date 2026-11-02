# Handoff, 2 November 2026: no sub-issues, reasons as evidence

John, 1 November 2026: a reason someone gives, such as opposing data centers because they raise the price of electricity, is evidence, not a sub-issue. The site stops identifying sub-issues: a statement is read into issues, solutions and evidence only, the "Part of" choice leaves the form and the tidy tools, and Merge stays. Branch `reasons-as-evidence`, merged on Eston's go on 2 November 2026 (PR 63, `eda3161`, live 11:51 UTC).

## Built

* **The reading** (`app/extract.py`): the sub-issue rules are gone; a narrower point about an issue (a harm it does, a cost, a resource it uses) is evidence supporting it, even when the writer calls it a sub-issue; a reason given with because, since or as is evidence supporting what it argues for or refuting what it argues against. How serious the writer says an issue is, a restatement, and what a proposal is or how it would work are not evidence; a declaration, charter or report the writer names still is. Two examples replace the Data centers sub-issue example. The reading gets issue names only, and `writing_about` for an issue as its name only. Word for word in `docs/planning/05_extraction.md`, "Reasons as evidence, no sub-issues".
* **The payload and the write path**: an issue row has no `parent`, and one sent by the reading or an older card is ignored. A post writes no `PART_OF`. The seed's issues block still does, a back-room copy holding `PART_OF` still restores, and every page that shows a tree (the Issues page, an issue page's Sub-issues, "Part of" above the form, breadcrumbs) still shows one already in a record. Editing a post never touched `PART_OF` and still does not.
* **The card**: no "Part of" select; the two lines telling testers how to add a sub-issue are gone (write page and the "Already in the database" panel). The two switches-off copies of the write page in `tests/fixtures/pages_before_phase3/` were refreshed for that line alone.
* **Tidy**: the "Make it part of" select is gone. A sub-issue already in a record shows "Part of {parent}." and **Make it a top level issue**; a top level issue has no move. `POST /issues/<key>/move` ignores any `parent` it is sent. Rename and Merge are unchanged; Merge still moves the merged issue's sub-issues. Older "moved X under Y" changes still read as before.
* **Ask**: the line under an issue's box says "and its sub-issues" only on an issue that still has some.
* Docs: `03_schema.md` (revision note, statement 3b, Q28, PART_OF), `04_interface.md` (card, panel, tidy, Ask line), `05_extraction.md` (contract, user message, cases, the new section), operator's guide (tidying, the issue page buttons).

## Verified

* `pytest -m "not live"`: 1207 passed.
* `node --test tests/*.cjs`: 132 passed (the two "Part of" tests became one).
* `pytest -m live` on `oci-neo4j-test` (7688): 154 passed, including: a post never writes `PART_OF`, even with a parent in its JSON; a post on an existing sub-issue leaves its `PART_OF` as it is; a move only makes a sub-issue top level.
* `card.js` is 382 lines.
* Reading cases on deepseek-v4-flash, the last round of rules: cases 15, 24, 25 and 28 four runs each, 26 and 27 three, all as expected; John's paragraph (case 2), Beth's objection (13) and the opposition on a solution's page (20) four runs each, as before the change; cases 1 to 23 once. The one known difference is case 11 (a proposal made in passing is now kept, under a fuller name; once in four runs the writer's ranking of the problems became evidence). Every run is in `05_extraction.md`.
* Local walk on the development database:
  * language model off: the write page for Security Council veto (a seed sub-issue) shows "Part of Need for world government" above the form and no line about sub-issues; the form's issue row has no "Part of"; a reason added by hand as evidence posted, the veto kept its place under Need for world government; the veto's Ask line reads "about this issue", Need for world government's "about this issue and its sub-issues"; no console errors;
  * language model set: "I'm opposed to new data centers near St. Louis, because they are increasing the price of electricity for everyone." read as the issue Data centers and the evidence "Data centers raise electricity prices" supporting it (not posted).

## Review

A fresh review of the whole branch found nothing blocking (suites green on its side too). Its points, and what was done:

* Docs that still described a parent (`03_schema.md`, `05_extraction.md`, `04_interface.md`, `CLAUDE.md`): fixed.
* Two prompt wordings that could, in principle, flip a reason's side or make a "concern" a second issue: tested as cases 29 and 30, three runs each; the reason's side and the single issue were right every time.
* The no-JavaScript Ask result page passes the issue without its sub-issues, so its line says "about this issue" even on an issue with sub-issues (the answer still reads them). Left as is: only a record with a tree, with JavaScript off.

## Open

* Merged and live on 2 November 2026: smoke 25 of 25; the live Ask page, an issue page and the Write card read back as built.
* **An older fault found by case 29**, not caused by this change: "I oppose the Security Council veto" is read as opposing the solution "Limit or abolish the Security Council veto". The prompt before this change does the same. Fixed on the card by the stance guard (`docs/handoffs/2026-11-02-stance-guard.md`), since every change to the stance rules cost case 2 its evidence.
* The tidy box was checked through its route tests and the live tests, not in a browser: the local accounts' passwords are not known here.
