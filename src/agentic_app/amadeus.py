from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class _TokenCache:
    access_token: str
    expires_at_epoch: float


class AmadeusClient:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("AMADEUS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("AMADEUS_CLIENT_SECRET")
        self.base_url = (base_url or os.environ.get("AMADEUS_BASE_URL") or "https://test.api.amadeus.com").rstrip("/")
        self.session = session or requests.Session()
        self._token: Optional[_TokenCache] = None

        if not self.client_id or not self.client_secret:
            raise RuntimeError("AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET must be set for Amadeus API calls.")

    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token.expires_at_epoch - 15:
            return self._token.access_token

        resp = self.session.post(
            f"{self.base_url}/v1/security/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not access_token or expires_in <= 0:
            raise RuntimeError("Failed to obtain Amadeus access token.")

        self._token = _TokenCache(access_token=access_token, expires_at_epoch=now + expires_in)
        return access_token

    def search_flights(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        max_results: int = 10,
        non_stop: Optional[bool] = None,
        currency_code: str = "USD",
    ) -> Dict[str, Any]:
        token = self._ensure_token()

        params: Dict[str, Any] = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": depart_date,
            "adults": adults,
            "max": max_results,
            "currencyCode": currency_code,
        }
        if return_date:
            params["returnDate"] = return_date
        if non_stop is not None:
            params["nonStop"] = str(non_stop).lower()

        resp = self.session.get(
            f"{self.base_url}/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        offers = payload.get("data", [])

        options: List[Dict[str, Any]] = []
        for offer in offers:
            itineraries = offer.get("itineraries", [])
            first_itinerary = itineraries[0] if itineraries else {}
            segments = first_itinerary.get("segments", [])
            first_segment = segments[0] if segments else {}
            last_segment = segments[-1] if segments else {}

            option = {
                "option_id": offer.get("id", ""),
                "provider": "amadeus",
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date,
                "return_date": return_date,
                "price_usd": float((offer.get("price") or {}).get("total", 0.0)),
                "stops": max(0, len(segments) - 1),
                "duration": first_itinerary.get("duration"),
                "departure_at": first_segment.get("departure", {}).get("at"),
                "arrival_at": last_segment.get("arrival", {}).get("at"),
                "carrier": (first_segment.get("carrierCode") or ""),
            }
            options.append(option)

        return {"options": options, "raw_offers_count": len(offers)}
