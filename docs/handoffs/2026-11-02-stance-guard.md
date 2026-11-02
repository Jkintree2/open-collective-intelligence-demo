# Handoff, 2 November 2026: the stance guard

Case 29: "I oppose the Security Council veto because it has blocked action on Syria." was read as opposing the existing solution "Limit or abolish the Security Council veto" (3 of 3 runs), the opposite of what the writer means. Eston chose a guard in code after five changes to the reading rules each cost John's supreme law paragraph (case 2) its UDHR and Earth Charter evidence. Branch `stance-guard`, not merged.

## Built

* `app/extract.py`: `_stances_on_what_is_named`, run by `prepared_card` only when the statement text is given (the reading's card, and the copy `/api/posts` rebuilds from `extraction_raw`). It drops a stance row on an existing solution whose name holds a change word (limit, abolish, end, ban, stop, moratorium and so on) when the statement takes a stance in words, names the rest of the solution's name and uses no change word itself; the solution's issue is added when the card lacks it. Logged as `stance_dropped` with a count. The reading rules are unchanged (same hash).
* `scripts/cards.py`: a `moratorium` context (stlouis plus John's live "Moratorium on building new data centers").
* `tests/extraction_cases.json`: case 29 expects never oppose; new cases 31 (the mirror, "I support the Security Council veto…") and 32 ("I'm against new data centers in St. Louis…", moratorium context).
* Tests: `tests/test_reading.py` (the conditions, word forms, a card without text, a new solution) and `tests/test_card_api.py` (case 29 through `/api/extract` and `/api/posts`).
* `docs/planning/05_extraction.md`: "The stance guard", with the rule attempts, the conditions and the runs; case 29's note points at it. `docs/handoffs/2026-11-02-reasons-as-evidence.md` now says PR 63 is merged.

## Verified

* `pytest -m "not live"`, `node --test tests/*.cjs`, and `pytest -m live` on 7688: see the PR.
* DeepSeek, the reading rules as they stand: case 29 no oppose 9 of 9 (3 of 3 oppose without the guard); case 31 no stance on the abolish solution 9 of 9; case 32 as expected 5 of 5 (the model makes no moratorium stance here even without the guard); cases 8, 14, 18, 20, 22 and 25 keep their stances 4 of 4; every other case twice, as expected.
* The live record holds 4 of 39 solutions with change words (read on 2 November): Stop burning fossil fuels, Carbon removal through forests and soil, Limit or abolish the Security Council veto, Moratorium on building new data centers.

## Known

* Case 31's reason lands on the wrong side (supports the abolish solution); the prompt as it stands does the same without the guard. Not the guard's to fix.
* A writer who supports a change in other words and uses a stance word ("I support doing away with the veto") gets no stance and sets it on the form.

## Open

* Eston's go to merge. Merging deploys John's live site. After it, `git fetch`, `scripts.smoke`, and a live read back (reading only).
