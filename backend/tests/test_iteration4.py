"""PaintOps Daily - Iteration 4 backend tests:
- POST /api/register-push (auth + own/other user_id + placeholder EMERGENT_PUSH_KEY tolerance)
- POST /api/reports/{id}/tts (ElevenLabs happy path + 401/404/403)
- send_push fire-and-forget: report create + digest send + signature all still succeed
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
PROD2_EMAIL = "prod2@paintops.com"
PROD2_PASSWORD = "Prod@12345"


class State:
    admin_token: str = ""
    admin_id: str = ""
    prod_token: str = ""
    prod_id: str = ""
    prod2_token: str = ""
    prod2_id: str = ""
    report_id: str = ""     # created by prod (has ai_summary)
    prod2_report_id: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)


# ---------- Prep ----------
class TestPrep:
    def test_admin_login(self, state):
        r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert r.status_code == 200, r.text
        d = r.json()
        state.admin_token = d["access_token"]
        state.admin_id = d["user"]["id"]

    def test_prod_login_or_create(self, state):
        r = _login(PROD_EMAIL, PROD_PASSWORD)
        if r.status_code != 200:
            cr = requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
                "email": PROD_EMAIL, "password": PROD_PASSWORD, "name": "Prod User",
                "role": "Production", "job_title": "Painter", "department": "Field",
                "job_code": "P-01", "is_admin": False,
            }, timeout=15)
            assert cr.status_code == 201, cr.text
            r = _login(PROD_EMAIL, PROD_PASSWORD)
        assert r.status_code == 200, r.text
        d = r.json()
        state.prod_token = d["access_token"]
        state.prod_id = d["user"]["id"]

    def test_prod2_login_or_create(self, state):
        r = _login(PROD2_EMAIL, PROD2_PASSWORD)
        if r.status_code != 200:
            cr = requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
                "email": PROD2_EMAIL, "password": PROD2_PASSWORD, "name": "Prod2 User",
                "role": "Production", "job_title": "Painter", "department": "Field",
                "job_code": "P-02", "is_admin": False,
            }, timeout=15)
            assert cr.status_code in (201, 400), cr.text
            r = _login(PROD2_EMAIL, PROD2_PASSWORD)
        assert r.status_code == 200, r.text
        d = r.json()
        state.prod2_token = d["access_token"]
        state.prod2_id = d["user"]["id"]


# ---------- 1) /register-push ----------
class TestRegisterPush:
    def test_register_push_requires_auth(self):
        r = requests.post(f"{API}/register-push", json={
            "user_id": "x", "platform": "ios", "device_token": "abc",
        }, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_register_push_own_user(self, state):
        r = requests.post(f"{API}/register-push", headers=_hdr(state.prod_token), json={
            "user_id": state.prod_id, "platform": "ios",
            "device_token": "TEST_TOKEN_PROD_ABCDEF",
        }, timeout=15)
        # Placeholder EMERGENT_PUSH_KEY -> 201 with note, or 201 normal
        assert r.status_code == 201, r.text
        d = r.json()
        assert d.get("status") == "registered"

    def test_register_push_other_user_forbidden(self, state):
        r = requests.post(f"{API}/register-push", headers=_hdr(state.prod_token), json={
            "user_id": state.admin_id, "platform": "ios",
            "device_token": "TEST_TOKEN_FORGERY",
        }, timeout=15)
        assert r.status_code == 403, r.text

    def test_register_push_admin_for_other(self, state):
        r = requests.post(f"{API}/register-push", headers=_hdr(state.admin_token), json={
            "user_id": state.prod_id, "platform": "android",
            "device_token": "TEST_TOKEN_ADMIN_FOR_PROD",
        }, timeout=15)
        assert r.status_code == 201, r.text


# ---------- 2) Report create + send_push non-blocking ----------
class TestReportCreateWithPush:
    def test_create_report_still_succeeds(self, state):
        # Regression: even with placeholder push key, create must succeed and populate ai_summary
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "IT4-TTS",
            "project_name": "TEST Iteration4 TTS Project",
            "highlights": "Framed the north wall. Applied primer to trim.",
            "delays": "None.",
            "change_orders": "None.",
            "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id"), "report id must exist"
        assert d.get("ai_summary"), "ai_summary must be populated"
        assert len(d["ai_summary"]) > 20
        state.report_id = d["id"]

    def test_create_report_for_prod2(self, state):
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod2_token), json={
            "project_code": "IT4-FOREIGN",
            "project_name": "TEST Iteration4 Foreign Project",
            "highlights": "Foreign report for TTS 403 test.",
            "delays": "None.",
            "change_orders": "None.",
            "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert r.status_code == 200, r.text
        state.prod2_report_id = r.json()["id"]


# ---------- 3) /reports/{id}/tts ----------
class TestReportTTS:
    def test_tts_requires_auth(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/tts", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_tts_bad_id_404(self, state):
        r = requests.post(f"{API}/reports/nonexistent-id/tts",
                          headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 404, r.text

    def test_tts_foreign_report_forbidden_for_non_management(self, state):
        # prod2 tries to TTS prod's report; both are Production role -> 403
        r = requests.post(f"{API}/reports/{state.report_id}/tts",
                          headers=_hdr(state.prod2_token), timeout=15)
        assert r.status_code == 403, r.text

    def test_tts_happy_path(self, state):
        # ONE call only to save ElevenLabs credits
        r = requests.post(f"{API}/reports/{state.report_id}/tts",
                          headers=_hdr(state.prod_token), timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "audio_data_url" in d
        assert d["audio_data_url"].startswith("data:audio/mpeg;base64,")
        assert isinstance(d.get("bytes"), int)
        assert d["bytes"] > 1000, f"expected >1000 bytes, got {d.get('bytes')}"


# ---------- 4) Signature push non-blocking ----------
class TestSignaturePushNonBlocking:
    def test_signature_still_works(self, state):
        png_b64 = ("data:image/png;base64,"
                   "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAA"
                   "AAYAAjCB0C8AAAAASUVORK5CYII=")
        r = requests.patch(
            f"{API}/reports/{state.report_id}/signature",
            headers=_hdr(state.prod_token),
            json={"customer_name": "TEST Homeowner IT4", "signature_base64": png_b64},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True


# ---------- 5) Digest send non-blocking ----------
class TestDigestPushNonBlocking:
    def test_digest_admin_still_ok(self, state):
        r = requests.post(f"{API}/digest/weekly",
                          headers=_hdr(state.admin_token),
                          json={"recipient_emails": ["delivered@resend.dev"]},
                          timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("text") and len(d["text"]) > 20
        assert isinstance(d.get("report_ids"), list)


# ---------- 6) Regression smoke ----------
class TestRegressionSmoke:
    def test_users_me(self, state):
        r = requests.get(f"{API}/auth/me", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["email"] == PROD_EMAIL

    def test_list_reports(self, state):
        r = requests.get(f"{API}/reports", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_get_report_detail(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}",
                         headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] == state.report_id
        assert d.get("signature", {}).get("customer_name") == "TEST Homeowner IT4"

    def test_weather_api(self, state):
        r = requests.get(f"{API}/weather?lat=37.77&lon=-122.42",
                         headers=_hdr(state.prod_token), timeout=20)
        assert r.status_code == 200, r.text

    def test_digest_schedule_get(self, state):
        r = requests.get(f"{API}/digest/schedule",
                         headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "enabled" in d

    def test_customers_list(self, state):
        r = requests.get(f"{API}/customers", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_portal_link_create(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/portal-link",
                          headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("public_url") or d.get("token")

    def test_transcribe_empty_400(self, state):
        headers = {"Authorization": f"Bearer {state.prod_token}"}
        files = {"audio": ("empty.m4a", b"", "audio/m4a")}
        r = requests.post(f"{API}/transcribe", headers=headers, files=files, timeout=15)
        assert r.status_code == 400, r.text
