# PLAN_v2.md: execution plan, revised after review

Supersedes `PLAN.md`. Every finding in `REVIEW.md` is fixed here, accepted with a reason, or moved to the after list; the disposition table at the end covers all 53 plus the interesting-versus-needed table. `03_schema.md`, `04_interface.md`, `05_extraction.md`, `06_seed.md`, `08_architecture.md` and `CLAUDE.md` carry a dated note at the top listing what changed in them.

## Changelog (what changed and which finding drove it)

| Change | Finding |
|---|---|
| Honest budget: 25.5 hours, not 24. Session 2 to 3.0 h plus 0.75 h of seed authoring outside any session, Session 3 to 5.0 h, Session 4 trimmed to SOW items plus admin; live extraction test suite, extraction log, live-test document, pagination and the "posting as" header cut; admin login is HTTP basic auth; seed JSON authored outside a session | C1, table |
| Calendar: friends get the link Wednesday 16 September, second invoice the same day; GitHub username from John by Friday 11; Render account by Tuesday 22; repository transfer at the end of Session 6 on Wednesday 23; call Thursday 24; Friday 25 is the only buffer and is stated as such | C1, C2, M21 |
| John's Aura instance is never reset without an emptiness check; `--reset` refuses a database holding non-seed nodes unless `--force`; Eston's temporary Free instance is the development database for the whole project; production is seeded once from an inline-variable shell; `TEST_ALLOW_LIVE` and the live `test_graph.py` are gone | C3, C9, M19, m22 |
| Startup connectivity check is non-fatal; a paused database renders a client-facing "the record is asleep" page with the Aura console link; `scripts/restore.py` reads the admin export back | C4, M14 |
| Drafted seed statements load under "Seed" and the two counter-arguments under a name John chooses (default "Counterpoint"); only John's verbatim sentences (S1, S2, S3, S9) load under his name; his approval flips `author` per statement | C5, M10 |
| Case 1 expects one approve ("Treat drug use as medical issue" is an imperative) and none on "Decriminalize drug sales"; the APPROVE rule is put to John this Saturday as a question with a default, so Friday's email is not the first he hears of it | C6 |
| Top-level issues rank on inclusive counts (people distinct across the family, claims and evidence summed) and show both numbers; a row of the five most discussed issue chips sits above the text box from Session 2 (links) and pre-fills the card from Session 3; "Write about this issue" moves to Session 3 | C7, table |
| Keep-alive: the GitHub cron is used only during the build in Eston's repository and is deleted before transfer; on the call John creates an UptimeRobot monitor with Google sign-in (five-minute interval, emails him when `/health` fails); whether `RETURN 1` resets Aura's idle timer is verified on the temporary instance over the weekend of 12 to 14 September | C8 |
| Datalists ship in the first pass of the card and are checked on an iPhone inside Session 3; the fallback is a substring suggestion list, not "no autocomplete" | M1 |
| A parent that is itself a sub-issue is replaced by its parent; a child that already has a parent keeps it; candidate list marks sub-issues as ineligible parents | M2, M3 |
| Deleting a post also deletes non-seed nodes it left with no relationships; MERGEd edge types are not deleted with a post; names have newlines stripped; the candidate block is the top 50 issues by claims plus the last 20 created | M4, M9 |
| Token bucket is 6 a minute and 300 a day; 401, 402 and 403 from the provider are stored as "last model error" and shown on the admin page; the guide's "reading stopped" entry leads with the DeepSeek balance | M5, M15 |
| The `thinking` field is sent only when the base URL contains `deepseek`; Session 3 begins with one raw call to the configured provider before any other code | M6 |
| Anonymous posts store `display_name` null and never set the name cookie; "people" is explained as "browsers" for anonymous posts in the tester email and the guide | M7 |
| Impersonation accepted for 0.1 and made visible in the Session 4 email and the guide | M8 |
| Seed email corrected (four verbatim statements; no proposal appears under two parts); S9 cites nothing on purpose; S8 softened; link check uses a browser user agent and follows redirects | M11, M12, m17 |
| Eston's Render workspace checked for other free services before Session 1; the redirect, if needed, is a static site; the service-name reclaim trick is verified the day before the call so the URL can survive handoff | M13, M22 |
| Handoff scrub covers `onrender.com`, `groq`, `ollama`, `databases.neo4j.io` and Eston's GitHub handle; commits use the GitHub noreply address; `SECRET_KEY` and `ADMIN_TOKEN` are `generateValue: true` in the blueprint so Eston never knows John's values and nothing is read aloud; the call is not recorded; the password manager entry is deleted at the end | M14 |
| `SITE_NAME` and `SITE_SENTENCE` are environment variables from Session 1 so John changes the sentence on Render's Environment tab, like the passphrase | M15 |
| Guide topics extended to the ten month-two cases in M15 | M15 |
| Gate copy names DeepSeek as an outside company that reads the text | M16 |
| Evidence links get `rel="noopener noreferrer"`; on a `found: false` card the Post button is disabled until a field is typed or "post it as a plain statement anyway" is clicked | M17 |
| Planning docs 03, 04, 05, 06, 07 and this plan are copied into the repository under `docs/planning/`; CLAUDE.md paths fixed; sessions are told their number in the first message | M18 |
| Candidate cache removed | M20 |
| Minor fixes: Issues link hidden until Session 2; error copy; request id kept in logs only; `last_activity` over every edge; parent pages show children's posts; casing and punctuation rules; keys shorter than two characters rejected; articles stripped only before a space; sort label "Most people"; a cancel link during reading; 4,000 character limit; case 8 checklist note; iOS recognition restart; `scripts/__init__.py`; bucket on `/enter`; spam folder note | m1 to m17, m20 |
| Non-English input stays refused; noted on the after list | m12 |
| Name cookie kept (server-side prefill is needed for the no-JavaScript form), but never set on an anonymous post | m21, M7 |
| **Accounts (Eston's decision, Saturday evening, overrides the rows above where they differ):** everything is built in Eston's accounts and moved at handoff. GitHub, Render, a Free Aura instance as production, and a DeepSeek key are all Eston's for the build; the development database is a local Neo4j 5 in Docker; the record migrates to a Free instance in John's Aura account by export and restore on the call, so `scripts/restore.py` is required, not a cut; the transfer target is `Jkintree2`; John's only pre-handoff tasks are a Render account and a DeepSeek account; the site is "Open Collective Intelligence"; `/health` runs a real read so no idle-timer experiment is needed; John's 21 August paragraph is seed S14 | Eston, 5 Sep |

## Budget, honest

| Unit | Hours | Cumulative |
|---|---|---|
| Planning (spent) | 2.0 | 2.0 |
| Seed JSON authoring, Eston, Sunday 6 September (data entry, not a session) | 0.75 | 2.75 |
| Session 1: walking skeleton | 3.0 | 5.75 |
| Session 2: schema, seed, Issues view | 3.0 | 8.75 |
| Session 3: extraction, card, merge | 5.0 | 13.75 |
| Session 4: dictation, states, admin, mobile | 3.0 | 16.75 |
| Session 5: revision round | 2.0 | 18.75 |
| Session 6: guide, README, scrub, transfer | 2.5 | 21.25 |
| Walkthrough call including the blueprint and UptimeRobot | 1.25 | 22.5 |
| Email and admin between sessions | 3.0 | 25.5 |

That is 1.5 hours over the 24 in the SOW at the honest rate, and it assumes the cuts below hold. Fixed fee means the overrun is Eston's. There is no separate contingency line because the review showed the old one was fiction; the buffer is Friday 25 and the cuts list. If a session overruns by more than an hour, the cut order is: the "Write about this issue" pre-fill (leave the chips as links), then iOS dictation (leave desktop), then the last-model-error line on the admin page. The export and restore scripts are never cut; they are how the record moves into John's account. Nothing from the SOW sentence list is ever cut; those are the datalist autocomplete, dictation on Chrome and Edge, the anonymous toggle, the three sorts, the counts, the seed, the guide and the call.

## Calendar

| Date | What |
|---|---|
| Sat 5 Sep | This plan. Email John: seed text for approval, three questions (below), the two accounts he needs before the call. |
| Sun 6 Sep | Eston: check the Render workspace for other free services; create the production Aura Free instance `oci` in his own account; start the local Docker database; open the DeepSeek account; author `seed/seed.json` from `06_seed.md`. |
| Mon 7 Sep | Session 1. Evening: link to John. |
| Wed 9 Sep | Session 2. Short note: Issues page is up. |
| Fri 11 Sep | Session 3, first half. |
| Sat 12 Sep | Session 3, second half. Email: the smart part is live. |
| Tue 15 Sep | Session 4. Evening: email "ready for two or three friends" and the second invoice. Reset production to seed before the email. |
| Wed 16 to Sun 20 Sep | Friends test. Eston reads logs daily, pushes nothing except a revert. Feedback by Sunday 20. |
| Mon 21 Sep | Session 5. Email: statuses, after list, call time, and the two accounts John needs before the call. |
| Tue 22 Sep | John confirms by email that his Render account (Google sign-in) and his DeepSeek account (5 USD balance, one key) exist. Eston verifies the service-name reclaim trick with a throwaway service, and rehearses export and restore from production into the local database. |
| Wed 23 Sep | Session 6: guide, README, scrub, cron deleted, repository transfer to `Jkintree2` initiated at the end. John accepts from the email (check spam). |
| Thu 24 Sep | The call, 17:00 Berlin / 10:00 St. Louis: John creates a Free instance in his Aura account; Eston restores the exported record into it; blueprint in John's Render with his Aura values and his DeepSeek key; UptimeRobot; verification; guide walkthrough. If the transfer was not accepted, re-initiate on the call and accept live. |
| Fri 25 Sep | Buffer. If either account did not exist on Thursday, this is the day. |

## Before Session 1 (Saturday and Sunday, Eston, about 1.5 hours including the seed JSON)

Everything is created in Eston's accounts now and moved into John's at handoff. John has sent no credentials and is not asked for any until the call.

1. Send the Saturday email (draft below): the seed text, three questions with defaults, and the two accounts John needs before the call.
2. Render: open the dashboard, list every free web service in the workspace, suspend any other one until 25 September (M13). Render's 750 free hours are 744 in a 31-day month for one service; a second one takes the demo down mid-week.
3. Aura: create a Free instance in Eston's own account, named `oci`. This is **production** for the whole build and test week (Aura Free allows one instance per account, so it cannot also be the development database). Download the credentials file and keep the URI and password in the password manager entry, which is deleted on 24 September.
4. Development database: `docker run -d --name oci-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/localpass neo4j:5`. If Docker is not on the Mac, install Docker Desktop before Session 2; Session 1 may use the Aura instance directly because nothing real is in it yet.
5. DeepSeek: open an account in Eston's name at platform.deepseek.com, top up 5 USD, create one key, keep it in the same password manager entry. The whole build and the test week then run on the model John will use, and his own key replaces it on the call. Groq or Ollama cloud remain the fallback by the three `LLM_*` variables if DeepSeek signup fails.
6. Author `seed/seed.json` from `06_seed.md` (technical notes): S1, S2, S3, S9, S14 as "John Kintree"; S4, S5, S7, S10, S11, S12, S13 as "Seed"; S6, S8 as "Counterpoint". Check every link with `curl -sL -A "Mozilla/5.0" -o /dev/null -w "%{http_code}"`; open in a browser any that is not 200.
7. Generate a temporary passphrase (three plain words). Generate Eston's own `SECRET_KEY` and `ADMIN_TOKEN` for the build; the blueprint generates John's.
8. Set `git config user.email` to the GitHub noreply address before the first commit (M14).
9. Confirm `gh auth status` is green and Docker runs (`docker ps`).

---

## Session 1: walking skeleton on a public URL (3.0 h)

**Goal.** A public URL behind the passphrase where a tester writes a statement and sees it in a feed that other testers also see, stored in Neo4j.

**Read.** `CLAUDE.md`, `04_interface.md` (screens 1 and 2 without the card), `08_architecture.md` (decisions 1, 2, 3, 6, 7, 8, 9, 11, 12, 16).

**Exists before.** The planning docs. Eston's GitHub and Render accounts, the workspace checked. The production Aura Free instance `oci` in Eston's account, and a local Neo4j 5 in Docker for development (or, for this session only, the Aura instance itself). The temporary passphrase and Eston's `SECRET_KEY` and `ADMIN_TOKEN`. The Session 1 prompt in `SESSION_1_PROMPT.md`.

**Tasks, in order.**

1. Repository `open-collective-intelligence-demo`, public, with: `CLAUDE.md`, `LICENSE` (MIT, John Kintree), `README.md` (stub), `.gitignore`, `requirements.txt` (pinned), `.env.example`, `render.yaml` (one web service; `buildCommand: pip install -r requirements.txt`; `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`; `envVars`: secrets `sync: false`, `SECRET_KEY` and `ADMIN_TOKEN` `generateValue: true`, `PYTHON_VERSION` 3.12, `SITE_NAME` and `SITE_SENTENCE` with defaults), `scripts/__init__.py`, `docs/planning/` containing copies of 03, 04, 05, 06, 07 and this plan.
2. `app/config.py`: read the environment; refuse to start without `DEMO_PASSPHRASE`, `SECRET_KEY`, `ADMIN_TOKEN`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`. `SITE_NAME` default "Open Collective Intelligence", `SITE_SENTENCE` default the draft sentence.
3. `app/text.py`: `normalise()`, `make_key()` (NFKC, lowercase, non-alphanumerics to single spaces, trim, leading the/a/an stripped only when followed by a space, result shorter than two characters rejected), `clean_name()` (newlines to spaces, trim, cap 120, upper-case the first character only when it is lower-case and the second is not upper-case, strip trailing `.,;:!?`). `tests/test_text.py`, ten cases including "The need for world government" versus "Need for world government", "Security council veto." versus "Security Council veto", "A/B testing", "iPhone", "!!!".
4. `app/graph.py`: driver in the lifespan with a non-fatal connectivity check (log a warning and continue); `ensure_constraints()`; `create_raw_post()`; `list_posts(limit=60)`; `health()`. Every read function catches `ServiceUnavailable` and raises `RecordAsleep`, which the error handler renders as the client-facing "asleep" page (C4).
5. `app/auth.py` and `templates/enter.html`: the gate as decision 6; the wrong-passphrase sleep counts toward the same in-memory bucket as `/api/extract` (m16). `tests/test_auth.py`: round trip; token signed under an old passphrase rejected.
6. `app/main.py`: lifespan, request-id middleware (id in the log line only, no header), the error page ("Something went wrong. Please try again in a minute."), the "asleep" page, `GET /enter`, `POST /enter`, `GET /`, `POST /posts` (HTML form, raw post, redirect), `GET /health`.
7. Templates and CSS: header with the site name from `SITE_NAME` and one link, "Write" (the "Issues" link is added in Session 2, m1); the sentence from `SITE_SENTENCE`; name row with the anonymous checkbox; text box with a 4,000 character limit; "Post"; the feed (name or Anonymous, relative time, statement in serif). Anonymous posts store `display_name` null and do not set the name cookie. Timebox CSS to 30 minutes.
8. `.github/workflows/keepalive.yml` (build-time only; deleted in Session 6): every 10 minutes and on dispatch, `curl -fsS "${{ vars.APP_URL }}/health"`.
9. Render: web service from the repo, free instance, variables set (Eston's values), deploy. `APP_URL` set in the repository's Actions variables. Run the workflow once by hand.
10. Verify on a laptop and a phone; check the Aura console for the nodes.

**Done when.**

- [ ] The live URL shows the passphrase page; a wrong passphrase shows the message after about a second; the right one shows the write page and survives a browser restart.
- [ ] A named post appears at the top of the feed with the name and "just now"; an anonymous post shows "Anonymous", and the Aura console shows `display_name` null on it.
- [ ] Changing `SITE_SENTENCE` on Render's Environment tab changes the sentence after the redeploy.
- [ ] `/health` returns `{"ok": true}`; the Actions run is green.
- [ ] With `NEO4J_URI` pointed at a wrong host locally (a Free instance cannot be paused by hand, so this stands in for a paused database): the app starts, and `/` shows the "asleep" page, not a traceback.
- [ ] Without `DEMO_PASSPHRASE` locally, `uvicorn` refuses to start with a readable message.
- [ ] At 360 px there is no horizontal scroll and every button is at least 44 px tall.
- [ ] `pytest` green, at least 10 tests. Deploy green. Commits small, author email is the noreply address.

**Committed and deployed.** Tag `v0.1.0-skeleton`.

**Email to John.** The link, the passphrase, the rough warning, what to try, the reminder of anything outstanding from Saturday. Draft below.

**Risks.**

* Render first-deploy friction: `render.yaml` is the source of truth.
* The `Secure` cookie flag on local HTTP: `APP_ENV=local` turns it off.
* CSS time sink: the 30-minute timebox.
* Temptation to start the card: no.

---

## Session 2: schema, seed, Issues view (3.0 h plus the 0.75 h of seed authoring already done)

**Goal.** The full schema is live with the seed loaded in John's Aura, and the Issues page ranks issues honestly with three sorts and opens into an issue detail page.

**Read.** `CLAUDE.md`, `03_schema.md`, `06_seed.md` (technical notes), `04_interface.md` (screens 2, 3, 4), `08_architecture.md` (decisions 10, 16).

**Exists before.** Session 1 live against production (`oci`, Eston's Aura account). The local Docker database running. `seed/seed.json` authored and link-checked.

**Tasks, in order.**

1. `app/extract.py`: the pydantic models only (`IssueItem`, `SolutionItem`, `EvidenceItem`, `CardPayload`) with the field rules in `05_extraction.md`. `tests/test_payload.py`: bad URL to null, unknown `for_issue` to the first issue, lists capped, names cleaned, a parent that is a sub-issue replaced by its parent (needs the candidate list passed in).
2. `app/graph.py`: `merge_post(...)` running the write path from `03_schema.md` in one `execute_write`, including the two `PART_OF` guards (M2, M3). Refactor `create_raw_post` onto it.
3. `scripts/seed.py`: `--counts`; `--reset --yes` refuses when the database contains any node without `seed = true` unless `--force` (C3). Seeds the issues block, then posts with the file's `created_at`.
4. `app/graph.py`: `list_issues(sort)` (Q1), `group_issues(rows)` with inclusive counts for top-level rows (C7), `top_issues(5)` for the chips row, `issue_header`, `issue_claimants`, `issue_solutions`, `issue_evidence`, `issue_posts` (own plus children's, m5), `post_structure`.
5. `templates/issues.html`, `templates/issue.html` per screens 3 and 4; sort labels "Most people", "Most recent", "Most evidence"; the "Issues" link appears in the header.
6. Write page: the chips row above the text box ("People are writing about:" plus the five most discussed issues as links to their pages; pre-fill comes in Session 3). Feed: chips per post, the seed tag.
7. Unit test for `group_issues` on a hand-made row list: the parent ranks on inclusive counts; a sub-issue with two parents cannot occur, so no test.
8. Seed the local database with `--reset --yes` and verify counts. Then seed production from a one-off shell with the variables typed inline (`NEO4J_URI=... NEO4J_USERNAME=neo4j NEO4J_PASSWORD=... python -m scripts.seed --reset --yes`; the guard passes because production holds only Session 1's throwaway posts, which have no `seed` property, so `--force` is needed once and never again). Local `.env` stays on the Docker database for the rest of the project (C9).

**Done when.**

- [ ] `/issues` under "Most people" shows "Need for world government" first with "3 people · 14 claims in total · 1 claim on the issue itself" and the five sub-issues indented, and nothing else.
- [ ] Sub-issue order under "Most people": Enforcement of international law (2 people, 3 claims), Global climate coordination (2, 3), Security Council veto (2, 2), then Need for supreme law above nations (1, 3) and Democratic legitimacy of global institutions (1, 2). "Most evidence": Security Council veto first (4). "Most recent" follows the file's dates.
- [ ] `/issues/<key of Security Council veto>` shows: claimed by 2 people (2 claims), names Seed and Counterpoint; one solution with "proposed by 1 · approved by 1 · opposed by 0"; two "Supported by" and two "Refuted by" items with working links; two posts.
- [ ] `python -m scripts.seed --counts` prints the numbers in `06_seed.md`; running the seed twice changes nothing; `--reset --yes` against a database with one hand-made non-seed node refuses without `--force`.
- [ ] The chips row shows five issues and each links to its page.
- [ ] `pytest` green. Deploy green. Production holds the seed and nothing else; the local database matches.

**Committed and deployed.** Tag `v0.1.1-issues`.

**Email to John.** Two or three sentences: the Issues page is up; what "Most people" means; the drafted statements are under "Seed" and the counter-arguments under "Counterpoint" until he approves them, at which point the ones he accepts move under his name.

**Risks.**

* Inclusive counts and grouping in Python are where the hour goes. One unit test on a fixed row list, written first.
* The counts checklist depends on the JSON matching the doc exactly; the numbers are the test.

---

## Session 3: extraction, the card, merge with resolution (5.0 h, two sittings)

**Goal.** A tester types a statement, the model fills in the card, the tester corrects it, posts it, and the graph grows with existing nodes reused and sub-issues under existing parents.

**Read.** `CLAUDE.md`, `05_extraction.md`, `04_interface.md` (screen 2, all states), `03_schema.md` (write path, Q8), `08_architecture.md` (decisions 4, 5, 14).

**Exists before.** Session 2 live. Eston's DeepSeek key in `.env` and on Render (opened before Session 1; Groq or Ollama cloud only if DeepSeek signup failed, in which case the prompt is re-checked on DeepSeek at handoff).

**Sitting one (2.5 h).**

1. One raw `httpx` call to the configured provider from a scratch script, printed to the terminal, before any other code: confirm the model id is served, `thinking: disabled` is accepted (sent only when the base URL contains `deepseek`), `response_format: json_object` returns JSON in `content`, `temperature` is accepted, latency at this hour (M6). Record the five answers in the commit message of the next step.
2. `app/extract.py`: `build_messages()`, `call_model()` (connect 5 s, read 25 s, one retry, JSON safety net, distinct statuses for 401, 402, 403 stored in `last_model_error`), `extract()` returning `Extraction | None`.
3. `app/graph.py`: `candidates()` (Q8, top 50 issues by claims plus last 20 created, all solutions and evidence up to 200, no cache).
4. `app/main.py`: `POST /api/extract` (length 4,000, bucket 6 a minute and 300 a day, logging), `GET /api/candidates`, `POST /api/posts` (validation, parent repair, `display_name` null when anonymous, `merge_post`, cookies), `GET /feed`.
5. `app/text.py`: `sentences()`; `tests/test_text.py` extended with cases 1 and 4 as exact strings (case 1 now includes "John Kintree approves Treat drug use as medical issue").

**Sitting two (2.5 h).**

6. `static/app.js`: the compose flow with datalists in the first pass (M1): "Read my statement" → reading state with the 8-second line, the "Stop and fill it in myself" link (m10) and the 25-second abandon → card: issue rows (input plus datalist, "part of" select of top-level issues, new/existing badge), solution rows (input plus datalist, for-issue select fed from issue rows, three radios), evidence rows (input, link, supports/refutes, about select), live sentences, Post and Discard, footnote. On `found: false`, Post is disabled until a field is typed or "post it as a plain statement anyway" is clicked (M17). Post → `/api/posts` → clear, "Added to the record", re-fetch `/feed`. The chips row and the "Write about this issue" button (added to the issue page now) open `/` with `?issue=<key>` and pre-fill the issue row and its parent (C7). The Session 1 HTML form keeps working without JavaScript.
7. `scripts/cards.py`: prints the card the model produces for each of the eleven cases in `tests/extraction_cases.json` against the live provider, for Eston to read; no assertions (table). `tests/test_payload.py` extended with hand-written fixture responses for cases 1, 4, 5, 6A, 7.
8. Run `scripts/cards.py`; tune the prompt for at most 45 minutes until at least nine cases read correctly; note the pass list in the commit message.
9. Deploy. Re-run cases 1, 5 and 8 on the live site by hand. Open the card on an iPhone: if Safari's datalist does not offer "Security Council veto" when typing "veto", replace the datalist with a ten-line substring suggestion list under the input.

**Done when.**

- [ ] John's drug sentence produces a card with one new issue, "Decriminalize drug sales" with "no position", "Treat drug use as medical issue" with "I approve this", no evidence, and the six sentences of case 1 word for word. Post → feed chips → `/issues` shows a new top-level issue.
- [ ] Case 8 under a name other than John Kintree (m13) produces the existing sub-issue with badge "existing" and "part of" preselected, the existing solution, "I approve this" preselected; after Post the detail page shows "approved by 2".
- [ ] Case 5 opens the empty card with the "could not find" line and Post disabled; typing an issue name enables it.
- [ ] With `LLM_API_KEY` unset locally, "Read my statement" opens the empty card with the "not answering" line within a second; a hand-filled card posts; picking an existing name shows "existing".
- [ ] A 4,500-character paste is refused in the browser and by the server (413).
- [ ] The seventh `curl` to `/api/extract` inside a minute returns 429 with the friendly message.
- [ ] On an iPhone, typing "veto" in the issue field offers "Security Council veto".
- [ ] The chips row pre-fills the card; "Write about this issue" on a sub-issue page pre-fills the issue and its parent.
- [ ] Render logs show `extract` and `merge` lines with latency; `scripts/cards.py` output for at least nine of eleven cases reads correctly.
- [ ] `pytest` green. Deploy green.

**Committed and deployed.** Tag `v0.1.2-extraction`.

**Email to John.** "The smart part is live." What to try; the approve rule as he decided it on Saturday, one sentence; ask for anything it got wrong with the text typed.

**Risks.**

* Still the session most likely to overrun; two sittings are the mitigation, and the datalist is not deferrable.
* Provider assumptions: task 1 exists to surface them in the first ten minutes.
* Prompt tuning: 45 minutes, then stop.
* DeepSeek signup fails for Eston: build on Groq by the three variables, and re-run `scripts/cards.py` on DeepSeek with John's key on the call before declaring the handoff done.

---

## Session 4: dictation, states, admin, mobile (3.0 h)

**Goal.** Complete for a stranger on a phone: dictation, every state, the admin page John operates, a real-phone pass.

**Read.** `CLAUDE.md`, `04_interface.md` (all), `08_architecture.md` (decisions 10, 11, 14).

**Exists before.** Session 3 live. Leftovers listed in the first message.

**Tasks, in order.**

1. Leftovers.
2. Dictation: feature-detected button; continuous with interim results; "Listening… speak now"; restart on `end` while active (m14); stop on second press. Chrome desktop and iPhone Safari; 30 minutes, then note what works in the guide and move on.
3. States: empty feed, empty issues, error page, asleep page, 429, English-only, too long, "not answering", "could not find", each with the exact copy.
4. Admin: HTTP basic auth with `ADMIN_TOKEN` as the password (table); counts; last model error line (M5); "Reload seed"; "Reset to seed" with typed `RESET`; "Download a copy" (`/admin/export.json`); last fifty posts with delete (Q11 with orphan cleanup, MERGEd types kept).
5. `scripts/restore.py export.json`: reads the export back with MERGE on keys and ids, into an empty database (refuses a non-empty one). Required: this is how the record moves from Eston's Aura account into John's on the call. Rehearse it once here: export production, restore into the local Docker database after a reset, compare `--counts`.
6. `rel="noopener noreferrer"` on evidence links (M17).
7. Real-phone pass at 360 px, keyboard open. Fix what breaks, nothing else.
8. Run the five test statements on the live site by hand (John's drug sentence, his supreme law paragraph, the Festival sentence, the seawall statement, case 7); tick them in the session, no document.
9. "Reset to seed" on production so friends start clean; tell John in the email that his week's test posts were cleared, or skip if he asks to keep them.

**Done when.**

- [ ] Dictate produces text on Chrome desktop; on iPhone it either works or the guide says which browser to use.
- [ ] Every state in task 3 triggers and shows the exact copy.
- [ ] `/admin` prompts for a password; with the token it shows counts and the model error line; "Reload seed" is idempotent; "Reset to seed" restores the counts; the export opens as JSON; delete removes a post, its edges and any node it alone created.
- [ ] `scripts/restore.py` on the reset local database reproduces production's `--counts` from an export.
- [ ] The five statements produce sensible cards.
- [ ] `pytest` green. Deploy green. Production is the seed plus nothing.

**Committed and deployed.** Tag `v0.1.3-testable`.

**Email to John, Tuesday 15 September evening.** "Ready for two or three friends." Link and passphrase; what a friend should do in five minutes; three honest notes: everything is public inside the test and an outside company, DeepSeek, reads what is typed; anyone with the passphrase can post under any name, including his, and the admin page (password in the email, in his own words: the "back room") deletes a post; "people" counts browsers for anonymous posts. Feedback by Sunday 20 with the text typed when something looked wrong. The after list. The second invoice attached, with the SOW sentence it satisfies.

**Risks.**

* Speech on iOS: 30 minutes, then the guide.
* Admin delete semantics: documented.
* Polish is unbounded: the task list is the boundary.

---

## Session 5: revision round (2.0 h)

**Goal.** John's feedback, consolidated by Eston into a numbered list, applied where in scope and listed where not.

**Read.** `CLAUDE.md`, `07_scope_guard.md`, the numbered list in the first message.

**Exists before.** A week of use. Eston's numbered list (20 minutes to write, from all emails).

**Tasks.**

1. Work on a branch. For each bug or wording item: fix, test locally against the Docker database, merge to `main` only at the end of the session with the checklist green (C9). For each feature item: after list with the date and a line.
2. If John chose the other APPROVE rule on Saturday or changed his mind: the prompt paragraph, the radio default, re-run cases 1, 7, 8 with `scripts/cards.py`.
3. If the list is short and the session is under 1.5 hours: a second export-and-restore rehearsal against the local database with the week's real posts, so the call on Thursday holds no surprises.
4. Re-run the five statements.

**Done when.**

- [ ] Every item has a status.
- [ ] One merge to `main`, deploy green, the five statements still produce sensible cards.

**Committed and deployed.** Tag `v0.1.4-revised`.

**Email to John.** Statuses, after list, the call time (Thursday 24, 17:00 Berlin), and the three things he must do before it: create a Render account with Google sign-in and a DeepSeek account with a 5 USD balance and one key, both by Tuesday 22 (reply "done"); have his Neo4j Aura login ready for the call; and watch his inbox and spam folder on Wednesday 23 for the GitHub transfer email (m20).

**Risks.**

* Late or absent feedback: the Sunday deadline; otherwise a self-review against `04_interface.md` and the hour moves to Session 6.

---

## Session 6: guide, README, scrub, transfer (2.5 h) and the call (1.25 h)

**Goal.** Everything runs in John's accounts, he has a plain guide, and nothing depends on Eston.

**Read.** `CLAUDE.md`, `08_architecture.md` (decisions 8, 9, 12), `07_scope_guard.md`.

**Exists before.** Session 5 live. John's GitHub account is `Jkintree2` (the owner of his project repository). His Render and DeepSeek accounts confirmed by Tuesday 22. The service-name reclaim trick verified on Tuesday 22 with a throwaway service. Export and restore rehearsed.

**Tasks, in order (Wednesday 23).**

1. `docs/operators-guide.md`, client-facing, covering: what the site is; giving someone the passphrase; changing the passphrase and the sentence at the top (Render, Environment, one variable each, save; everyone re-enters after a passphrase change); the back room: reload seed, reset to seed, download a copy, delete a post (what delete removes and what stays); where the back-room password is (Render, Environment, `ADMIN_TOKEN`, reveal); slow first visit; the "asleep" page and the Aura console Play button, with the rule never to leave it paused 30 days; the two emails that need action (Aura pause or deletion warning, UptimeRobot down alert) and the sender addresses, and the emails that need nothing; reading stopped: DeepSeek balance first, then the model error line; before widening the circle (closed test, DeepSeek reads the text, anyone can post as anyone, the address is an onrender.com one); adding a seed statement means posting it on the site under his name; what costs money (nothing by default; Render Starter 7 USD a month removes the slow first visit; DeepSeek pennies; never Aura Professional for this); recovering a deleted database (new Free instance, three variables on Render, reset to seed, then the last downloaded copy restored by whoever helps him); who to ask for what is on the after list. About 1.25 hours.
2. `README.md` for the next developer. No URLs that change.
3. Scrub: `grep -ri "eston\|mckeague\|creative consulting\|onrender.com\|groq\|ollama\|databases.neo4j.io\|<eston's github handle>" .` returns nothing outside `.git`; LICENSE names John; `render.yaml` has no ids. Delete `.github/workflows/keepalive.yml` (C8). Commit.
4. Transfer the repository to `Jkintree2`. Email him: look for the github.com email, also in spam, press Accept.

**On the call (Thursday 24).**

5. If the transfer is not accepted: re-initiate, John accepts live.
6. The database: John signs in to console.neo4j.io, creates a Free instance, downloads the credentials file. Eston downloads the current record from the admin page ("Download a copy"), then runs `scripts/restore.py export.json` with John's URI and password typed inline (John reads them out or pastes them into the call chat; they are his). `scripts/seed.py --counts` against John's instance matches the export.
7. The site: rename Eston's Render service to `...-old` (verified on Tuesday to free the subdomain). In John's Render: New Blueprint, the transferred repository, fill `NEO4J_*` (John's new instance), `DEMO_PASSPHRASE` (John chooses), `LLM_API_KEY` (John pastes his own DeepSeek key), service name set to the original so the URL survives (M22); `SECRET_KEY` and `ADMIN_TOKEN` are generated by Render. Deploy.
8. If the reclaim did not work on Tuesday: Eston's old service becomes a Render static site that redirects for 30 days, and John gets a one-line note for friends.
9. UptimeRobot in John's name: sign in with Google, one HTTP monitor on `/health`, five minutes, email alerts to him (C8).
10. Verify: the URL loads; the whole record is there, including the friends' posts from the test week; John posts; the Issues page updates; the card reads a statement on his DeepSeek key; John opens the back room with the token from Render's Environment tab.
11. Ten minutes on the guide, five on the after list. Not recorded.
12. Eston, after the call: delete the old Render service (or leave the static redirect), delete Eston's Aura instance `oci`, delete Eston's DeepSeek key, delete `.env` and the password manager entry, stop the Docker database.

**Done when.**

- [ ] The URL (same as before, or the new one with the redirect in place) serves the demo from John's Render account with the seed and John's post.
- [ ] `github.com/<john>/open-collective-intelligence-demo` exists; an edit to README in John's web UI deploys green.
- [ ] UptimeRobot shows the monitor up and emails John.
- [ ] John's Aura instance holds the record and `--counts` matches the export taken on the call.
- [ ] Eston has no environment file, no password manager entry, no DeepSeek key for the project, no running service except the redirect, and no Aura instance for the project.
- [ ] The guide is in the repository and John has it as a PDF.
- [ ] The scrub grep returns nothing.

**Committed and deployed.** Tag `v0.1.5-handoff` in John's repository.

**Email to John after the call.** The link, the guide as PDF, the after list, thanks, and if there is a redirect, the date it stops.

**Risks.**

* John cannot create the Aura Free instance on the call because his account already holds one (Aura Free is one per account) with his earlier experiments in it: ask him on the call whether it can be deleted; if not, the record stays on Eston's instance for one more week while he decides, and Eston's instance is the only thing left pointing at Eston. Say so in the after-call email with a date.
* Accounts missing on Thursday: the call creates them with John sharing his screen; the blueprint happens Friday 25 on a second short call. Say so in the Session 5 email so it is not a surprise.
* The subdomain reclaim fails: the static redirect; verified Tuesday so the answer is known before the call.
* Render's free signup changed: check Tuesday 22.

---

## Between sessions

### The Saturday email (client-facing draft)

Subject: Seed statements for your approval, and three small questions

> Hi John,
>
> Below are the statements the demo will open with. One issue, five parts of it, fourteen statements with the documents they cite. Five are your own words, including the paragraph from your note to Justin about autonomy and supreme law. The rest are drafted so the Issues page has some shape on the first day; they will appear under the name "Seed" until you approve them, and each one you approve moves under your name. Two of them argue the other side, citing the Montreal Protocol and the General Assembly's powers, so the record has evidence both ways from day one. Please read them as if you had written them, strike anything, change anything, and send more paragraphs of your own if you have them.
>
> On accounts: you do not need to send me anything now. I am building everything in my own accounts so you have a link as soon as possible, and on our call at the end we move all of it into yours. Two things to set up before then, whenever convenient in the next two weeks, both with your Google sign-in: an account at render.com, which will host the site, and an account at platform.deepseek.com with five dollars of credit, which pays for the reading service. I will send exact steps closer to the time.
>
> Three questions. A short answer to each is plenty, and if you do not answer I will go with the default in brackets.
>
> 1. The sentence at the top of the page, which everyone reads first. [My draft: "Write what you think about an issue that matters to you. We will pull out the issue, your claim, any evidence and any solution, show you what we found, and add it to a record everyone here shares."]
> 2. When someone proposes a solution, should the site record that they approve it, or only record "approves" when they say so? [Only when they say so. Every solution on the confirm card has a one-tap choice, so nothing is lost, and the counts stay honest. Your drug policy example would show one "approves" line, for "Deal with it as a medical issue", and a tap would add the other.]
> 3. The two statements arguing the other side: under whose name? [A name of your choosing; otherwise "Counterpoint".]
>
> A rough first version reaches you early next week.
>
> Warm regards,
> Eston

Then the client-facing section of `06_seed.md`.

### Later emails

Monday 7, after Session 1: the link and passphrase; rough warning; three things to try; anything outstanding from Saturday.

Wednesday 9, after Session 2: the Issues page; what "Most people" means; Seed and Counterpoint until approval.

Saturday 12, after Session 3 and only with his key deployed: the smart part; what to try; the approve rule as he chose it.

Tuesday 15, after Session 4: ready for friends; the three honest notes; feedback by Sunday 20; the after list; the second invoice.

Monday 21, after Session 5: statuses; after list; call time; the two things to do before it.

Thursday 24, after the call: the link, the guide, the after list, thanks.

### Accounts John must create

| Account | By | How | Cost |
|---|---|---|---|
| GitHub | exists: `Jkintree2` | nothing to do; accept the transfer email on Wednesday 23 | 0 |
| Render via Google | Tuesday 22 September ("done" by email) | render.com, sign up with Google | 0; 7 USD a month only if he later wants no slow first visit |
| DeepSeek platform, 5 USD balance, one key | Tuesday 22 September ("done" by email); the key is pasted on the call, never emailed | platform.deepseek.com; top up; create a key | 5 USD once |
| Neo4j Aura Free instance in his account | On the call, Thursday 24 | console.neo4i.io, New instance, Free, download the credentials file; if his account already holds a Free instance, decide on the call whether it can go | 0 |
| UptimeRobot via Google | On the call, Thursday 24 | uptimerobot.com, sign in with Google | 0 |

Eston's accounts during the build: GitHub (repository), Render (service), Aura Free instance `oci` (production), DeepSeek (key). All four are emptied or deleted after the call.

### The morning after each deploy (Eston, ten minutes)

1. Open the live URL in a private window; note a cold start.
2. During the build weeks: post one sentence, confirm, delete from the admin page once it exists. During the test week (16 to 20 September): do not post; read only.
3. Render logs: filter `"status": "error"`, `"status": "timeout"`, `"status": "auth"`; read any `extract` over 10 seconds.
4. Aura console: Running, not Paused.
5. Actions tab (build weeks only): the keep-alive ran in the last 10 minutes.
6. John's emails: one-line replies or the after list; batch wording changes for Session 5.

---

## Disposition of every finding

| Finding | Disposition |
|---|---|
| C1 budget | Fixed: honest 25.5 h, cuts made, calendar moved to Wednesday 16. The remaining 1.5 h over is accepted as Eston's cost of a fixed fee. |
| C2 handoff sequence | Fixed: transfer target is `Jkintree2`; Render and DeepSeek accounts by Tuesday 22; transfer Wednesday 23; call Thursday 24 with the database migration; fallback branch written. |
| C3 reset wipes John's instance | Fixed: production is Eston's own instance until handoff; John's instance is created on the call and only ever restored into; `--reset` guard; local Docker database for development. |
| C4 paused Aura kills boot | Fixed: non-fatal check, asleep page, restore script. |
| C5 drafted text under John's name | Fixed: "Seed" until approved, per-statement flip. |
| C6 APPROVE rule versus case 1 | Fixed: case 1 corrected; question 2 on Saturday with the default. |
| C7 junk-drawer Issues page | Fixed: inclusive counts, chips row, "Write about this issue" in Session 3. |
| C8 keep-alive dies | Fixed: cron only during the build; UptimeRobot in John's name at handoff; Aura idle-timer test on 12 to 14 September. |
| C9 no dev database | Fixed: local Neo4j 5 in Docker for the whole project; inline-variable seed of production; branch during the test week. |
| M1 autocomplete deferred | Fixed: datalists in the first pass; iPhone check in Session 3; substring fallback. |
| M2 sub-issue as parent | Fixed in `03_schema.md` and `05_extraction.md`. |
| M3 second parent | Fixed: WHERE guard. |
| M4 junk names persist | Fixed: orphan cleanup on delete, newline strip, candidate cap. |
| M5 bucket and balance | Fixed: 6 a minute, 300 a day; model error line; guide entry. |
| M6 provider assumptions | Fixed: raw call first; `thinking` only for DeepSeek. |
| M7 anonymous stores the name | Fixed: null `display_name`, no cookie; count inflation accepted and explained. |
| M8 impersonation | Accepted for 0.1: a closed test among friends; made visible in the email and the guide; individual accounts are the priced fix. |
| M9 delete removes MERGEd edges | Fixed: MERGEd types are not deleted. |
| M10 "Seed author" | Fixed: question 3; default "Counterpoint". |
| M11 seed email errors | Fixed in `06_seed.md`. |
| M12 HEAD checks | Fixed: browser user agent, follow redirects. |
| M13 750 hours | Fixed: workspace check Sunday; static redirect; guide line. |
| M14 pointers to Eston | Fixed: scrub list, noreply email, generated secrets, no recording, restore script, key before friends, password manager entry deleted; the webhook dies with the service. |
| M15 guide gaps | Fixed: topic list rewritten; `SITE_SENTENCE` variable. |
| M16 DeepSeek disclosure | Fixed: gate copy. |
| M17 raw text and links | Fixed: `noopener`; Post gated on `found: false`. |
| M18 CLAUDE.md paths | Fixed: `docs/planning/` in the repo; session number in the first message. |
| M19 live test option | Fixed: removed. |
| M20 candidate cache | Fixed: removed. |
| M21 invoice timing | Fixed: Tuesday 15 with the testable release. |
| M22 URL change | Fixed: reclaim the service name, verified Tuesday 22; static redirect as fallback. |
| m1 to m11, m13 to m17, m20, m22 | Fixed as listed in the changelog. |
| m12 non-English | After list. The reference file asks for the refusal; the model would do Spanish for free later. |
| m18, m19 | No change needed. |
| m21 name cookie | Accepted: the no-JavaScript form needs server-side prefill; the cookie is never set on an anonymous post. |
| Table: export | Keep plus restore. |
| Table: delete post | Keep, orphans fixed, MERGEd edges kept. |
| Table: request id | Kept in logs only. |
| Table: token bucket | Tightened. |
| Table: live test suite | Cut; replaced by `scripts/cards.py` that prints, no assertions. |
| Table: extraction log, live-test doc | Cut. |
| Table: "Write about this issue" | Promoted to Session 3. |
| Table: rollup | Kept with inclusive sort. |
| Table: keep-alive | Replaced at handoff. |
| Table: cookies | Two kept plus the name cookie (see m21). |
| Table: pagination | Deferred; 60 posts shown; after list. |
| Table: "posting as" header | Cut. |
| Table: admin token page | Replaced by basic auth. |
| Table: `test_graph.py` live | Cut. |
| Table: `test_auth.py` | Two cases. |
| Table: cache | Cut. |
| Table: tags, access log, typed RESET, seed policy | Kept. |
