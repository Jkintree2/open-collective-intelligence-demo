# Handoff, 30 October 2026: solution and evidence pages (GitHub issue 55)

John's GitHub issue 55, "Write about this solution", was quoted at 1,200 USD fixed on 30 October and invoiced (2026-10-30-006, period 31 October to 6 November). John accepted the same day. It is built on the branch `issue-55-solution-pages` as **PR 58**, which is open and not merged.

## Built

1. **A page for each solution**, `/solutions/<key>`:
   * breadcrumbs to its first issue, and "Write about this solution" at the top;
   * who proposed it, with anonymous posts kept anonymous;
   * the counts with Approve and Oppose (`_stance.html`; without JavaScript the form comes back to this page);
   * the issues it was proposed for, and its evidence, each linked to the evidence page;
   * the posts that mention it, and an Ask box.
2. **A page for each piece of evidence**, `/evidence/<key>`:
   * breadcrumbs, and "Write about this evidence" at the top;
   * its source link, who submitted it, and source confidence where its page was read;
   * what it supports or refutes, linked, and the evidence about it;
   * its posts, and an Ask box.
3. **Writing from either page.**
   * `/?solution=` and `/?evidence=` show what the database holds about it, and pass it to the reading as `writing_about`.
   * The card starts from the item's issue.
   * Three sentences were added to the reading rules. Details and the case run are in `docs/planning/05_extraction.md`.
4. **Links in:**
   * the chips under posts (Write page, issue pages, search, My statements);
   * solution and evidence names on issue pages, with a "source" link kept beside each piece of evidence;
   * search results on `/issues`;
   * solution and evidence sources under Ask answers.
5. **Questions** asked on these pages are kept with `solution_key` or `evidence_key`, and listed under that page's box.
6. **Schema and docs:**
   * New reads: Q50 to Q54 in `app/graph_item_pages.py`, plus Q40 and Q41 forms in `app/graph_ask.py`.
   * No new label, relationship type, constraint or index.
   * Updated: `03_schema.md`, `04_interface.md`, `05_extraction.md`, `code-map.md`, `CLAUDE.md`, and one paragraph in the operator's guide.

Out of scope, as agreed (Phase 4, SOW 0.3): a longer proposal text, editing it together, versions, and objections with reasons.

## Verified (before merge)

* `pytest -m "not live"`: 1206 passed (1198 before the review fixes below).
* `node --test tests/*.cjs`: 120 passed.
* `pytest -m live` on a disposable Neo4j (container `oci-neo4j-i55`, port 7697): 152 passed (151 before), including the new `tests/test_live_item_pages.py`.
* **Review fixes, 30 October** (Fable review of PR 58, findings 1, 3 and 4, and the missing backup test):
  * **Kept answers survive a revert.** A kept source no longer stores `page`, so its keys are exactly main's `Source` fields; `/ask/answers/<id>` works the page out again from the kind and `make_key(name)`. Answers kept before issue 55 now link too. Tested offline: kept sources from solution, evidence and issue pages hold only main's fields, and a kept answer without `page` links.
  * **First issue means the first to take the solution up.** Q50 orders a solution's issues by `HAVE_PROPOSED.created_at`; Q52 orders what evidence speaks to by its earliest edge there and picks a solution's home the same way. The solution digest (Q40 third form) has its own issues call in that order; the issue form of Q40 and Q42 are byte for byte as on main, so Phase 3's live digests do not change. Live test: a solution proposed for a newer issue first and an older one later. The old queries picked the older issue in all three places on that data.
  * **Evidence page without link reading.** "No source given." and "From personal experience." show only with `EVIDENCE_CHECK_ENABLED`, as on an issue page. "The writer's own words about ..." stays unconditional, like the source link (in 04).
  * **Backup:** a round trip and wrong-type cases for `Question.solution_key` and `evidence_key`.
  * Not re-walked in a browser after these fixes: the changes are covered by the tests above, and no template, script or style changed.
* Cards on deepseek-v4-flash:
  * New cases 18 to 22, three runs each: 15 of 15 as expected.
  * Cases 1 to 17, compared with the old prompt: unchanged except case 2 (below).
* Local walk-through on the Ask fixture record, signed in, all switches on, at 360 px:
  * the issue page links;
  * the solution page, with Oppose switched in place;
  * the evidence page;
  * Ask on a solution page, with the real model;
  * the kept answer page and the `/ask` list;
  * "Write about this solution", which posted the approval only;
  * "Write about this evidence";
  * search and My statements;
  * `LLM_API_KEY` unset: the card opens by hand and posts.
  * There was no sideways scroll and no 500.

## Open

* **Eston's go to merge PR 58.** The merge deploys the live site. After it, run `scripts.smoke` and open a live solution page and evidence page. Reading back a live Ask answer on a solution page would keep a public question, so leave that to John's first question.
* **Case 2 changed:** John's supreme law paragraph now reads approve on both existing solutions in 4 of 4 runs, where the old prompt read none in 4 of 4. The post then records the two approvals rather than claims and proposals. The case allows either answer. Say so to John only if he asks.
* **Writing from an evidence page claims the issue as well.** Like "Write about this issue", a statement written there claims the evidence's issue unless the writer clears that row. This keeps the post visible on the issue page.
* **Review finding 2, Eston's call:** the three new reading sentences are in the system prompt for every reading, not only with `writing_about` (case 2 above). Not changed; `app/extract.py` is as it was.
* **Not changed, smaller:** in an evidence digest a piece's own source still links to the first issue it speaks to directly, so it can name a different issue from the page's breadcrumbs when the evidence first spoke to a solution; and the review's other nits (post links in the new digests, "Proposed by 0 people", Q52 read twice).
* The disposable container `oci-neo4j-i55` (7697) was wiped by the live tests and holds only what the last one left (7 nodes); the walk-through record is gone. Remove it with `docker rm -f oci-neo4j-i55` when done.
* Carried over: "Tell me more." is listed publicly; remote branches of merged PRs are not deleted.
