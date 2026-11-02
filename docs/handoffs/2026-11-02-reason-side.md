# Handoff, 2 November 2026: the reason's side

PR 65's live read back: on John's record the veto solution sits under Need for world government (no Security Council veto issue), so "I oppose the Security Council veto because it has blocked action on Syria." came back with the reason REFUTING "Limit or abolish the Security Council veto", on the side of the model's dropped oppose. Eston: "Yes, fix it". Branch `reason-side`, not merged.

## Built

* `app/extract.py`: when the stance guard drops a row, reasons about that solution take the side of the writer's stance word (`_reason_side`): against words make them support the solution, for words make them refute it. Both kinds of word, or a negated stance, leave them as read. `stance_dropped` logs `reasons_turned`.
* `scripts/cards.py`: context `world`, the live record's shape. `tests/extraction_cases.json`: cases 33 and 34; case 31's note updated.
* Tests: `tests/test_reading.py` (both sides, "against", negated, mixed, a reason about something else).
* `docs/planning/05_extraction.md`: "The reason's side" under the stance guard. `docs/handoffs/2026-11-02-stance-guard.md` now says PR 65 is merged.

## Verified

* Offline, page scripts and live (7688): see the PR.
* DeepSeek: case 33 4 of 4 (reason supports the abolish solution, no stance), case 34 4 of 4 (reason refutes it), case 29 and case 31 4 of 4 each (31 now right), every other case once as expected.

## Open

* Eston's go to merge. Merging deploys John's live site. After it, `git fetch`, `scripts.smoke`, and one live `/api/extract` reading of case 29 (nothing posted).
