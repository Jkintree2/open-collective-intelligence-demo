# Handoff, 1 November 2026: a link named once, and a line for an unread statement

Two fixes from John's emails of 31 October, free under the 28 October terms (fixes to what was built are free through November). Branch `link-once-and-unread-line`, not merged.

## What John saw, and why

1. **"The statement after posting displayed the URL twice."** Evidence given only as a link is named after the link (`payload.link_name`). With no statement written, the card's lines become the statement (`text.sentences`, joined in `main.post_card`): "submits evidence <link>" and then "<link> refutes issue of …". His AEI link also kept Google's `gad_source` in its name, which the 120 character cap cut off mid-parameter.
2. **His counter proposal (majority votes, Robert's Rules) was never recorded** (31 October handoff, item 6). On a solution's Write page the card opens on arrival, so a statement written beside it was posted without ever being read.

## Built

* **One line for evidence named after its own link**: "{name} submits evidence {link}, which refutes issue of {issue}" (likewise supports, solution of, evidence of), in "What this will add" and so in a statement made from the card. A link with a name of its own, or with the writer's statement beside a page read the other way (issue 29), keeps its two lines. The feed's "show what was added" list keeps one line per thing added.
* **Tracking parameters** (`payload.TRACKING`: `utm_`, `gad_`, `gclid`, `gbraid`, `wbraid`, `fbclid`, `msclkid`) are dropped from link names and from the form in which two links count as the same (`link_key`, and `card.js` `linkKey` to match).
* **A line on the card when the statement has not been read**, **client-facing**: "Your statement has not been read yet. Press "Read my statement" to fill in the form from it." It shows when the card is open beside a statement no reading was asked for. It goes once a reading is asked for, even one that could not run, and does not come back when the statement is edited afterwards. It never shows with no language model, for a plain statement, or when editing a post. Post stays available.
* The write form carries `data-no-reading` whenever no language model is set, not only with the evidence check on, so the card knows. The two copies of the write page in `tests/fixtures/pages_before_phase3/` were refreshed for that attribute alone.
* Docs: 04_interface.md (both behaviours, the new line), 03_schema.md (tracking parameters).

## Verified

* `pytest -m "not live"`: 1212 passed (1208 on main).
* `node --test tests/*.cjs`: 133 passed (128 on main; new `test_card_unread.cjs`, and a tracking case in `test_card_same_link.cjs`).
* `pytest -m live` on `oci-neo4j-test` (7688): 152 passed.
* `card.js` is 394 lines, under the 400 limit.
* Local walk-through on the development database:
  * language model off (rule 4): a solution's Write page; typing beside the open card shows no line; a card with only a link (`gad_source`, `gclid` on it) and no statement previewed and posted as "… submits evidence Aei.org/commentary/data-centers-make-easy-targets, which supports solution of Decisions should be made by consensus.", the link once, and went back to the solution page;
  * language model set (an unreachable test address): typing beside the open card shows the line, Post stays on; "Read my statement" replaced it with "The language model is not answering right now…", and it did not come back;
  * no console errors.

## Open

* **Eston's go to merge.** Merging deploys John's live site. After it, run `scripts.smoke` and open a live solution's Write page, reading only.
* John's AEI evidence keeps its long name in the live record until someone renames or edits it.
