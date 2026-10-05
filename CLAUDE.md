# Open Collective Intelligence demo

A closed-test website where a small group of people write statements about issues they care about; a language model pulls out the issue, claim, evidence and solution; the writer corrects it; and it merges into a shared Neo4j graph that everyone can read. Version 0.1, built for John Kintree under a fixed-scope statement of work, extended by Phase 1 ("People and positions", SOW 0.2): invited accounts, one-click stances, editing and deleting one's own posts, keyword search, and tidying the issue tree with a list of changes. This file is for a coding session starting cold.

## Read first

`docs/planning/` in this repository holds copies of the planning documents. The ones that matter for any code change:

* `docs/planning/03_schema.md`: node labels, relationship types, every Cypher query. The schema is not to be extended without an entry in the plan.
* `docs/planning/04_interface.md`: every screen, every piece of copy John reads (marked client-facing).
* `docs/planning/05_extraction.md`: the model call, the JSON contract, the system prompt, the test cases, the APPROVE rule.
* `docs/planning/06_seed.md`: the seed record and its expected counts.

The scope is the one agreed in the statement of work. If a task is unclear, ask before writing code.

## Stack

Python 3.12, FastAPI, Jinja2, uvicorn. `neo4j` driver 6.x against Neo4j Aura Free. `httpx` for the one model call (OpenAI-compatible chat completions, DeepSeek by default). One CSS file, one vanilla JavaScript file, no build step, no npm. pytest. Hosted on Render (free web service, auto-deploy from `main`). No other services, no other dependencies without a reason in the commit message.

## Layout

