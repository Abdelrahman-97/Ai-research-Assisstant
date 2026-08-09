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
  main.py              FastAPI entrypoint
  config.py            Settings (pydantic-settings, reads .env)
  api/routes/          HTTP routes (health, ...)
  models/schemas.py    Pipeline data models
  services/
    integrity_checker.py   Validate uploaded data files
    claude_client.py       LLM wrapper (propose test, write Results)
    stats_executor.py      Generate + run analysis scripts
    report_writer.py       Markdown -> .docx export
  sandbox/
    docker_runner.py       Isolated script execution
docker/
  Dockerfile.sandbox   Python + R execution image
tests/                 Smoke tests
```

Service files are documented **stubs** (signatures + docstrings). Implement them file by file, reviewing each before moving on.

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
