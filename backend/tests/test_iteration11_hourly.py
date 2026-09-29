"""Iteration 11 backend tests — GET /api/weather/hourly.

Covers:
- Happy path shape/values
- hours param respected (hours=6 -> up to 6 points)
- Upper clamp (hours=99 -> up to 24)
- Lower clamp (hours=0 -> at least 1)
- Auth required
- Light regression: /weather, /geocode, /reports/{id}/tts (openai)
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://project-digest-7.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"

BOSTON_LAT, BOSTON_LON = 42.358, -71.060
HOUR_LABEL_RE = re.compile(r"^\d{2}:\d{2}$")


class State:
    admin_token: str = ""
    seed_report_id: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _assert_point_shape(p):
    # hour_label
    hl = p.get("hour_label")
    assert isinstance(hl, str) and HOUR_LABEL_RE.match(hl), \
        f"hour_label must match HH:MM, got {hl!r}"
    # temperature_f
    assert isinstance(p.get("temperature_f"), (int, float)), \
        f"temperature_f must be number, got {p.get('temperature_f')!r}"
    # precip_prob — number in [0, 100] or None
    pp = p.get("precip_prob")
    if pp is not None:
        assert isinstance(pp, (int, float)), f"precip_prob must be number/None, got {pp!r}"
        assert 0 <= pp <= 100, f"precip_prob out of [0,100]: {pp!r}"
    # precipitation
    assert isinstance(p.get("precipitation"), (int, float)), \
        f"precipitation must be number, got {p.get('precipitation')!r}"
    # conditions
    conds = p.get("conditions")
    assert isinstance(conds, str) and conds, f"conditions non-empty str, got {conds!r}"
    # weather_code
    assert isinstance(p.get("weather_code"), int), \
        f"weather_code must be int, got {p.get('weather_code')!r}"
    # wind_mph
    assert isinstance(p.get("wind_mph"), (int, float)), \
        f"wind_mph must be number, got {p.get('wind_mph')!r}"


# ---------- Prep ----------
class TestPrep:
    def test_login_admin(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=15)
        assert r.status_code == 200, r.text
        state.admin_token = r.json()["access_token"]


# ---------- 1) Happy Path ----------
class TestHourlyHappyPath:
    def test_hourly_default(self, state):
        r = requests.get(f"{API}/weather/hourly", headers=_hdr(state.admin_token),
                         params={"lat": BOSTON_LAT, "lon": BOSTON_LON}, timeout=30)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable")
        d = r.json()

        # echo lat/lon
        assert d.get("latitude") == BOSTON_LAT, f"latitude echo mismatch: {d.get('latitude')!r}"
        assert d.get("longitude") == BOSTON_LON, f"longitude echo mismatch: {d.get('longitude')!r}"

        # hours int
        assert isinstance(d.get("hours"), int), f"hours must be int, got {d.get('hours')!r}"

        # utc_offset_seconds int
        assert isinstance(d.get("utc_offset_seconds"), int), \
            f"utc_offset_seconds must be int, got {d.get('utc_offset_seconds')!r}"

        # fetched_at non-empty ISO string
        fa = d.get("fetched_at")
        assert isinstance(fa, str) and fa, f"fetched_at must be non-empty str, got {fa!r}"

        # points array 1..12
        points = d.get("points")
        assert isinstance(points, list), f"points must be list, got {type(points).__name__}"
        assert 1 <= len(points) <= 12, f"points length must be 1..12, got {len(points)}"

        for i, p in enumerate(points):
            try:
                _assert_point_shape(p)
            except AssertionError as e:
                raise AssertionError(f"point[{i}] shape invalid: {e}") from e

        # hours field should equal len(points)
        assert d["hours"] == len(points), \
            f"hours ({d['hours']}) must equal len(points) ({len(points)})"


# ---------- 2) hours param respected ----------
class TestHoursParam:
    def test_hours_6(self, state):
        # ensure we still have token (fixture is module-scoped; run serial)
        assert state.admin_token, "prep must login first"
        r = requests.get(f"{API}/weather/hourly", headers=_hdr(state.admin_token),
                         params={"lat": BOSTON_LAT, "lon": BOSTON_LON, "hours": 6}, timeout=30)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable")
        d = r.json()
        assert d.get("hours") is not None and d["hours"] <= 6, \
            f"hours field must be <=6, got {d.get('hours')!r}"
        points = d.get("points") or []
        assert len(points) <= 6, f"points length must be <=6, got {len(points)}"
        assert len(points) >= 1, "expected at least 1 point"


# ---------- 3) hours upper clamp ----------
class TestHoursClampUpper:
    def test_hours_99_clamped_to_24(self, state):
        assert state.admin_token
        r = requests.get(f"{API}/weather/hourly", headers=_hdr(state.admin_token),
                         params={"lat": BOSTON_LAT, "lon": BOSTON_LON, "hours": 99}, timeout=30)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable")
        d = r.json()
        assert d.get("hours") is not None and d["hours"] <= 24, \
            f"hours field must be <=24 (clamped), got {d.get('hours')!r}"
        points = d.get("points") or []
        assert len(points) <= 24, f"points length must be <=24, got {len(points)}"


# ---------- 4) hours lower clamp ----------
class TestHoursClampLower:
    def test_hours_0_clamped_to_min_1(self, state):
        assert state.admin_token
        r = requests.get(f"{API}/weather/hourly", headers=_hdr(state.admin_token),
                         params={"lat": BOSTON_LAT, "lon": BOSTON_LON, "hours": 0}, timeout=30)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable")
        d = r.json()
        points = d.get("points") or []
        assert len(points) >= 1, \
            f"backend must enforce max(1, ...) -> at least 1 point, got {len(points)}"
        assert d.get("hours") is not None and d["hours"] >= 1, \
            f"hours field must be >=1, got {d.get('hours')!r}"


# ---------- 5) Auth required ----------
class TestAuthRequired:
    def test_hourly_requires_auth(self):
        r = requests.get(f"{API}/weather/hourly",
                         params={"lat": BOSTON_LAT, "lon": BOSTON_LON}, timeout=15)
        assert r.status_code in (401, 403), r.text


# ---------- 6) Light regression ----------
class TestRegression:
    def test_login_for_regression(self, state):
        # Re-login here to be robust if xdist splits classes across workers
        if not state.admin_token:
            r = requests.post(f"{API}/auth/login",
                              json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                              timeout=15)
            assert r.status_code == 200, r.text
            state.admin_token = r.json()["access_token"]

    def test_weather_current_ok(self, state):
        r = requests.get(f"{API}/weather", headers=_hdr(state.admin_token),
                         params={"lat": BOSTON_LAT, "lon": BOSTON_LON}, timeout=30)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable")
        d = r.json()
        for k in ("latitude", "longitude", "temperature_f", "wind_mph",
                  "precipitation", "weather_code", "conditions", "fetched_at"):
            assert k in d, f"/weather missing key {k}"

    def test_geocode_boston_ok(self, state):
        r = requests.get(f"{API}/geocode", headers=_hdr(state.admin_token),
                         params={"q": "Boston"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results")
        assert isinstance(results, list) and len(results) >= 1, \
            f"expected at least 1 geocode result, got {results!r}"
        item = results[0]
        assert isinstance(item.get("label"), str) and item["label"]
        assert isinstance(item.get("latitude"), (int, float))
        assert isinstance(item.get("longitude"), (int, float))

    def test_report_tts_openai(self, state):
        # Create a minimal report to TTS
        rc = requests.post(f"{API}/reports", headers=_hdr(state.admin_token), json={
            "highlights": "TEST iter11 regression tts.",
            "delays": "",
            "change_orders": "",
            "material_notes": "",
            "include_weather": False,
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert rc.status_code == 200, rc.text
        rid = rc.json()["id"]
        state.seed_report_id = rid

        r = requests.post(f"{API}/reports/{rid}/tts",
                          headers=_hdr(state.admin_token), timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "audio_data_url" in d and d["audio_data_url"], "audio_data_url missing/empty"
        vp = d.get("voice_provider")
        # openai expected (elevenlabs quota exhausted per spec)
        assert vp in ("openai", "elevenlabs"), f"unexpected voice_provider={vp!r}"
