# Code map

One line per file: what lives where. Read the line for a file before changing it; CLAUDE.md points here so it stays short.

```
app/main.py        FastAPI app, page routes, lifespan (driver open/close, non-fatal connectivity check), request-id middleware (emailed links cut from the log through pages.loggable_path), the CrossSite handler, error and asleep pages; include_routers() adds every app/routes_*.py router
app/config.py      settings from environment variables; refuses to start without DEMO_PASSPHRASE, SECRET_KEY, ADMIN_TOKEN, NEO4J_*, and SITE_URL (https, or http on this machine with APP_ENV=local) when ACCOUNTS_ENABLED is true; SITE_NAME and SITE_SENTENCE have defaults; MAIL_FROM, GMAIL_* and MAIL_CONSOLE for email
app/auth.py        passphrase cookie (signed, 30 days, embeds a hash of the passphrase), admin HTTP basic auth and form tokens, in-process limits (MinuteBucket, KeyedLimit, DailyLimit, PostSpacing)
app/accounts.py    emails, scrypt passwords (two at a time), link secrets and lifetimes, the member cookie, person_name(), entry_state(), every account limiter (sign in, entering, forgot per minute, the per address link limit); no I/O
app/members.py     who is reading: Member, current_member, member_key, require_access, require_member, require_same_origin and CrossSite, wants_json, member cookies, safe_next, posting_identity
app/pages.py       page() and link_problem() for router modules; loggable_path() for the request log; WRITE_NOTICES and write_notice() for the write page
app/mailer.py      send(): Gmail API with the send permission only, over httpx (MAIL_CONSOLE prints instead, locally); last_mail_error for the back room
app/emails.py      the invitation, first account, password and change of email emails, word for word from 04_interface.md
app/graph.py       constraints and full-text indexes, the 0.1 Cypher as constants (Q1, Q3 and Q10 revised for Phase 1; the one-stance statement and ranked Q4 beside the 0.1 ones, chosen by ACCOUNTS_ENABLED), merge_post(), group_issues(), read queries
app/graph_runtime.py process driver, query execution, RecordAsleep; no Cypher
app/graph_posts.py post and seed write orchestration; write_payload() is shared by posting and editing, with the one_stance switch; no Cypher of its own (it runs the statements in graph.py)
app/graph_backup.py admin deletion, export and restore transactions; no Cypher
app/graph_accounts.py account Cypher (Q12 to Q22)
app/graph_stances.py one stance per person and solution (Q23)
app/graph_own_posts.py own posts: Q24, Q25 and the feed's yes or no flags (Q7)
app/graph_search.py keyword search (Q26, Q27)
app/graph_tidy.py  move, rename, merge and their change record (Q28 to Q32)
app/graph_evidence.py Phase 2: statements 5 and 5b with the check and source facts, one post's stored readings (Q35), and the issue page's source confidence read (Q39)
app/backup.py      portable export format version 2 (version 1 still restores), typed values and validation; passwords and links never in a copy
app/admin.py       Basic-auth back room routes, the reading service and sending email lines
app/routes_accounts.py /sign-in, /sign-out, /account (My account), /my-statements (X1, its own page and menu item), /forgot-password, /reset/{link}
app/routes_people.py   /people (enter, send again, withdraw) and /accept/{link}
app/routes_stances.py  approve and oppose on the issue page
app/routes_own_posts.py editing (with or without JavaScript, the card built from the post's current edges) and deleting one's own post
app/routes_tidy.py     rename, move and merge an issue; /changes
app/routes_admin_people.py the back room's People section (/admin/people)
app/routes_email.py    X2: change one's email (/account/email, /email/{link}), only with EMAIL_CHANGE_ENABLED; every earlier address kept with its date
app/routes_evidence.py Phase 2: POST /api/check-evidence (behind EVIDENCE_CHECK_ENABLED; per person and site limits, cached links free); read_link() adds the arXiv full paper read, the PDF with no text, and YouTube captions or a pasted transcript (read afresh, never kept)
app/search.py      the safe keyword query and grouped results
app/tidy.py        who may tidy, tidying copy and change sentences, tidied_names() for reloading the seed
app/extract.py     prompt, model call with one retry, last_model_error, Extraction; re-exports CardPayload and resolution
app/payload.py     card models, cleaning, reference resolution
app/fetch_page.py  Phase 2: reads the page behind an evidence link (public addresses only, checked on every redirect and pinned; 2 MB, HTML or plain text, standard library HTML to text), and the DeepSeek Fetch backup for pages it cannot open (X3); no Cypher
app/fetch_pdf.py   Phase 2 revision round: the text of a PDF (pypdf, in a separate process that sends each page as it reads it, stopped after 25 seconds keeping the pages read, and held to 384 MB on Linux; 15 MB, first 40 pages; date from its own information), arXiv's abstract to paper addresses; no Cypher
app/fetch_video.py Phase 2 revision round: a YouTube video's captions through YouTube's player data (public addresses only, pinned, no redirects, 2 MB and 8 seconds a request), or a transcript the writer pasted (never kept); the quote's time; logs "reader": "youtube" and the outcome; no Cypher
app/check.py       Phase 2: one reading per evidence link (supports, partly, refutes or unclear, with a quote that must be on the page; the claim is judged first, and the writer's supports or refutes is never sent), the writer's own sentence, source facts, suggestions, and the process cache the write path confirms checks against; no Cypher
app/issue_groups.py inclusive issue counts and sorting; no Cypher
app/confidence.py  Phase 2: source confidence on the issue page (Q39's rows to one line per piece of evidence: type, date, age, primary or secondary, agreement, and the disagreement line); no Cypher
app/text.py        normalise(), make_key(), clean_name(), sentences(payload, display_name)
app/templates/     base, enter, sign_in, account, my_statements, forgot, reset, email_change, people, withdraw, accept, link_problem, index, issues, issue, delete_post, merge_confirm, changes, admin, error, asleep; fragments _feed, _post, _about_issue, _record_notice, _stance, _tidy, _admin_people, _confidence (Phase 2)
app/static/        app.css (one anchor per Phase 1 sub-plan); card.js (card, preview, Post), dictation.js (speech input), app.js (page wiring; loads last), about_issue.js (the summary above the write form), stances.js (approve and oppose in place), edit_post.js (opens the card on a post being edited), once.js (submit once guard for forms marked data-once; loaded from base.html); evidence_check.js (Phase 2: reads each evidence link on the card, row by row, says "No source given." with the own experience tick for a row with no link, and holds the transcript box for a video; loads before card.js, only with EVIDENCE_CHECK_ENABLED)
seed/seed.json     the seed record, same shape as the card payload
scripts/__init__.py
scripts/seed.py    python -m scripts.seed [--counts] [--reset --yes [--force]]; reset keeps accounts and refuses a database holding non-seed nodes; reload writes nothing when complete and reads tidied seed issues as they are now
scripts/make_admin.py John's own account, the root of who entered whom: NEO4J_* from the shell only (never .env), prints the database host and name, needs --yes, refuses a database on this machine unless --local, sends nothing; his first link comes from "Forgot your password?"
scripts/cards.py   prints the card the live model produces for each case in tests/extraction_cases.json (needs LLM_API_KEY)
scripts/checks.py  prints the evidence check for each case in tests/check_cases.json, with tokens used (needs LLM_API_KEY)
scripts/probe_reading.py one reading service preflight call; prints capability results, never credentials
scripts/restore.py loads an admin export into an empty database
scripts/smoke.py   read-only checks on the deployed site after each deploy (GET only; the served scripts and style match --ref; OCI_SMOKE_COOKIE adds the signed-in pages)
tests/             offline by default (no network, no database); conftest.py (live_graph, member_app), page_harness.js (the fake page every *.cjs test drives); test_live_*.py are marked live and run only against the disposable Neo4j on port 7688; extraction_cases.json, fixtures/
docs/operators-guide.md   client-facing guide for John
docs/planning/     copies of the planning documents
render.yaml        Render blueprint; SECRET_KEY and ADMIN_TOKEN are generateValue: true
```
