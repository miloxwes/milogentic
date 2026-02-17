# agentic-app (uv)

Minimal agentic app with:

- Agent loop and tool-calling flow
- FastAPI API endpoint
- Separated frontend UI (HTML/CSS/JS static assets)
- SQLite-backed memory
- In-memory tool rate limiting
- Stub LLM by default, optional Groq-backed LLM when `GROQ_API_KEY` is set

## Project structure

Backend:

- `src/agentic_app/app.py` (FastAPI routes + static serving)
- `src/agentic_app/agent.py` (agent loop, LLM orchestration, tool execution)
- `src/agentic_app/tools.py` (tool specs + implementations)

Frontend:

- `src/agentic_app/web/index.html`
- `src/agentic_app/web/static/styles.css`
- `src/agentic_app/web/static/app.js`

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

Open the UI in your browser:

```text
http://127.0.0.1:8000/
```

UI includes:

- Request form (`session_id`, `goal`)
- Agent state diagram (submitted -> pickup -> rag/memory -> llm call -> llm result -> tool execution -> final)
- Tool catalog (from prompt tool specs)
- LLM prompt/result trace (expandable JSON tree)
- Full execution steps (expandable JSON tree)

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

## API notes

`POST /agent/run` returns:

- `session_id`
- `final_text`
- `steps` (includes `llm_prompt`, `llm_result`, tool outcomes, and final/error events)

## Optional Groq LLM

If `GROQ_API_KEY` is set, `build_agent()` uses `GroqLLM`; otherwise it uses `LLMStub`.

```bash
export GROQ_API_KEY=...
export GROQ_MODEL=llama-3.3-70b-versatile
```
