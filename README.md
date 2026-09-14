# Open Collective Intelligence demo

A closed test website where a small group of people write statements about issues they care about and read them in one shared record; version 0.1, built for John Kintree.
Run locally: create a Python 3.12 virtual environment, `pip install -r requirements.txt`, copy `.env.example` to `.env` and fill it in, then `uvicorn app.main:app --reload --port 8000`.
Deploy: push to `main`; Render builds the service described in `render.yaml` and reads its settings from the Environment tab of the dashboard.

The reading service is optional. Without `LLM_API_KEY`, writers can fill the card by hand; the original HTML form also posts plain statements without JavaScript.

Before enabling live reading, set `LLM_API_KEY` in the local environment and deployment dashboard, then run `.venv/bin/python -m scripts.probe_reading`. This makes one provider call and prints capability checks without credentials. Run `.venv/bin/python -m scripts.cards` to review all eleven acceptance cases (including the three variants of case 6), or add `--case 1` for one case. Candidates come from the committed seed fixture; this script never reads or writes a database. Its output needs human assessment and is not a passing test result.

Run `.venv/bin/python -m pytest -q` for the offline suite. It uses mock HTTP transports and database stubs; it never contacts the reading service or a database.

Card models and normalization live in `app/payload.py`, re-exported by `app/extract.py`; the provider call and `last_model_error` remain in `app/extract.py`. Database connection handling is in `app/graph_runtime.py`, issue grouping in `app/issue_groups.py`, and all Cypher remains in `app/graph.py`. The gated `/api/preview` endpoint uses the same resolution and sentence rules as posting, so the preview reflects what is saved.

The unlinked `/admin` back room uses HTTP Basic authentication: any username and `ADMIN_TOKEN` as the password. Every mutation is POST-only and requires a signed form token; reset additionally requires exact `RESET`. Download a copy before a deliberate reset. Per-post deletion removes its CLAIM, SUBMIT, PROPOSE, SUPPORTS and REFUTES relationships, its Post and POSTED link, and touched disconnected non-seed Issue/Solution/Evidence records. Persons, seed records and HAVE_PROPOSED, APPROVE, OPPOSE and PART_OF relationships remain, even if their originating post is deleted.

`/admin/export.json` downloads a versioned `oci-record` JSON file with logical identities, all stored properties, typed temporal values and every relationship (including parallel ones). Run `.venv/bin/python -m scripts.restore export.json` with the destination settings to restore into an empty database. Stop all destination writers first. Invalid input is rejected before connecting; a nonempty destination is refused before data writes; the restore is one transaction. Verify the destination environment before running it. The restore neither clears a database nor runs the reading service. Keep exports private: they include original statements and reading responses. `app/backup.py` validates the format, `app/graph_backup.py` manages its transactions, and `app/graph_posts.py` holds post-write orchestration; all Cypher stays in `app/graph.py`.

Dictation is feature-detected, with continuous/interim results and a second-press stop. The offline suite runs `node --test tests/test_dictation.cjs` when Node is installed; otherwise that wrapper is explicitly skipped. Node is a development-only test tool, not an application dependency. Native Chrome/Edge microphone acceptance and the actual iPhone Safari dictation/autocomplete/keyboard check are still pending. Chrome API detection and 360-pixel browser layout checks are not substitutes for those checks.
