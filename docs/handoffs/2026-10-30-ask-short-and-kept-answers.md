# Handoff, 30 October 2026: short answers, and listed questions open their answers

John's emails of 30 October ("Puzzled", "Repeat question") asked for answers of two or three sentences unless more is asked for, and for each listed question to link to the answer it got. Both shipped in PR 56.

## Shipped

1. **PR 56** (merge `97ce6fb`).
   * **Short answers.** Answering rule 12 asks for two or three sentences, under 400 characters not counting a quotation, longer only when the question asks for more ("tell me more", "in detail", "list them all"). Rules 2, 4 and 10 make room for the short form.
   * **The answer guard checks a count line sentence by sentence.** The short answer to "Which solutions have the most approval?" is the counts alone, 211 characters, and the old 200 character limit on the whole paragraph dropped it in 3 of 3 runs. Case A18 ("Tell me more.") was added to `tests/ask_cases.json`.
   * **Kept answers.** A `Question` keeps the answer it last got (`answer`, JSON text) and an `id` (uuid4 hex, unique constraint `question_id`, made at startup with `ASK_ENABLED`). The list under the box links to `/ask/answers/<id>`. That page shows the answer, its day and Ask again, but only while every post it cites is there, unedited since and under the same name. Questions kept before 30 October have no answer and stay buttons.
   * Copy changed: the note under the box, the About paragraph and the operator's guide. Docs: `03_schema.md` (Q47 to Q49), `04_interface.md`, `05_extraction.md`, `code-map.md`, `CLAUDE.md`.

## Verified

Before merge:
* `pytest -m "not live"`: 1181 passed. `node --test tests/*.cjs`: 116 passed. `pytest -m live` on a disposable local Neo4j: 142 passed, including the new `tests/test_live_questions.py`.
* Case run on the fixture record with the language model, 9 cases: all answered as expected, with no paragraph dropped. On 29 October, 7 of 15 runs had dropped a paragraph. Most answers are one paragraph of 420 to 510 characters. A18 gives 3 to 4 paragraphs.
* Local walk on the fixture record:
  * a question on an issue page got a two sentence answer and was listed as a link;
  * the link opened the answer page;
  * with one cited post marked edited, the page withheld the answer;
  * Ask again answered afresh and the page showed again;
  * "Tell me more." gave 3 paragraphs;
  * phone width checked.

After the deploy, read back on the live site:

| Check | Expected | Live |
|---|---|---|
| PR 56 deploy (GitHub deployment `7437896761`, `97ce6fb`) | success | success, 12:11 UTC |
| `scripts.smoke` | all pass | 25 of 25 passed |
| `/about` signed out | new answer and kept-answer wording; "Answers are not kept" gone | as expected |
| `/ask/answers/<id>` signed out | sends to sign in | 303 to `/sign-in?next=…` |
| `/static/ask.js`, `/static/app.css` | the link code and the answer page styles | present |

Not read back live: a signed-in answer, the link under the box, and the `question_id` constraint. Asking on the live site keeps a question for everyone (rule 11). These are covered by the tests and the local walk above. John's next question will be the first live one.

## Left

* **A follow-up such as "Tell me more." is listed for everyone** like any question, as "And why?" has been since 28 October. On its own in the list it says little. To decide: leave it, list only questions asked without earlier ones, or show the question it followed.
* **GitHub issue 55, "Write about this solution"** (John, 30 October): a page for each solution and each piece of evidence, each with a Write link, reachable by asking and from the buttons under statements. Not started; it needs agreeing first.
* The answer guard still drops a paragraph without a word when one breaks its rules. This is now rare in the case run.
* Carried over:
  * Remote branches of merged PRs are not deleted.
  * Duplicate solutions can be merged with Tidy.
  * John cannot remove a listed question himself.