```
app/main.py        FastAPI app, page routes, lifespan (driver open/close, non-fatal connectivity check), request-id middleware (emailed links cut from the log through pages.loggable_path), the CrossSite handler, error and asleep pages; include_routers() adds every app/routes_*.py router
app/config.py      settings from environment variables; refuses to start without DEMO_PASSPHRASE, SECRET_KEY, ADMIN_TOKEN, NEO4J_*, and SITE_URL when ACCOUNTS_ENABLED is true; SITE_NAME and SITE_SENTENCE have defaults; MAIL_FROM, GMAIL_* and MAIL_CONSOLE for email
app/auth.py        passphrase cookie (signed, 30 days, embeds a hash of the passphrase), admin HTTP basic auth and form tokens, in-process limits (MinuteBucket, KeyedLimit, DailyLimit, PostSpacing)
app/accounts.py    emails, scrypt passwords (two at a time), link secrets and lifetimes, the member cookie, person_name(), entry_state(), every account limiter (sign in, entering, forgot per minute, the per address link limit); no I/O
app/members.py     who is reading: Member, current_member, member_key, require_access, require_member, require_same_origin and CrossSite, wants_json, member cookies, safe_next, posting_identity
app/pages.py       page() and link_problem() for router modules; loggable_path() for the request log; WRITE_NOTICES and write_notice() for the write page
app/mailer.py      send(): Gmail API with the send permission only, over httpx (MAIL_CONSOLE prints instead, locally); last_mail_error for the back room
app/emails.py      the invitation, first account and password emails, word for word from 04_interface.md
app/graph.py       constraints and full-text indexes, the 0.1 Cypher as constants (Q1, Q3 and Q10 revised for Phase 1; the one-stance statement and ranked Q4 beside the 0.1 ones, chosen by ACCOUNTS_ENABLED), merge_post(), group_issues(), read queries
app/graph_runtime.py process driver, query execution, RecordAsleep; no Cypher
app/graph_posts.py post and seed write orchestration; write_payload() is shared by posting and editing, with the one_stance switch; no Cypher of its own (it runs the statements in graph.py)
app/graph_backup.py admin deletion, export and restore transactions; no Cypher
app/graph_accounts.py account Cypher (Q12 to Q22)
app/graph_stances.py one stance per person and solution (Q23)
app/graph_own_posts.py own posts: Q24, Q25 and the feed's yes or no flags (Q7)
app/graph_search.py keyword search (Q26, Q27)
app/graph_tidy.py  move, rename, merge and their change record (Q28 to Q32)
app/backup.py      portable export format version 2 (version 1 still restores), typed values and validation; passwords and links never in a copy
app/admin.py       Basic-auth back room routes, the reading service and sending email lines
app/routes_accounts.py /sign-in, /sign-out, /account, /forgot-password, /reset/{link}
app/routes_people.py   /people (enter, send again, withdraw) and /accept/{link}
app/routes_stances.py  approve and oppose on the issue page
app/routes_own_posts.py editing (with or without JavaScript, the card built from the post's current edges) and deleting one's own post
app/routes_tidy.py     rename, move and merge an issue; /changes
app/routes_admin_people.py the back room's People section (/admin/people)
app/search.py      the safe keyword query and grouped results
app/tidy.py        who may tidy, tidying copy and change sentences, tidied_names() for reloading the seed
app/extract.py     prompt, model call with one retry, last_model_error, Extraction; re-exports CardPayload and resolution
app/payload.py     card models, cleaning, reference resolution
app/issue_groups.py inclusive issue counts and sorting; no Cypher
app/text.py        normalise(), make_key(), clean_name(), sentences(payload, display_name)
app/templates/     base, enter, sign_in, account, forgot, reset, people, withdraw, accept, link_problem, index, issues, issue, delete_post, merge_confirm, changes, admin, error, asleep; fragments _feed, _post, _about_issue, _record_notice, _stance, _tidy, _admin_people
app/static/        app.css (one anchor per Phase 1 sub-plan); card.js (card, preview, Post), dictation.js (speech input), app.js (page wiring; loads last), about_issue.js (the summary above the write form), stances.js (approve and oppose in place), edit_post.js (opens the card on a post being edited), once.js (submit once guard for forms marked data-once; loaded from base.html)
seed/seed.json     the seed record, same shape as the card payload
scripts/__init__.py
scripts/seed.py    python -m scripts.seed [--counts] [--reset --yes [--force]]; reset keeps accounts and refuses a database holding non-seed nodes; reload writes nothing when complete and reads tidied seed issues as they are now
scripts/make_admin.py John's own account, the root of who entered whom: NEO4J_* from the shell only (never .env), prints the database host and name, needs --yes, refuses a database on this machine unless --local, sends nothing; his first link comes from "Forgot your password?"
scripts/cards.py   prints the card the live model produces for each case in tests/extraction_cases.json (needs LLM_API_KEY)
scripts/probe_reading.py one reading service preflight call; prints capability results, never credentials
scripts/restore.py loads an admin export into an empty database
tests/             offline by default (no network, no database); conftest.py (live_graph, member_app), page_harness.js (the fake page every *.cjs test drives); test_live_*.py are marked live and run only against the disposable Neo4j on port 7688; extraction_cases.json, fixtures/
docs/operators-guide.md   client-facing guide for John
docs/planning/     copies of the planning documents
render.yaml        Render blueprint; SECRET_KEY and ADMIN_TOKEN are generateValue: true
```

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in NEO4J_*, DEMO_PASSPHRASE, SECRET_KEY, ADMIN_TOKEN; LLM_API_KEY optional
python -m scripts.seed      # idempotent
uvicorn app.main:app --reload --port 8000
pytest                      # no network needed for the default set
```

Open http://localhost:8000, enter the passphrase, write something. Without `LLM_API_KEY` the card opens empty and you fill it by hand; that path must always work.

Accounts locally: set `ACCOUNTS_ENABLED=true`, `APP_ENV=local`, `SITE_URL=http://localhost:8000` and `MAIL_CONSOLE=1`, and leave `GMAIL_*` unset; emails, links included, print to the uvicorn terminal instead of going out (`MAIL_CONSOLE` does nothing outside `APP_ENV=local`). Make the local first account with `NEO4J_URI=neo4j://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=localpass python -m scripts.make_admin --email john@example.org --name "John Kintree" --local --yes`, then choose its password through "Forgot your password?". Use `example.org` addresses only.

Page scripts: `node --test tests/*.cjs` (not `node --test tests/`). Live tests need the disposable Neo4j: `docker run -d --name oci-neo4j-test -p 7688:7687 -e NEO4J_AUTH=neo4j/testpass1 neo4j:5`, then `OCI_TEST_NEO4J_URI=neo4j://localhost:7688 OCI_TEST_NEO4J_PASSWORD=testpass1 python -m pytest -m live`. They wipe that database and refuse port 7687.

The local `.env` points at the development database, a local Neo4j 5 in Docker (`docker run -d --name oci-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/localpass neo4j:5`, then `NEO4J_URI=neo4j://localhost:7687`), never at production. Production is an Aura Free instance and is written to only by the deployed app, by one deliberate seed load and by one `scripts.make_admin` run at rollout, each with the connection variables typed inline. On Aura Free the only user database is named after the instance id, not `neo4j`, so `NEO4J_DATABASE` must be set to that id on Render (it is `sync: false` in the blueprint); without it startup fails with `DatabaseNotFound`. `--reset` against production is never run from a saved file.

## Deploy

