# Handoff, 28 October 2026: the four fixes from John's call

John's call of 28 October (17:00 Berlin) confirmed Phase 3 is switched on in Render (all four switches) and asked for four changes. All four shipped in **PR 47** (merge `4a799fb`).

## Shipped

1. **Ask gives a verdict on a guiding document.** For "is X consistent with article or principle Y", the answer quotes it, then says plainly yes, partly or no, judged only by setting the solution's own words beside the document's, then how. Every other question still gets no verdict. Rules 2 and 10 in `app/ask.py` (mirrored in `05_extraction.md`), cases A16 and A17. Case run of 28 October on the fixture (deepseek-v4-flash): A16 says the tax fits 7d and where it falls short; A17 says Articles 25 and 28 do not make a missing tax a violation; A15, A2 and A7 as before; sources dropped 0.
2. **"Language model" instead of "reading service"** in every message, page, back room line and doc John or a tester reads (John's email of 28 October). Code comments keep the old name. CLAUDE.md rule 5 allows "language model" site wide; `tests/test_wording.py` keeps "reading service" off pages, page script strings and server messages.
3. **About from the sign in page:** "About this site" under "Forgot your password?", only while `ABOUT_ENABLED` is set; switched off, the page is unchanged byte for byte.
4. **Ask the database:** the box is empty with the cursor in it (`autofocus`), no example question, like the Write page. The issue page box keeps its example.

## Verified

Before merge: `pytest -m "not live"` 1143 passed, `node --test tests/*.cjs` 112 passed; the local site showed the About link on sign in and `/about` signed out.

After the deploy (GitHub deployment `7395206543`, success, 28 October 20:28 Berlin), read back on the live site signed out:

| Check | Expected | Live |
|---|---|---|
| `scripts.smoke --ref origin/main` | all pass, served files are `4a799fb`'s | 25 of 25 passed |
| Sign in page | "About this site" under "Forgot your password?" | present |
| `/about` signed out | opens, no "reading service" | 200, 0 mentions |
| `app.js` slow message | "The language model is not answering right now" | matches |
| "reading service" in served page scripts | comments only | `ask.js` 1 and `evidence_check.js` 2, all comments |

Not read back live (needs signing in, and the verdict needs a question to the language model on the production site): the empty Ask box with the cursor in it, and the 7d verdict. Both are covered by tests and the case run above; John can try "Is the proposed solution of a global carbon tax consistent with the Earth Charter, Article 7d?" on Ask.

## Left, for John or the next phase

* **A list of recent questions under the Ask box** (John on the call): needs questions and answers to be kept, which the site does not do. It goes with the next phase, not Phase 3.
* **Issue pages are long:** Ask about this issue sits far down on a top-level issue. An issue menu or tabs (Solutions, Evidence, Ask, Posts) was suggested on the call; not agreed or built.
* **Duplicate solutions:** "Global carbon tax by referendum" and "Carbon tax" should probably be merged. John can do it with Tidy.
* **Next phase (John's priority):** wiki style editing of a proposed solution, with reasoned objections and no unanimity, then a conversational interface by phone. A scope of work is being written; nothing is agreed.
* Follow-up questions were not tried by John on the call.
