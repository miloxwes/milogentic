from __future__ import annotations

import json
import os
from datetime import date
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import BadRequestError, OpenAI, RateLimitError


@dataclass(frozen=True)
class LLMToolCall:
    tool_name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    tool_call: Optional[LLMToolCall] = None
    final_text: Optional[str] = None


class GroqLLM:
    """
    Uses Groq's OpenAI-compatible endpoint to:
    - generate normal text, OR
    - request tool calls (function calling)
    """

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key_env: str = "GROQ_API_KEY",
        model_env: str = "GROQ_MODEL",
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} is not set")

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = os.environ.get(model_env, model)

    def decide(
        self,
        user_goal: str,
        memory_events: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        rag_context: str,
    ) -> LLMResponse:
        today_iso = date.today().isoformat()
        available_tool_names = {t["name"] for t in tools}
        preferred_search_tool = (
            "search_flights_amadeus"
            if "search_flights_amadeus" in available_tool_names
            else "search_flights_priceline"
        )

        # Convert our ToolSpec -> OpenAI tools schema
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

        # Keep memory compact (you can improve summarization later)
        history_lines: List[str] = []
        for e in memory_events[-20:]:
            role = e["role"]
            content = e.get("content", "")
            if role == "tool":
                tool_name = (e.get("meta") or {}).get("tool_name")
                history_lines.append(f"[tool:{tool_name}] {content}")
            else:
                history_lines.append(f"[{role}] {content}")

        system = (
            "You are a task agent. If you need external data or actions, call a tool. "
            "Call at most one tool per step. When you are done, respond with a final answer. "
            "Do not invent tool results. "
            f"Today's date is {today_iso}. Never call flight search tools with past dates. "
            f"When searching flights, prefer {preferred_search_tool} when available."
        )

        user = (
            f"Goal:\n{user_goal}\n\n"
            f"RAG context:\n{rag_context}\n\n"
            f"Recent history:\n" + "\n".join(history_lines)
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=openai_tools,
                tool_choice="auto",
                temperature=0.2,
            )
        except BadRequestError as e:
            # Give an actionable hint when Groq retires a model.
            message = str(e)
            if "model_decommissioned" in message or "decommissioned" in message.lower():
                raise RuntimeError(
                    f"Groq model '{self.model}' is decommissioned. "
                    "Set GROQ_MODEL to an active model from "
                    "https://console.groq.com/docs/deprecations."
                ) from e
            raise
        except RateLimitError as e:
            raise RuntimeError(
                "Groq API rate limit reached. Wait and retry, or reduce request frequency/token usage."
            ) from e

        msg = resp.choices[0].message

        # Tool call path
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            tc = tool_calls[0]
            fn = tc.function
            args = json.loads(fn.arguments) if fn.arguments else {}
            return LLMResponse(tool_call=LLMToolCall(tool_name=fn.name, arguments=args))

        # Final text path
        content = msg.content or ""
        return LLMResponse(final_text=content.strip())
