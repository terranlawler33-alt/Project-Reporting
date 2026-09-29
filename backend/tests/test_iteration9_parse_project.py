"""Iteration 9 — POST /api/parse-project (voice-to-project structured parse).

Covers:
  1. Structured parsing happy path (customer / address / materials / times / touch-up).
  2. Empty text -> 400.
  3. Whitespace-only text -> 400.
  4. Very long text (5000+ chars) -> 200 with 10-key schema (server truncates to 4000).
  5. Gibberish input -> 200 with mostly-null body, touch_up=False, notes non-empty.
  6. Auth required (no Authorization header) -> 401/403.
  7. Schema consistency — exactly the 10 documented keys, types validated.

Regression:
  8. GET /api/reports still returns 200.
  9. POST /api/reports with `projects` payload still works.
 10. POST /api/reports/{id}/tts still works (voice_provider="openai" acceptable).
 11. GET /api/customers/history?name=... still works.
 12. POST /api/transcribe unchanged (400 on missing file, endpoint reachable).
"""
import os
import uuid
import time
import pytest
import requests

# ---------- Base URL discovery (never hardcode) ----------
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for ln in fh:
            if ln.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"

# Long timeout because the endpoint calls gpt-5.4 (spec allows up to 15s per call).
LLM_TIMEOUT = 45

EXPECTED_KEYS = {
    "customer_name", "address", "project_code", "project_name",
    "notes", "materials_used", "start_time", "end_time",
    "touch_up", "priority_flag",
}


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _assert_schema(body: dict):
    """Every response must have exactly the 10 keys with the documented types."""
    assert isinstance(body, dict), f"body not dict: {type(body)}"
    assert set(body.keys()) == EXPECTED_KEYS, (
        f"schema mismatch. missing={EXPECTED_KEYS - set(body.keys())}, "
        f"extra={set(body.keys()) - EXPECTED_KEYS}"
    )
    # touch_up MUST be a bool
    assert isinstance(body["touch_up"], bool), f"touch_up not bool: {type(body['touch_up'])}"
    # every other field: non-empty string OR None (no empty strings, no numbers)
    for k in EXPECTED_KEYS - {"touch_up"}:
        v = body[k]
        assert v is None or (isinstance(v, str) and v.strip() != ""), (
            f"field {k!r} must be None or non-empty string, got {v!r}"
        )


