from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TypedDict

from agentic_app.amadeus import AmadeusClient
from agentic_app.rate_limit import RateLimit


class ToolSpec(TypedDict):
    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    rate_limit: Optional[RateLimit] = None
    approx_cost_usd: float = 0.0


def tool_spec(tool: Tool) -> ToolSpec:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters_schema,
    }


# -----------------------
# Mock tool implementations
# -----------------------

def search_flights_priceline(args: Dict[str, Any]) -> Dict[str, Any]:
    # Replace with real Priceline API call later.
    origin = args["origin"]
    dest = args["destination"]
    depart_date = args["depart_date"]
    return_date = args.get("return_date")
    max_price = args.get("max_price_usd", 9999)

    options = [
        {
            "option_id": "PL-101",
            "provider": "priceline",
            "origin": origin,
            "destination": dest,
            "depart_date": depart_date,
            "return_date": return_date,
            "price_usd": 420,
            "stops": 0,
            "duration_minutes": 330,
        },
        {
            "option_id": "PL-102",
            "provider": "priceline",
            "origin": origin,
            "destination": dest,
            "depart_date": depart_date,
            "return_date": return_date,
            "price_usd": 310,
            "stops": 1,
            "duration_minutes": 510,
        },
        {
            "option_id": "PL-103",
            "provider": "priceline",
            "origin": origin,
            "destination": dest,
            "depart_date": depart_date,
            "return_date": return_date,
            "price_usd": 610,
            "stops": 0,
            "duration_minutes": 325,
        },
    ]
    options = [o for o in options if o["price_usd"] <= max_price]
    return {"options": options}


def search_flights_amadeus(args: Dict[str, Any]) -> Dict[str, Any]:
    client = AmadeusClient()
    result = client.search_flights(
        origin=args["origin"],
        destination=args["destination"],
        depart_date=args["depart_date"],
        return_date=args.get("return_date"),
        adults=int(args.get("adults", 1)),
        max_results=int(args.get("max_results", 10)),
        non_stop=args.get("non_stop"),
        currency_code=args.get("currency_code", "USD"),
    )
    max_price = args.get("max_price_usd")
    if max_price is not None:
        result["options"] = [o for o in result["options"] if o.get("price_usd", 0) <= max_price]
    return result


def check_calendar_freebusy(args: Dict[str, Any]) -> Dict[str, Any]:
    # Replace with Google Calendar later.
    return {
        "free_windows": [
            {"start": "2026-02-24T09:00:00-08:00", "end": "2026-02-24T18:00:00-08:00"},
            {"start": "2026-02-26T08:00:00-08:00", "end": "2026-02-26T18:00:00-08:00"},
        ]
    }


def hold_booking(args: Dict[str, Any]) -> Dict[str, Any]:
    option_id = args["option_id"]
    return {"hold_id": f"HOLD-{option_id}", "expires_in_minutes": 15}


def confirm_booking(args: Dict[str, Any]) -> Dict[str, Any]:
    hold_id = args["hold_id"]
    return {"confirmation_id": f"CONF-{hold_id}", "status": "confirmed"}


def build_tools() -> List[Tool]:
    return [
        Tool(
            name="calendar_freebusy",
            description="Get user's free time windows for a date range.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
            handler=check_calendar_freebusy,
            rate_limit=RateLimit(max_calls=10, window_seconds=60),
        ),
        Tool(
            name="search_flights_amadeus",
            description=(
                "Search live flight offers using the Amadeus API. "
                "Requires AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Airport code, e.g. SFO"},
                    "destination": {"type": "string", "description": "Airport code, e.g. JFK"},
                    "depart_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "return_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "adults": {"type": "integer", "description": "Adult passengers count (default 1)"},
                    "max_results": {"type": "integer", "description": "Maximum offers to return (default 10)"},
                    "non_stop": {"type": "boolean", "description": "If true, only nonstop flights"},
                    "currency_code": {"type": "string", "description": "Fare currency, default USD"},
                    "max_price_usd": {"type": "integer", "description": "Optional local post-filter on USD fares"},
                },
                "required": ["origin", "destination", "depart_date"],
            },
            handler=search_flights_amadeus,
            rate_limit=RateLimit(max_calls=5, window_seconds=60),
            approx_cost_usd=0.01,
        ),
        Tool(
            name="search_flights_priceline",
            description="Search flights using a Priceline-like provider.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Airport code, e.g. SFO"},
                    "destination": {"type": "string", "description": "Airport code, e.g. JFK"},
                    "depart_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "return_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "max_price_usd": {"type": "integer", "description": "Maximum price in USD"},
                },
                "required": ["origin", "destination", "depart_date"],
            },
            handler=search_flights_priceline,
            rate_limit=RateLimit(max_calls=5, window_seconds=60),
            approx_cost_usd=0.01,
        ),
        Tool(
            name="hold_booking",
            description="Place a temporary hold on a selected flight option.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "option_id": {"type": "string", "description": "Option ID from search results"},
                },
                "required": ["option_id"],
            },
            handler=hold_booking,
            rate_limit=RateLimit(max_calls=10, window_seconds=60),
        ),
        Tool(
            name="confirm_booking",
            description="Confirm a booking using a hold id. Requires explicit user approval.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "hold_id": {"type": "string", "description": "Hold ID returned from hold_booking"},
                    "user_approved": {"type": "boolean", "description": "Must be true to proceed"},
                },
                "required": ["hold_id", "user_approved"],
            },
            handler=confirm_booking,
            rate_limit=RateLimit(max_calls=5, window_seconds=60),
        ),
    ]
