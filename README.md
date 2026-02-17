# agentic-app (uv)

Minimal agentic app with:

- Agent loop and tool-calling flow
- FastAPI API endpoint
- SQLite-backed memory
- In-memory tool rate limiting
- Stub LLM by default, optional Groq-backed LLM when `GROQ_API_KEY` is set

## Prerequisites

- Python `3.10` to `3.12`
- [`uv`](https://docs.astral.sh/uv/)

## Install / compile

Create the virtual environment and install project + dev dependencies:

```bash
uv sync --dev
```

Build a distributable wheel/sdist:

```bash
uv build
```

## Start the app

Development server with reload:

```bash
uv run uvicorn agentic_app.app:app --host 127.0.0.1 --port 8000 --reload
```

Or use the project script entrypoint:

```bash
uv run agentic-app
```

Call the endpoint:

```bash
curl -X POST http://127.0.0.1:8000/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","goal":"Book me a flight from SFO to JFK next week under $500, prefer morning."}'
```

## Run tests and lint

```bash
uv run pytest
uv run ruff check .
```

## Debugging

### VS Code

1. Ensure dependencies are installed with `uv sync --dev`.
2. Select interpreter: `.venv/bin/python` (created by `uv`).
3. Start API in debug mode:

```bash
uv run python -m uvicorn agentic_app.app:app --reload --host 127.0.0.1 --port 8000
```

4. Put breakpoints in files like `src/agentic_app/agent.py` and `src/agentic_app/app.py`.

### PyCharm / IntelliJ

1. Configure project interpreter to `.venv/bin/python`.
2. Add a Run/Debug configuration:
- Module name: `uvicorn`
- Parameters: `agentic_app.app:app --reload --host 127.0.0.1 --port 8000`
- Working directory: project root
3. Start debug and set breakpoints in `src/agentic_app/agent.py`.

## Optional Groq LLM

If `GROQ_API_KEY` is set, `build_agent()` uses `GroqLLM`; otherwise it uses `LLMStub`.

```bash
export GROQ_API_KEY=...
export GROQ_MODEL=llama-3.3-70b-versatile
```
