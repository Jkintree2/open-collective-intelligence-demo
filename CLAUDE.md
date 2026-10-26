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

`app/` (FastAPI routes in `routes_*.py`, Cypher only in `graph*.py`, templates, `static/`), `scripts/`, `seed/`, `tests/`, `docs/`. The one-line-per-file map is `docs/code-map.md`: read it before changing a file you have not opened. Add a line there for every new file.

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

Every push to `main` deploys to Render. There is no staging. So: run `pytest` and open the local site before every push, and push small. After each deploy, run `python -m scripts.smoke --url <the live address>` (it reads, never writes, so it is the one check allowed against production; `git fetch` first so `origin/main` is the merged commit). If a deploy breaks the live site, revert the commit and push again; do not fix forward on a broken site. Environment variables live in the Render dashboard, never in the repo. `render.yaml` describes the service so it can be recreated in another Render account by "New Blueprint".

Phase 2 (evidence that checks itself) runs behind `EVIDENCE_CHECK_ENABLED`, set in the Render dashboard; unset, the card is the Phase 1 card and nothing is fetched. `DEEPSEEK_FETCH=0` stops the backup reader. Change your email (X2) has its own switch, `EMAIL_CHANGE_ENABLED`, also in the dashboard; unset, Your account has no change of email form and its pages answer not found. Phase 1 runs behind `ACCOUNTS_ENABLED`; unset, the site keeps the passphrase and the 0.1 rules for posts, stances and the order of solutions (decision X1), and keyword search on the Issues page works too. Its variables (`SITE_URL`, `MAIL_FROM`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `ACCOUNTS_ENABLED`) live in the Render dashboard. The Gmail values come from John's own Google project, with the send permission only, and only John types them in.

Phase 3 (talking to the record) has four switches, each set in the Render dashboard and off unless set: `ASK_ENABLED` (Ask the record: `/ask` and the box on each issue page), `FOLLOW_UPS_ENABLED` (follow-up questions on the card), `PLACES_ENABLED` (the Place row on the card, the place under each post and the Near filter on the Issues page) and `ABOUT_ENABLED` (`/about`). Unset, the menu item is absent, the pages answer not found and nothing is read, written or sent for that part. The guiding principles have no switch: the extraction prompt stays byte for byte the same.

## Schema in brief

Nodes: `Person {key, name, anonymous}`, `Issue {key, name, seed}`, `Solution {key, name, seed}`, `Evidence {key, name, url, seed}`, `Post {id, text, created_at, anonymous, display_name, source, extraction_raw, edited_at}` (since Phase 3 also `place_country`, an ISO two-letter code or null, `place_area`, as typed, and `place_area_key`, its `make_key`; written only with `PLACES_ENABLED`; range indexes on `place_country` and `place_area_key`), `Change {id, kind, created_at, details}`. `key` is the normalised name (`text.make_key`), except on accounts. An account is a `Person` with an `email`: key `acct:<uuid4>`, plus `email` (lower-cased, unique), `country`, `postal_code`, `password_hash` (scrypt; null until accepted and after a restore), `admin` (John's account only), `active`, `created_at`, `accepted_at`, and one live link: `token_hash`, `token_purpose` (`invite` or `reset`), `token_expires_at`. Password and link fields never reach a template, a log or a copy. Unique constraints on all keys, on `Post.id`, `Person.email`, `Person.token_hash` and `Change.id`; full-text indexes `record_names` (Issue, Solution and Evidence names) and `post_text`.

Edges, from actor to target, each carrying `post_id` and `created_at` (Person edges also `anonymous`): `POSTED`, `CLAIM`, `SUBMIT`, `PROPOSE`, `HAVE_PROPOSED` (Issue to Solution, MERGE), `SUPPORTS`, `REFUTES` (Evidence to Issue, Solution or Evidence), `APPROVE`, `OPPOSE` (Person to Solution, MERGE one per pair; with `ACCOUNTS_ENABLED` set, one stance per person and solution: a new stance, by click or by a post, replaces the opposite one, and pairs left from 0.1 stay until that person takes a new stance; unset, posts follow the 0.1 rule and may hold both; a click stance carries `source: "click"` and no `post_id`), `PART_OF` (sub-issue to top-level issue, one level; one made by tidying has no `post_id`). Phase 1 adds `ENTERED` (account to account: `relationship`, `agreed`, `created_at`; one into every account except John's, the root), `MADE` (admin account to `Change`) and `CHANGED` (`Change` to `Issue`, moved to the kept issue on a merge). No other labels or types. `DECIDE` is deliberately absent.

Display verbs: claims, submits evidence, proposes solution, has proposed, supports, refutes, approves, opposes; supports and refutes name what they speak to (`supports issue of`, `solution of`, `evidence of`). Sentences are `display name, lowercase verb, node name`. An issue already in the record reads "claims about existing issue <name>" under "What this will add", and its card row says "This issue is already in the record." (John, 24 October 2026).

## Rules

1. **No features outside the agreed scope.** If a task seems to need one, stop and agree it with John first.
2. **No new dependency without a one-line reason in the commit message.** The allowed set is in `requirements.txt`. A CDN script counts as a dependency.
3. **Every push deploys, so every push must work.** Tests green, local site opened, then push.
4. **The model is optional.** Any change to compose must be checked once with `LLM_API_KEY` unset.
5. **Copy is John's.** Interface words come from `04_interface.md`. Never write node, edge, graph, Cypher, model, extraction or entity where a tester can read it. No dashes in client-facing text.
6. **Cypher lives in the `graph*.py` modules only** (`graph.py`, and since Phase 1 `graph_accounts.py`, `graph_stances.py`, `graph_own_posts.py`, `graph_search.py`, `graph_tidy.py`, since Phase 2 `graph_evidence.py`, and since Phase 3 `graph_ask.py` and `graph_places.py`). Relationship types and labels are substituted from whitelists, never from user input.
7. **Secrets never touch the repo, logs or templates.** Log the request id, sizes, latencies and counts; log text only at DEBUG.
8. **Nothing personal to the builder in the repo.** No URLs, emails or account names. LICENSE and README name John.
9. **Seed is loaded by `scripts/seed.py` or the admin page, never at startup.** The first account is made once, by `scripts/make_admin.py`, never at startup.
10. **Keep files small and boring.** If a script in `app/static/` passes 400 lines or `graph.py` passes 500, split by responsibility before adding more.
11. **Production is never a test target.** Local runs, tests and resets use the local Docker database. Work on a branch and merge to `main` only with the tests green.
12. **Copy that John may change lives in environment variables.** The site name and the sentence at the top are `SITE_NAME` and `SITE_SENTENCE`; do not hard-code them in a template.

## Done means

The change is verified in a browser or terminal, `pytest` is green, the commit is pushed, the deploy is green on Render, `scripts.smoke` passes against it, and the live URL was opened after the deploy.
