# Open Collective Intelligence demo

A closed test website where a small group of people write statements about issues they care about and read them in one shared record; version 0.1, built for John Kintree.
Run locally: create a Python 3.12 virtual environment, `pip install -r requirements.txt`, copy `.env.example` to `.env` and fill it in, then `uvicorn app.main:app --reload --port 8000`.
Deploy: push to `main`; Render builds the service described in `render.yaml` and reads its settings from the Environment tab of the dashboard.
