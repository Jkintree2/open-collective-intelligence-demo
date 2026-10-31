# Handoff, 31 October 2026: writing from solution and evidence pages, after John tried them

John tried the live solution and evidence pages (GitHub issue 55, live since 31 October as `da2be8b`) and sent four emails the same afternoon. Three of his reports are fixed here, on the branch `item-page-write-fixes`, under the 28 October terms (fixes to what was built are free through November). Not merged.

## What John saw, and why

Checked against `main` (`8f2928f`) and his live records, read signed in without clicking anything.

1. **"The form only showed one of the related issues."** The card started from a solution's first issue only (`about_solution` gave one `issue_key`).
2. **His opposition reasons "not shown".** Both opposition posts were listed under "Posts about this solution" all along, below the Ask box. Showing reasons beside the count, and a counter solution tied to what it opposes, are Phase 4 ("objections with reasons", SOW 0.3).
3. **Evidence attached to Climate change instead of the solution or the evidence.** A row from "+ add evidence" started as "supports" the first issue on the card, wherever the writer came from. That is how "People in the United States are too individualistic", "Costs of shared EVs will be much less" and an anonymous "BYD Seagull is not sold in the United States" landed on Climate change.
4. **"The display should go back to the page."** After Post the Write page stayed where it was.
5. **One piece of evidence refuting one thing and supporting another, in one post.** Not possible today: `resolve_payload` keeps a piece of evidence once per post (`if key in seen: continue`). Not in this branch.
6. **His counter proposal (majority votes, Robert's Rules) was never recorded.** Not the reading: case 23 returns both proposals in 3 of 3 runs on the unchanged prompt (05_extraction.md). Most likely the statement was never read. On a solution's Write page the card opens on arrival, and its Post sends the statement as written with only the card's rows. **Not changed here: Eston to decide** (for example, a line on the card when the statement has not been read, which is new copy for John, or reading it before posting).

## Built

* **Every issue of the solution on the card** (`data-issue-keys`, `card.js` `solutionIssues`), added after the reading's own issues. On issue and evidence pages nothing changes.
* **A stance alone still claims none of the solution's issues** (`payload._positions_only`): a stance-only row now holds every issue the solution is linked to, not only the one its row names. Without this, a plain "I oppose" from the consensus page would claim Methods of collective decision making and drop Need for world government.
* **"+ add evidence" starts about the page's solution or evidence** (`card.handEvidence`, `data-solution` / `data-evidence`), and as "refutes" against a solution the card opposes.
* **Back to the page after Post** (`data-return`, in `card.post`).
* **Case 23** and the `consensus` context in `scripts/cards.py`.
* Docs: 04_interface.md (the three behaviours, no new copy), 05_extraction.md (case 23).

## Verified

* `pytest -m "not live"`: 1208 passed (1206 on main, plus the two-issue write page and the stance-only case).
* `node --test tests/*.cjs`: 128 passed (120 on main, plus eight in `test_card_item_pages.cjs`).
* `pytest -m live` on `oci-neo4j-test` (7688): 152 passed.
* `card.js` is 389 lines, under the 400 limit.
* Local walk-through on the development database, `LLM_API_KEY` unset (rule 4), passphrase site:
  * a solution proposed for two issues: the card opened with both; Oppose plus a hand-added evidence row started "refutes" about the solution; the preview read "opposes" and "refutes solution of"; Post went back to the solution page, which lists the evidence under "Refuted by";
  * from that evidence's page: the hand-added row started about the evidence; Post went back to the evidence page, which lists the new evidence under "Refuted by".
  * Not walked: the reading path with the model on (covered by the page tests), a signed-in account, and a phone width (no layout change).

## Open

* **Eston's go to merge.** Merging deploys John's live site. After it, run `scripts.smoke` and open a live solution page and its Write page, reading only.
* **Item 6 above**: Eston's call on the unread statement.
* **John's existing records stay as they are.** The three evidence items above still point at Climate change until someone edits those posts. Two of the four test posts are listed as Anonymous.
* **Not in this branch:** reasons for opposition beside the count, counter solutions tied to what they oppose and asking for a reason on Oppose (Phase 4 in SOW 0.3, left out of issue 55 as agreed); one evidence with two targets in one post (item 5).
* Carried over: the card's lists hold the newest 50 issues and 200 solutions and pieces of evidence, so an item older than that is not offered as the default. A position chosen above the box before the page has loaded its lists opens the card with an empty issue row (seen in a scripted walk-through, also on `main`).
