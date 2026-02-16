# agentic-app (Poetry)

A minimal, production-shaped agentic application:

- **Agent** loop (your code)
- **LLM** stub (deterministic local behavior; swap with real LLM later)
- **Tools** with schemas + rate limits
- **Memory** persisted in SQLite
- **FastAPI** endpoint

## Quick start

```bash
poetry install
poetry run uvicorn agentic_app.app:app --reload
```

Run:

```bash
curl -X POST http://127.0.0.1:8000/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","goal":"Book me a flight from SFO to JFK next week under $500, prefer morning."}'
```

You should see the agent:
1) checks calendar
2) searches flights
3) places a hold
4) asks for approval (does not auto-purchase)

## Using Groq

If `GROQ_API_KEY` is set, the app uses Groq instead of the local stub.

```bash
export GROQ_API_KEY=...
export GROQ_MODEL=llama-3.3-70b-versatile
```

If a model is retired, set `GROQ_MODEL` to an active one listed in Groq deprecations docs.

## Next steps

- Replace `LLMStub` with an LLM client that supports tool calling.
- Replace mock tools with real provider APIs.
- Replace `_rag_retrieve` with a vector DB retriever.
- Add Temporal for durability (optional).
