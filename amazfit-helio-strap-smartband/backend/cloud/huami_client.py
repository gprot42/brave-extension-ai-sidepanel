"""Huami/Zepp cloud API client.

Uses the internal app API (same as Zepp app) with apptoken authentication.
Login is a 2-step process: get access token → exchange for apptoken.
Data fetched via band_data.json (sleep, activity, HR) and /events (SpO2, stress).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

# Regional base URLs
REGION_URLS = {
    "eu-central-1": {
        "user": "https://api-user.huami.com",
        "login": "https://account.huami.com",
        "data": "https://api-mifit-de2.huami.com",
        "events": "https://api-mifit-de2.zepp.com",
    },
    "us-west-2": {
        "user": "https://api-user.huami.com",
        "login": "https://account.huami.com",
        "data": "https://api-mifit.huami.com",
        "events": "https://api-mifit.zepp.com",
    },
    "cn": {
        "user": "https://api-user.huami.com",
        "login": "https://account.huami.com",
        "data": "https://api-mifit.huami.com",
        "events": "https://api-mifit.zepp.com",
    },
}

REDIRECT_URI = "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"


class HuamiClient:
    """Async client for the Huami/Zepp cloud API."""

    def __init__(self, region: str = "eu-central-1"):
        self.region = region
        urls = REGION_URLS.get(region, REGION_URLS["eu-central-1"])
        self._user_url = urls["user"]
        self._login_url = urls["login"]
        self._data_url = urls["data"]
        self._events_url = urls["events"]
        self.apptoken: str = ""
        self.userid: str = ""
        self._http = httpx.AsyncClient(timeout=30.0, follow_redirects=False)

    async def close(self):
        await self._http.aclose()

    @property
    def is_logged_in(self) -> bool:
        return bool(self.apptoken and self.userid)

    def set_credentials(self, apptoken: str, userid: str):
        """Set pre-existing credentials (from .env)."""
        self.apptoken = apptoken
        self.userid = userid

    # ── Login (2-step) ─────────────────────────────────────

    async def login(self, email: str, password: str) -> tuple[str, str]:
        """Login and return (apptoken, userid).

        Step 1: POST credentials → get access token from redirect URL
        Step 2: Exchange access token for apptoken + userid
        """
        # Step 1: Get access token
        logger.info("Cloud login step 1: getting access token...")
        resp = await self._http.post(
            f"{self._user_url}/registrations/{email}/tokens",
            data={
                "state": "REDIRECTION",
                "client_id": "HuaMi",
                "redirect_uri": REDIRECT_URI,
                "token": "access",
                "password": password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Follow redirect chain to get access token
        access_token = None
        if resp.status_code in (301, 302, 303):
            location = resp.headers.get("location", "")
            parsed = urlparse(location)
            params = parse_qs(parsed.query)
            if params.get("error"):
                raise ValueError(f"Login failed — check email and password (error {params['error'][0]})")
            access_token = params.get("access", [None])[0]

        if not access_token and resp.status_code == 429:
            raise ValueError("Rate limited by Huami API — please wait a few minutes and try again")

        if not access_token:
            # Try regional and alternate Zepp endpoints
            alt_urls = [
                f"https://api-user-de2.huami.com/registrations/{email}/tokens",
                f"https://api-user.zepp.com/registrations/{email}/tokens",
            ]
            for alt_url in alt_urls:
                logger.info("Trying alternate endpoint: %s", alt_url)
                resp = await self._http.post(
                    alt_url,
                    data={
                        "state": "REDIRECTION",
                        "client_id": "HuaMi",
                        "redirect_uri": REDIRECT_URI,
                        "token": "access",
                        "password": password,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code == 429:
                    raise ValueError("Rate limited by Huami API — please wait a few minutes and try again")
                if resp.status_code in (301, 302, 303):
                    location = resp.headers.get("location", "")
                    parsed = urlparse(location)
                    params = parse_qs(parsed.query)
                    access_token = params.get("access", [None])[0]
                    if access_token:
                        break

        if not access_token:
            raise ValueError(f"Failed to get access token (status {resp.status_code}, body: {resp.text[:200]})")

        logger.info("Cloud login step 1: got access token")

        # Step 2: Exchange for apptoken
        logger.info("Cloud login step 2: exchanging for apptoken...")
        resp = await self._http.post(
            f"{self._login_url}/v2/client/login",
            data={
                "app_name": "com.xiaomi.hm.health",
                "dn": (
                    "account.huami.com,api-user.huami.com,"
                    "api-mifit.huami.com,api-mifit-de2.huami.com,"
                    "api-mifit-de2.zepp.com,api-mifit.zepp.com"
                ),
                "device_id": "02:00:00:00:00:00",
                "device_model": "android_phone",
                "app_version": "4.0.9",
                "allow_registration": "false",
                "third_name": "huami",
                "grant_type": "access_token",
                "country_code": "GB",
                "code": access_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        body = resp.json()
        token_info = body.get("token_info", {})
        self.apptoken = token_info.get("app_token", "")
        self.userid = token_info.get("user_id", "")

        if not self.apptoken:
            raise ValueError(f"Failed to get apptoken: {body}")

        logger.info("Cloud login successful: userid=%s", self.userid)
        return self.apptoken, self.userid

    # ── Data Fetching ──────────────────────────────────────

    def _headers(self) -> dict:
        return {"apptoken": self.apptoken}

    async def fetch_band_data(
        self, from_date: date, to_date: date, query_type: str = "summary"
    ) -> dict:
        """Fetch band_data.json — the main data endpoint.

        query_type="summary" → sleep + activity
        query_type="detail"  → adds HR binary blob
        """
        if not self.is_logged_in:
            raise RuntimeError("Not logged in")

        resp = await self._http.get(
            f"{self._data_url}/v1/data/band_data.json",
            params={
                "query_type": query_type,
                "device_type": "android_phone",
                "userid": self.userid,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def fetch_events(
        self,
        event_type: str,
        from_date: date,
        to_date: date,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch events (SpO2, stress, PAI) from the events endpoint."""
        if not self.is_logged_in:
            raise RuntimeError("Not logged in")

        from_ms = int(
            (from_date - date(1970, 1, 1)).total_seconds() * 1000
        )
        to_ms = int(
            ((to_date + timedelta(days=1)) - date(1970, 1, 1)).total_seconds() * 1000
        )

        # Try regional events endpoint, fall back to global
        for base in [self._events_url, "https://api-mifit.zepp.com"]:
            try:
                resp = await self._http.get(
                    f"{base}/users/{self.userid}/events",
                    params={
                        "from": str(from_ms),
                        "to": str(to_ms),
                        "eventType": event_type,
                        "limit": str(limit),
                        "timeZone": "Europe/London",
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("items", [])
            except Exception as e:
                logger.debug("Events endpoint %s failed: %s", base, e)
                continue

        return []

    # ── Convenience methods ────────────────────────────────

    async def fetch_sleep_and_activity(
        self, from_date: date, to_date: date
    ) -> dict:
        """Fetch summary data (sleep + activity) for a date range."""
        return await self.fetch_band_data(from_date, to_date, "summary")

    async def fetch_spo2(self, from_date: date, to_date: date) -> list[dict]:
        """Fetch SpO2 events."""
        return await self.fetch_events("blood_oxygen", from_date, to_date)

    async def fetch_stress(self, from_date: date, to_date: date) -> list[dict]:
        """Fetch stress events."""
        return await self.fetch_events("stress", from_date, to_date)


# Module-level singleton
client = HuamiClient()