Every push to `main` deploys to Render. There is no staging. So: run `pytest` and open the local site before every push, and push small. If a deploy breaks the live site, revert the commit and push again; do not fix forward on a broken site. Environment variables live in the Render dashboard, never in the repo. `render.yaml` describes the service so it can be recreated in another Render account by "New Blueprint".

Phase 1 runs behind `ACCOUNTS_ENABLED`; unset, the site keeps the passphrase and the 0.1 rules for posts, stances and the order of solutions (decision X1), and keyword search on the Issues page works too. Its variables (`SITE_URL`, `MAIL_FROM`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `ACCOUNTS_ENABLED`) live in the Render dashboard. The Gmail values come from John's own Google project, with the send permission only, and only John types them in.

## Schema in brief

Nodes: `Person {key, name, anonymous}`, `Issue {key, name, seed}`, `Solution {key, name, seed}`, `Evidence {key, name, url, seed}`, `Post {id, text, created_at, anonymous, display_name, source, extraction_raw, edited_at}`, `Change {id, kind, created_at, details}`. `key` is the normalised name (`text.make_key`), except on accounts. An account is a `Person` with an `email`: key `acct:<uuid4>`, plus `email` (lower-cased, unique), `country`, `postal_code`, `password_hash` (scrypt; null until accepted and after a restore), `admin` (John's account only), `active`, `created_at`, `accepted_at`, and one live link: `token_hash`, `token_purpose` (`invite` or `reset`), `token_expires_at`. Password and link fields never reach a template, a log or a copy. Unique constraints on all keys, on `Post.id`, `Person.email`, `Person.token_hash` and `Change.id`; full-text indexes `record_names` (Issue, Solution and Evidence names) and `post_text`.

Edges, from actor to target, each carrying `post_id` and `created_at` (Person edges also `anonymous`): `POSTED`, `CLAIM`, `SUBMIT`, `PROPOSE`, `HAVE_PROPOSED` (Issue to Solution, MERGE), `SUPPORTS`, `REFUTES` (Evidence to Issue, Solution or Evidence), `APPROVE`, `OPPOSE` (Person to Solution, MERGE one per pair; with `ACCOUNTS_ENABLED` set, one stance per person and solution: a new stance, by click or by a post, replaces the opposite one, and pairs left from 0.1 stay until that person takes a new stance; unset, posts follow the 0.1 rule and may hold both; a click stance carries `source: "click"` and no `post_id`), `PART_OF` (sub-issue to top-level issue, one level; one made by tidying has no `post_id`). Phase 1 adds `ENTERED` (account to account: `relationship`, `agreed`, `created_at`; one into every account except John's, the root), `MADE` (admin account to `Change`) and `CHANGED` (`Change` to `Issue`, moved to the kept issue on a merge). No other labels or types. `DECIDE` is deliberately absent.

Display verbs: claims, submits, proposes, has proposed, supports, refutes, approves, opposes. Sentences are `display name, lowercase verb, node name`.

## Rules

1. **No features outside the agreed scope.** If a task seems to need one, stop and agree it with John first.
2. **No new dependency without a one-line reason in the commit message.** The allowed set is in `requirements.txt`. A CDN script counts as a dependency.
3. **Every push deploys, so every push must work.** Tests green, local site opened, then push.
4. **The model is optional.** Any change to compose must be checked once with `LLM_API_KEY` unset.
5. **Copy is John's.** Interface words come from `04_interface.md`. Never write node, edge, graph, Cypher, model, extraction or entity where a tester can read it. No dashes in client-facing text.
6. **Cypher lives in the `graph*.py` modules only** (`graph.py`, and since Phase 1 `graph_accounts.py`, `graph_stances.py`, `graph_own_posts.py`, `graph_search.py`, `graph_tidy.py`). Relationship types and labels are substituted from whitelists, never from user input.
7. **Secrets never touch the repo, logs or templates.** Log the request id, sizes, latencies and counts; log text only at DEBUG.
8. **Nothing personal to the builder in the repo.** No URLs, emails or account names. LICENSE and README name John.
9. **Seed is loaded by `scripts/seed.py` or the admin page, never at startup.** The first account is made once, by `scripts/make_admin.py`, never at startup.
10. **Keep files small and boring.** If a script in `app/static/` passes 400 lines or `graph.py` passes 500, split by responsibility before adding more.
11. **Production is never a test target.** Local runs, tests and resets use the local Docker database. Work on a branch and merge to `main` only with the tests green.
12. **Copy that John may change lives in environment variables.** The site name and the sentence at the top are `SITE_NAME` and `SITE_SENTENCE`; do not hard-code them in a template.

## Done means

The change is verified in a browser or terminal, `pytest` is green, the commit is pushed, the deploy is green on Render, and the live URL was opened after the deploy.
