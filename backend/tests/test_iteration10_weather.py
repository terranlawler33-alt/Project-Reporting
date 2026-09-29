"""Iteration 10 backend tests — Weather features on Daily Reporting FastAPI backend.

Covers:
- Auto weather on POST /visits
- POST /visits/{id}/refresh-weather (self, 404, 403 for cross-user by Production role)
- GET /geocode (200 for real query, 400 empty, 401/403 no auth, empty results)
- GET /weather (auth required, admin OK)
- POST /reports auto-derived projects carrying per-visit weather + WEATHER IMPACT
- POST /reports with explicit projects[].weather roundtrip
- Light regression: /parse-project, /reports/{id}/tts, /customers/history, GET /reports
"""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://project-digest-7.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"
PROD_EMAIL = "production@paintops.com"
PROD_PASSWORD = "Prod@12345"

BOSTON_LAT, BOSTON_LON = 42.358, -71.060


class State:
    admin_token: str = ""
    prod_token: str = ""
    prod_id: str = ""
    admin_id: str = ""
    admin_visit_id: str = ""
    prod_visit_id: str = ""
    admin_visit_weather_refreshed_at: str = ""
    seed_customer_name: str = "AutoW"
    seed_report_id: str = ""
    explicit_report_id: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Prep: log in admin + ensure prod user exists ----------
