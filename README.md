# AI Research Assistant

Statistical analysis and Results-section writing assistant for researchers.

**Core principle:** the AI *proposes* against citable methodology; a human confirms every judgment call; nothing is treated as fact until the sandbox or a human has verified it.

## Pipeline

1. User uploads a data file and research protocol
2. AI proposes a statistical test with reasoning
3. **Mandatory human checkpoint** — user confirms or overrides the test
4. Script is generated and shown for **mandatory preview**
5. Sandboxed, non-AI Docker environment runs the Python or R script
6. Artifacts (tables, figures, raw output) are collected
7. AI writes a Results section grounded strictly in those artifacts
8. Export to Word (`.docx`); the AI works in Markdown throughout, converting at export

Python and R are both supported from v1.

## Project layout

```
app/
  main.py              FastAPI entrypoint (wires all routers)
  config.py            Settings (pydantic-settings, reads .env)
  api/
    deps.py            Auth + paid-access dependencies
    routes/
      health.py        Health check
      auth.py          Sign up / sign in (JWT)
      payments.py      EasyKash link + success webhook
      runs.py          Pipeline: upload, plan, approve, script, execute, results, download
  models/schemas.py    All data models (users, payments, run state machine)
  store/repository.py  In-memory store (DROP-IN replaceable by a real DB)
  services/
    llm_client.py          Kimi (Moonshot) client — chat / chat_json / ping
    integrity_checker.py   Validate + summarize uploaded data
    planner.py             Kimi proposes the statistical plan
    stats_executor.py      Kimi writes the script; runs it via the sandbox
    results_writer.py      Kimi verifies output + writes the Results section
    report_writer.py       Markdown -> .docx export
    security.py            Password hashing + JWT
    payments.py            EasyKash integration
    orchestrator.py        The run state machine (enforces the human checkpoint)
  sandbox/
    docker_runner.py       Isolated script execution (Docker; dev subprocess fallback)
docker/
  Dockerfile.sandbox   Python + R execution image
tests/                 Integrity, auth+payment, and full end-to-end pipeline tests
```

The pipeline is fully implemented and tested end-to-end. Two deliberate stand-ins
to finish before production: the **in-memory store** (`store/repository.py`) should
be replaced by a real database, and the **EasyKash** request/response field names
and signature scheme in `services/payments.py` should be confirmed against their
current merchant docs.

## API flow

```
POST /auth/signup            (email, password, scope: thesis|studies)
POST /auth/login             -> JWT
POST /payments/link          -> EasyKash payment URL
POST /payments/callback      (EasyKash webhook) -> unlocks access
POST /runs                   -> run_id
POST /runs/{id}/upload       (protocol text + data file)
POST /runs/{id}/plan         -> AI proposes plan (status: awaiting_approval)
POST /runs/{id}/approve      -> HUMAN CHECKPOINT (confirm or edit)
POST /runs/{id}/script       -> AI writes script (preview)
POST /runs/{id}/execute      -> sandbox runs it
POST /runs/{id}/results      -> AI verifies + writes Results, exports .docx
GET  /runs/{id}/download     -> the .docx
```

## Getting started

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # then fill in ANTHROPIC_API_KEY etc.

uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the API docs, or hit http://127.0.0.1:8000/health.

Run tests:

```bash
pytest
```

Build the sandbox image (needed once script execution is implemented):

```bash
docker build -f docker/Dockerfile.sandbox -t research-assistant-sandbox:latest .
```

## Status

v0.1.0 — project skeleton. App boots, `/health` and `/` respond, tests pass. Pipeline services are stubbed and ready to be built out.
