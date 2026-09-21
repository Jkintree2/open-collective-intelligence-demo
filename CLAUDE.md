# Open Collective Intelligence demo

A closed-test website where a small group of people write statements about issues they care about; a language model pulls out the issue, claim, evidence and solution; the writer corrects it; and it merges into a shared Neo4j graph that everyone can read. Version 0.1, built for John Kintree under a fixed-scope statement of work. This file is for a coding session starting cold.

## Read first

`docs/planning/` in this repository holds copies of the planning documents. The ones that matter for any code change:

* `docs/planning/03_schema.md`: node labels, relationship types, every Cypher query. The schema is not to be extended without an entry in the plan.
* `docs/planning/04_interface.md`: every screen, every piece of copy John reads (marked client-facing).
* `docs/planning/05_extraction.md`: the model call, the JSON contract, the system prompt, the test cases, the APPROVE rule.
* `docs/planning/06_seed.md`: the seed record and its expected counts.
* `docs/planning/07_scope_guard.md`: what is in, what is out, and the sentence for everything else.
* `docs/planning/PLAN_v2.md`: the sessions, and what "done" means for each.

The session number and its checklist are given in the first message of the session. If they are absent, ask before writing code.

## Stack

Python 3.12, FastAPI, Jinja2, uvicorn. `neo4j` driver 6.x against Neo4j Aura Free. `httpx` for the one model call (OpenAI-compatible chat completions, DeepSeek by default). One CSS file, one vanilla JavaScript file, no build step, no npm. pytest. Hosted on Render (free web service, auto-deploy from `main`). No other services, no other dependencies without a reason in the commit message.

## Layout

```
app/main.py        FastAPI app, routes, lifespan (driver open/close, non-fatal connectivity check), request-id middleware, error and asleep pages
app/config.py      settings from environment variables; app refuses to start without DEMO_PASSPHRASE, SECRET_KEY, ADMIN_TOKEN, NEO4J_*; SITE_NAME and SITE_SENTENCE have defaults
app/auth.py        passphrase cookie (signed, 30 days, embeds a hash of the passphrase), admin HTTP basic auth
app/graph.py       driver, constraints, all Cypher as constants, merge_post(), group_issues(), read queries; RecordAsleep on ServiceUnavailable
app/extract.py     prompt, model call with one retry, last_model_error, Extraction; re-exports CardPayload and resolution
app/payload.py     card models, cleaning, reference resolution
app/graph_runtime.py process driver, query execution, RecordAsleep; no Cypher
app/graph_posts.py post and seed write orchestration; no Cypher
app/graph_backup.py admin deletion, export and restore transactions; no Cypher
app/backup.py      portable export format, typed values and input validation
app/admin.py       Basic-auth admin routes and safe reading-error summaries
app/issue_groups.py inclusive issue counts and sorting; no Cypher
app/text.py        normalise(), make_key(), clean_name(), sentences(payload, display_name)
app/templates/     base, enter, index, issues, issue, admin, error, asleep, _feed and _about_issue (fragments)
app/static/        app.css, app.js, about_issue.js (the summary above the write form)
seed/seed.json     the seed record, same shape as the card payload
scripts/__init__.py
scripts/seed.py    python -m scripts.seed [--counts] [--reset --yes [--force]]; reset refuses a database holding non-seed nodes
scripts/cards.py   prints the card the live model produces for each case in tests/extraction_cases.json (needs LLM_API_KEY)
scripts/restore.py loads an admin export into an empty database
tests/             test_text.py, test_auth.py, test_payload.py, test_grouping.py, extraction_cases.json, fixtures/ (no network, no database)
docs/operators-guide.md   client-facing guide for John
docs/planning/     copies of the planning documents
render.yaml        Render blueprint; SECRET_KEY and ADMIN_TOKEN are generateValue: true
.github/workflows/keepalive.yml   every 10 minutes GET /health; build-time only, deleted before the repository is transferred
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

The local `.env` points at the development database, a local Neo4j 5 in Docker (`docker run -d --name oci-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/localpass neo4j:5`, then `NEO4J_URI=neo4j://localhost:7687`), never at production. Production is an Aura Free instance and is written to only by the deployed app and by one deliberate seed load with the connection variables typed inline. On Aura Free the only user database is named after the instance id, not `neo4j`, so `NEO4J_DATABASE` must be set to that id on Render (it is `sync: false` in the blueprint); without it startup fails with `DatabaseNotFound`. `--reset` against production is never run from a saved file.

## Deploy

Every push to `main` deploys to Render. There is no staging. So: run `pytest` and open the local site before every push, and push small. If a deploy breaks the live site, revert the commit and push again; do not fix forward on a broken site. Environment variables live in the Render dashboard, never in the repo. `render.yaml` describes the service so it can be recreated in another Render account by "New Blueprint".

## Schema in brief

Nodes: `Person {key, name, anonymous}`, `Issue {key, name, seed}`, `Solution {key, name, seed}`, `Evidence {key, name, url, seed}`, `Post {id, text, created_at, anonymous, display_name, source, extraction_raw}`. `key` is the normalised name (`text.make_key`). Unique constraints on all keys and on `Post.id`.

Edges, from actor to target, each carrying `post_id` and `created_at` (Person edges also `anonymous`): `POSTED`, `CLAIM`, `SUBMIT`, `PROPOSE`, `HAVE_PROPOSED` (Issue to Solution, MERGE), `SUPPORTS`, `REFUTES` (Evidence to Issue, Solution or Evidence), `APPROVE`, `OPPOSE` (Person to Solution, MERGE one per pair), `PART_OF` (sub-issue to top-level issue, one level). No other labels or types. `DECIDE` is deliberately absent.

Display verbs: claims, submits, proposes, has proposed, supports, refutes, approves, opposes. Sentences are `display name, lowercase verb, node name`.

## Rules

1. **No features outside `07_scope_guard.md`.** If a task seems to need one, stop and write it into the after list instead.
2. **No new dependency without a one-line reason in the commit message.** The allowed set is in `requirements.txt`. A CDN script counts as a dependency.
3. **Every push deploys, so every push must work.** Tests green, local site opened, then push.
4. **The model is optional.** Any change to compose must be checked once with `LLM_API_KEY` unset.
5. **Copy is John's.** Interface words come from `04_interface.md`. Never write node, edge, graph, Cypher, model, extraction or entity where a tester can read it. No dashes in client-facing text.
6. **Cypher lives in `graph.py` only.** Relationship types and labels are substituted from whitelists, never from user input.
7. **Secrets never touch the repo, logs or templates.** Log the request id, sizes, latencies and counts; log text only at DEBUG.
8. **Nothing personal to the builder in the repo.** No URLs, emails or account names. LICENSE and README name John.
9. **Seed is loaded by `scripts/seed.py` or the admin page, never at startup.**
10. **Keep files small and boring.** If `app.js` passes 400 lines or `graph.py` passes 500, split by responsibility before adding more.
11. **Production is never a test target.** Local runs, tests and resets use the local Docker database. During the test week (16 to 20 September) work on a branch and merge to `main` only with the session checklist green.
12. **Copy that John may change lives in environment variables.** The site name and the sentence at the top are `SITE_NAME` and `SITE_SENTENCE`; do not hard-code them in a template.

## Done means

The session's checklist in `docs/planning/PLAN_v2.md` is verified in a browser or terminal, the commit is pushed, the deploy is green on Render, and the live URL was opened after the deploy.