# ================================================================
# (1) Structured parsing happy path
# ================================================================
class TestParseProjectHappyPath:
    def test_dictation_extracts_expected_fields(self, admin_token):
        text = (
            "Worked at John Smith's house at 123 Main Street. Painted the front "
            "porch with two coats of Sherwin Williams ProClassic. Started at "
            "8:00 AM, finished around 3:30 PM. Touch-ups needed on the trim "
            "around the front door."
        )
        r = requests.post(
            f"{API}/parse-project",
            headers=_hdr(admin_token),
            json={"text": text},
            timeout=LLM_TIMEOUT,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        _assert_schema(body)

        # customer_name should contain Smith
        assert body["customer_name"], "customer_name is null"
        assert "Smith" in body["customer_name"], f"customer_name={body['customer_name']!r}"

        # address should contain 123 Main
        assert body["address"], "address is null"
        assert "123 Main" in body["address"], f"address={body['address']!r}"

        # materials should mention ProClassic or Sherwin
        assert body["materials_used"], "materials_used is null"
        assert (
            "ProClassic" in body["materials_used"]
            or "Sherwin" in body["materials_used"]
            or "proclassic" in body["materials_used"].lower()
        ), f"materials_used={body['materials_used']!r}"

        # start_time near 8:00
        assert body["start_time"], "start_time is null"
        assert "8" in body["start_time"] and ":00" in body["start_time"], (
            f"start_time={body['start_time']!r}"
        )

        # end_time near 3:30
        assert body["end_time"], "end_time is null"
        assert "3" in body["end_time"] and "30" in body["end_time"], (
            f"end_time={body['end_time']!r}"
        )

        # touch_up must be true; priority_flag must be Touch-Ups
        assert body["touch_up"] is True, f"touch_up={body['touch_up']!r}"
        assert body["priority_flag"] == "Touch-Ups", (
            f"priority_flag={body['priority_flag']!r}"
        )

        # notes non-empty
        assert body["notes"] and len(body["notes"]) > 0


# ================================================================
# (2) (3) Empty / whitespace text -> 400
# ================================================================
class TestParseProjectInputValidation:
    def test_empty_text_returns_400(self, admin_token):
        r = requests.post(
            f"{API}/parse-project",
            headers=_hdr(admin_token),
            json={"text": ""},
            timeout=15,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        # helpful message
        detail = r.json().get("detail", "")
        assert detail, "no detail message in 400 response"

    def test_whitespace_only_returns_400(self, admin_token):
        r = requests.post(
            f"{API}/parse-project",
            headers=_hdr(admin_token),
            json={"text": "   \n\t   "},
            timeout=15,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


# ================================================================
# (4) Very long input -> 200 (server truncates)
# ================================================================
class TestParseProjectLongInput:
    def test_5000_chars_returns_200_with_schema(self, admin_token):
        long_text = (
            "Painted the exterior of the home at 500 Oak Avenue for customer "
            "Jane Doe. Used Behr Marquee flat white on all siding. "
        ) * 60  # ~120 chars * 60 = ~7200 chars
        assert len(long_text) > 5000

        r = requests.post(
            f"{API}/parse-project",
            headers=_hdr(admin_token),
            json={"text": long_text},
            timeout=LLM_TIMEOUT,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        _assert_schema(body)


# ================================================================
# (5) Gibberish input -> 200, mostly null, notes falls back to input
# ================================================================
class TestParseProjectGibberish:
    def test_gibberish_returns_null_fields_and_notes_fallback(self, admin_token):
        text = "asdf jkl qwerty zxcv"
        r = requests.post(
            f"{API}/parse-project",
            headers=_hdr(admin_token),
            json={"text": text},
            timeout=LLM_TIMEOUT,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        _assert_schema(body)

        # touch_up must be false
        assert body["touch_up"] is False, f"touch_up={body['touch_up']!r}"

        # notes must be non-empty (could be LLM interpretation OR the input fallback)
        assert body["notes"], "notes must be non-empty for gibberish"

        # Most content fields should be null (we allow a couple to be inferred loosely)
        content_fields = ["customer_name", "address", "project_code",
                          "project_name", "materials_used", "start_time",
                          "end_time"]
        null_count = sum(1 for k in content_fields if body[k] is None)
        assert null_count >= 5, (
            f"expected at least 5 null content fields for gibberish, got {null_count}: {body}"
        )


# ================================================================
# (6) Auth required
# ================================================================
class TestParseProjectAuth:
    def test_no_auth_header_rejected(self):
        r = requests.post(
            f"{API}/parse-project",
            headers={"Content-Type": "application/json"},
            json={"text": "hello"},
            timeout=15,
        )
        # canonical unauthenticated status can be 401 or 403 (FastAPI HTTPBearer default)
        assert r.status_code in (401, 403), (
            f"expected 401/403, got {r.status_code}: {r.text}"
        )

    def test_bad_bearer_token_rejected(self):
        r = requests.post(
            f"{API}/parse-project",
            headers={"Authorization": "Bearer garbage.token.here",
                     "Content-Type": "application/json"},
            json={"text": "hello"},
            timeout=15,
        )
        assert r.status_code in (401, 403), (
            f"expected 401/403 for bad token, got {r.status_code}: {r.text}"
        )


# ================================================================
# (7) Schema consistency across several inputs
# ================================================================
class TestParseProjectSchemaConsistency:
    @pytest.mark.parametrize("text", [
        "Painted living room today",
        "Change order requested by customer for exterior trim.",
        "Damaged the customer's fence with the ladder — property damage.",
        "1234567890",
    ])
    def test_all_responses_have_exact_10_keys(self, admin_token, text):
        r = requests.post(
            f"{API}/parse-project",
            headers=_hdr(admin_token),
            json={"text": text},
            timeout=LLM_TIMEOUT,
        )
        assert r.status_code == 200, r.text
        _assert_schema(r.json())


# ================================================================
# (8-12) Regression on other endpoints
# ================================================================
class TestRegression:
    def test_get_reports_200(self, admin_token):
        r = requests.get(f"{API}/reports", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_post_reports_with_projects_payload(self, admin_token):
        payload = {
            "report_date": time.strftime("%Y-%m-%d"),
            "projects": [
                {
                    "customer_name": f"TEST_IT9_{uuid.uuid4().hex[:6]}",
                    "address": "9 Regression Way",
                    "project_code": "IT9-R",
                    "project_name": "Regression Paint",
                    "notes": "TEST IT9 regression project",
                    "materials_used": "Test paint",
                    "start_time": "8:00 AM",
                    "end_time": "5:00 PM",
                    "touch_up": True,
                    "priority_flag": "Touch-Ups",
                }
            ],
        }
        r = requests.post(f"{API}/reports", headers=_hdr(admin_token),
                          json=payload, timeout=LLM_TIMEOUT)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        assert "id" in created, created
        # Verify persistence via GET /reports (report shows up)
        rid = created["id"]
        # store on class for tts test
        TestRegression._report_id = rid  # type: ignore[attr-defined]

        get_r = requests.get(f"{API}/reports", headers=_hdr(admin_token), timeout=15)
        assert get_r.status_code == 200
        ids = [it.get("id") for it in get_r.json()]
        assert rid in ids, f"created report {rid} not in list"

    def test_reports_tts_still_works(self, admin_token):
        rid = getattr(TestRegression, "_report_id", None)
        if not rid:
            pytest.skip("no report id from previous test")
        r = requests.post(f"{API}/reports/{rid}/tts",
                          headers=_hdr(admin_token), timeout=LLM_TIMEOUT)
        assert r.status_code == 200, r.text
        body = r.json()
        # OpenAI fallback is expected because ElevenLabs quota exhausted
        assert body.get("voice_provider") in ("openai", "elevenlabs"), body
        # Some kind of audio url / base64 must be present
        assert any(k in body for k in ("audio_url", "audio_data_url", "audio_base64", "url")), body

    def test_customers_history_endpoint(self, admin_token):
        # Use the customer we just created via projects payload
        r = requests.get(
            f"{API}/customers/history",
            params={"name": "TEST_IT9"},
            headers=_hdr(admin_token),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Response shape can be list or dict wrapper — just make sure it's JSON
        assert r.json() is not None

    def test_transcribe_endpoint_still_reachable(self, admin_token):
        # No file attached -> should be 400/422 (endpoint reachable, not 404/500)
        r = requests.post(f"{API}/transcribe",
                          headers={"Authorization": f"Bearer {admin_token}"},
                          timeout=15)
        assert r.status_code in (400, 422), (
            f"expected 400/422 without file, got {r.status_code}: {r.text}"
        )
