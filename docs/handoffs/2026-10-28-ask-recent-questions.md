# Handoff, 28 October 2026 (evening): recent questions on Ask, and the issue page menu

Session moved to a fresh one because of length. Two pieces of work are open; neither is merged.

## 1. Issue page menu: PR 49 (branch `issue-page-menu`), done, awaiting merge approval

A row of buttons under each issue's name (Sub-issues (n), Solutions (n), Evidence (n), Ask, Posts, Tidy for John), each jumping to its heading. From John's call of 28 October. Tests green (1144 Python, 112 page scripts), checked at 375 px and desktop on the local site. Eston chose to do it at no charge (it was taken out of the SOW 0.3 draft).

## 2. Recent questions under the Ask box: branch `ask-recent-questions`, built, not yet opened as a PR

John's email "Announcing v0.2" (28 October, 20:04 UTC) asks for the list of the most recent questions on the Ask page before he announces v0.2 (he will wait until a day or two after the US midterms). Eston: "just do what he wants" (no charge).

Built on this branch:

* New label `Question {key, text, issue_key, created_at, asked_at, asked}`, no edges, never who asked. Kept only when Ask answered (`status == "answered"`). Same words on the same issue are one Question, moved to the top (`graph_questions.question_key`). Q47 (keep) and Q48 (latest) in `app/graph_questions.py`, spec in `03_schema.md`. Unique key and `asked_at` index made at startup only with `ASK_ENABLED` (`graph.QUESTION_INDEXES`, `ensure_constraints(asking=...)`).
* `routes_ask._keep` after an answer (failure only logged: `question_not_kept`); `routes_ask.recent_questions` for `/ask` (10, all) and the issue page (5, that issue; called from `main.issue_page`), failure only logged.
* `_ask.html`: list under the answers, "Questions people are asking" on `/ask`, "Questions asked about this issue" under an issue box, each a button; hidden when empty. `ask.js`: a tap puts the question in the box; an answered question joins the top at once. CSS `.ask-recent`, `.ask-again`.
* Copy: the Ask note and the About paragraph now say an answered question is listed for everyone, without the name of who asked, and answers are not kept. `04_interface.md`, the operator's guide, CLAUDE.md schema brief, `code-map.md` updated.
* Copies: `backup.LABEL_KEYS` has `Question` (without it a copy would fail once a question exists); `issue_key`, `asked`, `asked_at` validated.
* Tests: 1156 Python passed, `tests/test_ask.cjs` 15 passed, before the CSS was added.

Left to do on this branch:

1. Run the full suite again (`pytest -m "not live"` and `node --test tests/*.cjs`).
2. Look at it on the local site against the disposable test Neo4j (port 7688, `testpass1`, fixture loaded by `python -m scripts.asks --load`), at phone width and desktop: ask a question (needs `LLM_API_KEY` from `.env`), see it listed on `/ask` and under the issue box, tap a listed question.
3. Optionally a live test of Q47 and Q48 (`-m live`, port 7688).
4. Open the PR. Then ask Eston before merging either PR: every merge to main deploys to John's live site. After each deploy: `scripts.smoke`, and read back the live pages.
5. Both PRs touch `app/static/app.css` in different places; merge one, then bring the other up to date.

## Also open (outside the repo)

* Reply drafts to John in Gmail are not sent. The "Next phase" draft says the recent questions list goes in the next phase proposal; that is now out of date (it is being built now, no charge). John's "Announcing v0.2" email has no reply yet.
* SOW 0.3 draft (in the builder's private folder) now holds Phase 4 (reaching agreement) and Phase 5 (talking, later) only; price, weeks and date are still blanks for Eston.
* No way yet for John to remove a listed question himself; the guide says to ask whoever helps with the site.
