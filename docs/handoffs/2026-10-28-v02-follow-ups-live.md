# Handoff, 28 October 2026 (night): issue page buttons and recent questions are live

The two follow-ups from John's call and his "Announcing v0.2" email shipped tonight as part of Phase 3, at no charge (the builder's decision). This replaces the "left to do" lists in `2026-10-28-ask-recent-questions.md`, and the "recent questions go with the next phase" item in `2026-10-28-call-fixes.md`.

## Shipped

1. **PR 49** (merge `145a5d7`): a row of buttons under each issue's name, Sub-issues (n) when there are any, Solutions (n), Evidence (n), Ask (only with `ASK_ENABLED`), Posts and, for John only, Tidy. Each jumps to its heading; nothing is hidden.
2. **PR 50** (merge `6dc1f12`): the latest answered questions under the Ask box. "Questions people are asking" on `/ask` (10, each with "On <issue>" when asked on an issue page) and "Questions asked about this issue" under each issue's box (5). A tap puts the question in the box. Kept as `Question` (Q47, Q48 in `03_schema.md`), never with who asked; answers are still not kept. The Ask note and the About paragraph say so.
   * Found in the browser check and fixed before merge (`7b97899`): the "On <issue>" link was the browser's default blue and split after "On" at desktop width.
   * Brought up to date with main after PR 49 (`29b9c2e`): one conflict in `tests/test_ask_routes.py`, both sides' new tests kept.

## Verified

Before merge, on the combined branch: `pytest -m "not live"` 1157 passed, `node --test tests/*.cjs` 115 passed. On the local site against the disposable test Neo4j, with the language model on, at 375 px and desktop: a question answered on `/ask` and one on an issue page were each listed in the right place and still there after a reload; the issue page listed only its own; a tap filled and focused the box; no sideways scroll, no console errors; the same words again with other spacing and case stayed one question (`asked` 2) and moved to the top; the issue page showed the button row and the list together.

After each deploy, read back on the live site (signed in pages through an existing browser session that is not John's account, read only):

| Check | Expected | Live |
|---|---|---|
| PR 49 deploy (GitHub deployment `7396519610`) | success | success, 21:28 Berlin |
| `scripts.smoke --ref origin/main` after PR 49 | all pass, served files are `145a5d7`'s | 25 of 25 passed |
| Issue page "Climate change" after PR 49 | button row, every target on the page | Sub-issues (1), Solutions (10), Evidence (17), Ask, Posts; all 5 targets present |
| PR 50 deploy (GitHub deployment `7396572847`) | success | success, 21:31 Berlin |
| `scripts.smoke --ref origin/main` after PR 50 | all pass, served files are `6dc1f12`'s | 25 of 25 passed |
| `/about` signed out | new paragraph about listed questions; "Questions and answers are not kept" gone | present; 0 mentions |
| `/ask` signed in | "Questions people are asking", hidden while empty; new note under the box | hidden, 0 items; note matches |
| Issue page signed in | "Questions asked about this issue" under the box, hidden while empty; button row still there | matches |
| `app.css`, `ask.js` served | the new list rules and the tap handler | present |

Not read back live: a question being listed once answered, because that writes to the production database (rule 11). It is covered by the tests and the local check above. The lists are empty on the live site until someone's question gets an answer. The `Question` key constraint and `asked_at` index are made at startup with `ASK_ENABLED`; startup succeeded, but they were not confirmed on Aura directly.

## Left

* **No way for John to remove a listed question himself.** The operator's guide says to ask whoever helps with the site.
* John will send the v0.2 announcement a day or two after the US election.
* Reply drafts to John (the "Next phase" thread and "Announcing v0.2") are updated in the builder's mail to say both pieces are live; not sent.
* The SOW 0.3 draft (in the builder's private folder) holds Phase 4 (reaching agreement) and Phase 5 (talking, later); price, weeks and date are still blanks.
* Carried over from the call fixes handoff, not rechecked tonight: duplicate solutions ("Global carbon tax by referendum" and "Carbon tax") can be merged by John with Tidy.
