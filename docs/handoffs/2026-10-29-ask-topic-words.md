# Handoff, 29 October 2026 (evening): Ask reads the issue a question is about

John's "Asking" emails of 29 October reported two whole-database questions on the Ask page that left things out. This shipped the fix for the first one as a fix to Phase 3, at no charge. The second is not yet explained.

## Shipped

1. **PR 53** (merge `dbc9d4d`): `ask.issue_query`. The search that picks a whole-database question's three issues leaves out the guiding documents' own names ("Universal Declaration of Human Rights", "UDHR", "Earth Charter", "Statement of purpose", "guiding documents"). Searched, those names found the evidence and solutions named after the documents first, so "How does the issue of climate change relate to the principles of the Universal Declaration of Human Rights and the Earth Charter?" read three issues about supreme law and a world government and never the climate issue. A question with nothing else to look for is searched whole, as before. The issue page's Ask box, the answering rules, the page and the copy are unchanged. `docs/planning/05_extraction.md` (record scope) and `docs/code-map.md` say so.

## Verified

Before merge: `pytest -m "not live"` 1165 passed, `node --test tests/*.cjs` 115 passed, `pytest -m live` on a disposable local Neo4j 138 passed. The new live test (John's question reads "global climate coordination" first on the fixture record) fails on the code before the change with "need for supreme law above nations". On the local site against the fixture record, John's question through `/api/ask` was answered, about climate, 3 issues read.

After the deploy, read back on the live site:

| Check | Expected | Live |
|---|---|---|
| PR 53 deploy (GitHub deployment `7420186069`, `dbc9d4d`) | success | success, 19:00 Berlin |
| `scripts.smoke --ref origin/main` | all pass, served files are `dbc9d4d`'s | 25 of 25 passed |

Not read back live: an answer to John's question, because an answered question is kept in the production database (rule 11), and the Ask pages need a sign-in. Covered by the tests and the local check above.

## Found on the way, not changed

* **The model does not pick Earth Charter 7d by itself.** On the seed it quoted principles 5, 6, 7 or 7b for climate, never 7d, with or without a nudge in the answering rules. Rule 10 names an article only when the question or a post does; with one post saying the carbon tax fits 7d, the answer led with 7d in 3 of 3 runs.
* **The answer guard drops paragraphs without a word.** It keeps paragraphs in order up to 1,200 characters and drops one with no post cited unless it is a short count line. The model often writes past its 1,000 character limit, and its document paragraph tends to come last, so it is the one cut. Seen in 7 of 15 local runs.

## Left

* **"What solutions have been proposed for the issue of climate change?" left out "Global carbon tax by referendum" on the live site.** Not reproduced on the seed (3 of 3 answers led with it). It needs a back-room copy of the live record, restored into a disposable local Neo4j.
* Carried over: duplicate solutions ("Global carbon tax by referendum" and "Carbon tax") can be merged by John with Tidy; John cannot remove a listed question himself.
* The local `.venv/bin/uvicorn` launcher points at the repository's old path; run `.venv/bin/python -m uvicorn` instead.
