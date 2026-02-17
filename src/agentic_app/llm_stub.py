from __future__ import annotations

import os

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class LLMToolCall:
    tool_name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    tool_call: Optional[LLMToolCall] = None
    final_text: Optional[str] = None


class LLMStub:
    """
    Deterministic "LLM" for demo. Replace with real LLM client later.
    """

    def decide(
        self,
        user_goal: str,
        memory_events: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        rag_context: str,
    ) -> LLMResponse:
        # Very simple state machine based on what is already in memory.
        available_tool_names = {t["name"] for t in tools}

        has_amadeus_creds = bool(os.environ.get("AMADEUS_CLIENT_ID") and os.environ.get("AMADEUS_CLIENT_SECRET"))
        search_tool_name = "search_flights_priceline"
        if "search_flights_amadeus" in available_tool_names and has_amadeus_creds:
            search_tool_name = "search_flights_amadeus"

        def has_tool(tool_name: str) -> bool:
            return any(
                e.get("meta", {}).get("tool_name") == tool_name
                for e in memory_events
                if e["role"] == "tool"
            )

        if not has_tool("calendar_freebusy"):
            return LLMResponse(
                tool_call=LLMToolCall(
                    tool_name="calendar_freebusy",
                    arguments={"start_date": "2026-02-23", "end_date": "2026-03-01"},
                )
            )

        if not has_tool(search_tool_name):
            return LLMResponse(
                tool_call=LLMToolCall(
                    tool_name=search_tool_name,
                    arguments={
                        "origin": "SFO",
                        "destination": "JFK",
                        "depart_date": "2026-02-24",
                        "return_date": "2026-02-27",
                        "max_price_usd": 500,
                    },
                )
            )

        if not has_tool("hold_booking"):
            last_search = None
            for e in reversed(memory_events):
                if e.get("meta", {}).get("tool_name") == search_tool_name:
                    last_search = e.get("meta", {}).get("tool_result")
                    break
            options = (last_search or {}).get("options", [])
            if not options:
                return LLMResponse(
                    final_text="No flights found under your price cap. Want to increase max price or change dates?"
                )
            cheapest = sorted(options, key=lambda x: x["price_usd"])[0]
            return LLMResponse(
                tool_call=LLMToolCall(
                    tool_name="hold_booking",
                    arguments={"option_id": cheapest["option_id"]},
                )
            )

        return LLMResponse(
            final_text=(
                "I found a flight and placed a 15-minute hold. "
                "Reply with 'approve' to confirm booking, or 'cancel' to stop."
            )
        )
