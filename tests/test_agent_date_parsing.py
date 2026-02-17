from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from agentic_app.agent import Agent
from agentic_app.memory import MemoryStore
from agentic_app.rate_limit import InMemoryRateLimiter
from agentic_app.tools import Tool


@dataclass(frozen=True)
class _ToolCall:
    tool_name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class _LLMResponse:
    tool_call: Optional[_ToolCall] = None
    final_text: Optional[str] = None


class _OneToolThenFinalLLM:
    def __init__(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._calls = 0

    def decide(
        self,
        user_goal: str,
        memory_events: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        rag_context: str,
    ) -> _LLMResponse:
        self._calls += 1
        if self._calls == 1:
            return _LLMResponse(tool_call=_ToolCall(tool_name=self._tool_name, arguments=self._tool_args))
        return _LLMResponse(final_text="done")


def test_agent_accepts_iso_datetime_return_date(tmp_path):
    db_path = tmp_path / "memory.db"
    captured: Dict[str, Any] = {}

    def fake_search(args: Dict[str, Any]) -> Dict[str, Any]:
        captured.update(args)
        return {"options": []}

    depart = (date.today() + timedelta(days=7)).isoformat()
    llm = _OneToolThenFinalLLM(
        tool_name="search_flights_amadeus",
        tool_args={
            "origin": "SFO",
            "destination": "JFK",
            "depart_date": depart,
            "return_date": "2030-04-14T00:00:00Z",
        },
    )
    tools = [
        Tool(
            name="search_flights_amadeus",
            description="test",
            parameters_schema={"type": "object", "properties": {}},
            handler=fake_search,
        )
    ]
    agent = Agent(
        memory=MemoryStore(db_path=str(db_path)),
        llm=llm,  # type: ignore[arg-type]
        tools=tools,
        rate_limiter=InMemoryRateLimiter(),
    )

    res = agent.run("s1", "test goal")

    assert res.final_text == "done"
    assert captured["return_date"] == "2030-04-14"


def test_agent_drops_invalid_return_date_instead_of_blocking(tmp_path):
    db_path = tmp_path / "memory.db"
    captured: Dict[str, Any] = {}

    def fake_search(args: Dict[str, Any]) -> Dict[str, Any]:
        captured.update(args)
        return {"options": []}

    depart = (date.today() + timedelta(days=7)).isoformat()
    llm = _OneToolThenFinalLLM(
        tool_name="search_flights_amadeus",
        tool_args={
            "origin": "SFO",
            "destination": "JFK",
            "depart_date": depart,
            "return_date": "next friday",
        },
    )
    tools = [
        Tool(
            name="search_flights_amadeus",
            description="test",
            parameters_schema={"type": "object", "properties": {}},
            handler=fake_search,
        )
    ]
    agent = Agent(
        memory=MemoryStore(db_path=str(db_path)),
        llm=llm,  # type: ignore[arg-type]
        tools=tools,
        rate_limiter=InMemoryRateLimiter(),
    )

    res = agent.run("s1", "test goal")

    assert res.final_text == "done"
    assert "return_date" not in captured


class _FailingLLM:
    def __init__(self, message: str = "provider throttled") -> None:
        self._message = message

    def decide(
        self,
        user_goal: str,
        memory_events: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        rag_context: str,
    ) -> _LLMResponse:
        raise RuntimeError(self._message)


def test_agent_handles_llm_errors_without_crashing(tmp_path):
    db_path = tmp_path / "memory.db"
    agent = Agent(
        memory=MemoryStore(db_path=str(db_path)),
        llm=_FailingLLM(),  # type: ignore[arg-type]
        tools=[],
        rate_limiter=InMemoryRateLimiter(),
    )

    res = agent.run("s1", "test goal")

    assert "LLM decision failed" in res.final_text
    assert any(step.get("type") == "llm_error" for step in res.steps)


class _FallbackLLM:
    def decide(
        self,
        user_goal: str,
        memory_events: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        rag_context: str,
    ) -> _LLMResponse:
        return _LLMResponse(final_text="fallback ok")


def test_agent_falls_back_on_llm_rate_limit(tmp_path):
    db_path = tmp_path / "memory.db"
    agent = Agent(
        memory=MemoryStore(db_path=str(db_path)),
        llm=_FailingLLM(message="Groq API rate limit reached"),
        tools=[],
        rate_limiter=InMemoryRateLimiter(),
        fallback_llm=_FallbackLLM(),  # type: ignore[arg-type]
    )

    res = agent.run("s1", "test goal")

    assert res.final_text == "fallback ok"
    assert any(step.get("type") == "llm_fallback" for step in res.steps)