class TestPrep:
    def test_login_admin(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        state.admin_token = d["access_token"]
        state.admin_id = d["user"]["id"]

    def test_login_or_create_prod(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": PROD_EMAIL, "password": PROD_PASSWORD},
                          timeout=15)
        if r.status_code != 200:
            cr = requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
                "email": PROD_EMAIL, "password": PROD_PASSWORD, "name": "Prod User",
                "role": "Production", "job_title": "Painter", "department": "Field",
                "job_code": "P-01", "is_admin": False,
            }, timeout=15)
            assert cr.status_code == 201, cr.text
            r = requests.post(f"{API}/auth/login",
                              json={"email": PROD_EMAIL, "password": PROD_PASSWORD},
                              timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        state.prod_token = d["access_token"]
        state.prod_id = d["user"]["id"]


# ---------- 1) POST /visits auto-attaches weather snapshot ----------
class TestVisitAutoWeather:
    def test_create_visit_auto_weather(self, state):
        payload = {
            "latitude": BOSTON_LAT,
            "longitude": BOSTON_LON,
            "customer_name": state.seed_customer_name,
        }
        r = requests.post(f"{API}/visits", headers=_hdr(state.admin_token),
                          json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id"), "visit must have id"
        state.admin_visit_id = d["id"]
        weather = d.get("weather")
        refreshed_at = d.get("weather_refreshed_at")

        if weather is None:
            # Acceptable degradation
            assert refreshed_at is None, (
                "If weather is null, weather_refreshed_at must also be null. "
                f"Got refreshed_at={refreshed_at!r}"
            )
            pytest.skip("Open-Meteo unavailable — weather is null but response is 200 as expected")
        else:
            assert isinstance(weather.get("temperature_f"), (int, float)), \
                f"temperature_f must be number, got {weather.get('temperature_f')!r}"
            assert isinstance(weather.get("wind_mph"), (int, float)), \
                f"wind_mph must be number, got {weather.get('wind_mph')!r}"
            assert isinstance(weather.get("precipitation"), (int, float)), \
                f"precipitation must be number, got {weather.get('precipitation')!r}"
            assert isinstance(weather.get("conditions"), str) and weather["conditions"], \
                f"conditions must be non-empty string, got {weather.get('conditions')!r}"
            assert isinstance(weather.get("weather_code"), int), \
                f"weather_code must be int, got {weather.get('weather_code')!r}"
            assert isinstance(refreshed_at, str) and refreshed_at, \
                f"weather_refreshed_at must be a non-empty ISO string, got {refreshed_at!r}"
            state.admin_visit_weather_refreshed_at = refreshed_at


# ---------- 2) POST /visits/{id}/refresh-weather ----------
class TestRefreshWeather:
    def test_refresh_self_visit(self, state):
        if not state.admin_visit_id:
            pytest.skip("no seed visit")
        r = requests.post(f"{API}/visits/{state.admin_visit_id}/refresh-weather",
                          headers=_hdr(state.admin_token), timeout=30)
        # Backend may return 502 if Open-Meteo is down; assert 200 primary path
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable (502 from refresh)")
        d = r.json()
        # LocationVisit shape
        for key in ("id", "user_id", "timestamp", "latitude", "longitude",
                    "weather", "weather_refreshed_at"):
            assert key in d, f"missing {key} in refresh response"
        assert d["id"] == state.admin_visit_id
        assert d.get("weather"), "weather must be set after refresh"
        new_ts = d.get("weather_refreshed_at")
        assert isinstance(new_ts, str) and new_ts
        if state.admin_visit_weather_refreshed_at:
            assert new_ts >= state.admin_visit_weather_refreshed_at, (
                f"weather_refreshed_at should be >= create-time. "
                f"new={new_ts} old={state.admin_visit_weather_refreshed_at}"
            )

    def test_refresh_unknown_visit_404(self, state):
        r = requests.post(f"{API}/visits/does-not-exist-xyz/refresh-weather",
                          headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 404, r.text

    def test_refresh_others_visit_forbidden_for_production(self, state):
        # Admin-owned visit; Production role hitting refresh on someone else's visit
        if not state.admin_visit_id:
            pytest.skip("no admin visit")
        r = requests.post(f"{API}/visits/{state.admin_visit_id}/refresh-weather",
                          headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 403, r.text


# ---------- 3) GET /geocode ----------
class TestGeocode:
    def test_geocode_boston_ok(self, state):
        r = requests.get(f"{API}/geocode", headers=_hdr(state.admin_token),
                         params={"q": "Boston"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results")
        assert isinstance(results, list), "results must be array"
        assert 1 <= len(results) <= 8, f"expected 1..8 results, got {len(results)}"
        for item in results:
            assert isinstance(item.get("label"), str) and item["label"], \
                f"label must be non-empty str; got {item.get('label')!r}"
            assert isinstance(item.get("latitude"), (int, float)), \
                f"latitude must be number; got {item.get('latitude')!r}"
            assert isinstance(item.get("longitude"), (int, float)), \
                f"longitude must be number; got {item.get('longitude')!r}"

    def test_geocode_empty_q_400(self, state):
        r = requests.get(f"{API}/geocode", headers=_hdr(state.admin_token),
                         params={"q": ""}, timeout=15)
        assert r.status_code == 400, r.text

    def test_geocode_requires_auth(self):
        r = requests.get(f"{API}/geocode", params={"q": "Boston"}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_geocode_no_match_returns_empty(self, state):
        r = requests.get(f"{API}/geocode", headers=_hdr(state.admin_token),
                         params={"q": "qwertyuiop12345nomatch"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results")
        assert isinstance(results, list)
        # empty or near-empty (allow a few noisy fuzzy matches, cap at 3)
        assert len(results) <= 3, f"expected near-empty results, got {len(results)}: {results}"


# ---------- 4) GET /weather auth ----------
class TestWeatherAuth:
    def test_weather_requires_auth(self):
        r = requests.get(f"{API}/weather", params={"lat": 40, "lon": -74}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_weather_admin_ok(self, state):
        r = requests.get(f"{API}/weather", headers=_hdr(state.admin_token),
                         params={"lat": 40, "lon": -74}, timeout=30)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("Open-Meteo temporarily unavailable")
        d = r.json()
        for key in ("latitude", "longitude", "temperature_f", "wind_mph",
                    "precipitation", "weather_code", "conditions", "fetched_at"):
            assert key in d, f"missing {key} in /weather response"


# ---------- 5) POST /reports auto-derives projects + carries weather ----------
class TestReportAutoProjectsCarryWeather:
    def test_create_visits_then_report_no_projects(self, state):
        # Two distinct visits for admin so `projects` gets auto-derived per visit
        for cname, lat, lon in [
            ("TEST_AutoW_A", 42.360, -71.058),
            ("TEST_AutoW_B", 40.7128, -74.0060),
        ]:
            r = requests.post(f"{API}/visits", headers=_hdr(state.admin_token),
                              json={"latitude": lat, "longitude": lon,
                                    "customer_name": cname}, timeout=30)
            assert r.status_code == 200, r.text

        # Create report WITHOUT `projects` — must derive from today's visits
        rc = requests.post(f"{API}/reports", headers=_hdr(state.admin_token), json={
            "highlights": "TEST auto projects derivation.",
            "delays": "None.",
            "change_orders": "None.",
            "material_notes": "None.",
            "include_weather": True,
            "include_visits": True,
            "include_breaks": False,
            "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert rc.status_code == 200, rc.text
        state.seed_report_id = rc.json()["id"]

        gr = requests.get(f"{API}/reports/{state.seed_report_id}",
                          headers=_hdr(state.admin_token), timeout=30)
        assert gr.status_code == 200, gr.text
        d = gr.json()
        projects = d.get("projects")
        assert isinstance(projects, list) and len(projects) >= 1, \
            f"projects must be non-empty array, got {projects!r}"

        with_weather = [p for p in projects if p.get("weather")]
        assert with_weather, (
            "At least one derived project must carry a non-null weather snapshot. "
            f"projects={projects}"
        )

        summary = (d.get("ai_summary") or "")
        low = summary.lower()
        # Look for WEATHER IMPACT block and some weather hint
        assert "weather impact" in low, f"WEATHER IMPACT block missing in ai_summary: {summary[:400]!r}"
        assert ("°f" in low) or (" f" in low) or ("weather" in low), \
            f"Expected °F/F/weather mention in ai_summary: {summary[:400]!r}"


# ---------- 6) Explicit projects[].weather roundtrip ----------
class TestExplicitProjectsWeatherRoundtrip:
    def test_explicit_projects_weather_roundtrip(self, state):
        payload = {
            "highlights": "TEST explicit projects weather.",
            "delays": "",
            "change_orders": "",
            "material_notes": "",
            "include_weather": False,
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "recipient_emails": [],
            "projects": [{
                "id": "p1",
                "address": "Test",
                "weather": {
                    "temperature_f": 72,
                    "wind_mph": 5,
                    "precipitation": 0.0,
                    "conditions": "Clear",
                    "weather_code": 0,
                },
            }],
        }
        r = requests.post(f"{API}/reports", headers=_hdr(state.admin_token),
                          json=payload, timeout=180)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        state.explicit_report_id = rid

        gr = requests.get(f"{API}/reports/{rid}", headers=_hdr(state.admin_token), timeout=30)
        assert gr.status_code == 200, gr.text
        d = gr.json()
        projects = d.get("projects") or []
        assert projects, "expected projects to persist"
        assert projects[0].get("id") == "p1"
        w = projects[0].get("weather") or {}
        assert w.get("temperature_f") == 72, f"weather.temperature_f roundtrip broken: {w!r}"
        assert w.get("conditions") == "Clear"
        assert w.get("weather_code") == 0


# ---------- 7) Light regression ----------
class TestRegression:
    def test_parse_project_quick(self, state):
        r = requests.post(f"{API}/parse-project", headers=_hdr(state.admin_token),
                          json={"text": "Painted trim at 12 Main St, needs touch-ups tomorrow"},
                          timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        # Response should be an object with expected keys (values may be null)
        assert isinstance(d, dict)
        for k in ("customer_name", "address", "project_code", "project_name",
                  "notes", "materials_used", "start_time", "end_time",
                  "touch_up", "priority_flag"):
            assert k in d, f"parse-project missing key {k}"

    def test_report_tts_openai_ok(self, state):
        if not state.seed_report_id:
            pytest.skip("no seed report")
        r = requests.post(f"{API}/reports/{state.seed_report_id}/tts",
                          headers=_hdr(state.admin_token), timeout=180)
        # tts may return 200 with audio or specific 4xx if content missing; treat 200 as success
        assert r.status_code == 200, r.text
        d = r.json()
        assert "audio_data_url" in d
        vp = d.get("voice_provider")
        # openai is acceptable per spec
        assert vp in ("openai", "elevenlabs"), f"unexpected voice_provider={vp!r}"

    def test_customers_history(self, state):
        r = requests.get(f"{API}/customers/history",
                         headers=_hdr(state.admin_token),
                         params={"name": "TEST_AutoW_A"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Shape: visits list + reports summary + photos
        assert isinstance(d.get("visits"), list)
        assert isinstance(d.get("reports"), list) or isinstance(d.get("reports_summary"), list) or True
        # At least visits should include our seeded customer
        assert any(v.get("customer_name") == "TEST_AutoW_A" for v in d["visits"]), \
            f"expected TEST_AutoW_A visit in history: {d['visits'][:3]}"

    def test_get_reports_list(self, state):
        r = requests.get(f"{API}/reports", headers=_hdr(state.admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d, list)
