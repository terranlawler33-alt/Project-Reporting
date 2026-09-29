"""Iteration 17 — Visit edit/delete/bookmark endpoints.

Covers:
- Bookmark toggle + list endpoint.
- PATCH updates, empty-string clears, unknown id 404, partial patch preserves fields.
- DELETE returns {ok:true}, second delete 404, visit disappears from /visits/today.
- RBAC: non-privileged Production user cannot edit others' visits; admin can.
- Light regression: POST /api/visits auto-weather, POST /visits/{id}/end,
  GET /api/reports returns projects with weather, POST /reports/{id}/tts returns voice_provider.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"

BOSTON_LAT, BOSTON_LON = 42.358, -71.060


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("token") or body["access_token"]


def _create_visit(tok, **overrides):
    payload = {
        "latitude": BOSTON_LAT,
        "longitude": BOSTON_LON,
        "customer_name": overrides.get("customer_name", "TEST_Cust"),
        "address": overrides.get("address", "TEST 1 Main St"),
        "project_code": overrides.get("project_code", "TESTPRJ"),
        "notes": overrides.get("notes", "TEST notes"),
    }
    r = requests.post(f"{API}/visits", headers=_hdr(tok), json=payload, timeout=45)
    assert r.status_code == 200, f"create visit failed: {r.status_code} {r.text}"
    return r.json()


# ------------- Shared session-scoped fixtures -------------
@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def prod_creds(admin_token):
    """Create (idempotent) a Production role user for RBAC test."""
    email = f"test_prod_{uuid.uuid4().hex[:8]}@paintops.com"
    password = "Prod@12345"
    r = requests.post(
        f"{API}/admin/users",
        headers=_hdr(admin_token),
        json={
            "email": email,
            "password": password,
            "name": "TEST Prod User",
            "role": "Production",
            "is_admin": False,
        },
        timeout=30,
    )
    assert r.status_code == 201, f"create prod user failed: {r.status_code} {r.text}"
    user_id = r.json()["id"]
    tok = _login(email, password)
    yield {"email": email, "password": password, "token": tok, "id": user_id}
    # cleanup
    try:
        requests.delete(f"{API}/admin/users/{user_id}", headers=_hdr(admin_token), timeout=15)
    except Exception:
        pass


# ------------- 1. Bookmark flow -------------
class TestBookmarkFlow:
    def test_bookmark_toggle_and_list(self, admin_token):
        # Fresh bookmarked list state prior to creating a new visit — capture ids so we can
        # assert new visit appears/disappears rather than requiring an empty account.
        r0 = requests.get(f"{API}/visits/bookmarked", headers=_hdr(admin_token), timeout=15)
        assert r0.status_code == 200
        initial_ids = {v["id"] for v in r0.json()}

        v = _create_visit(admin_token, customer_name="TEST_Bkmk")
        vid = v["id"]
        assert v.get("bookmarked") is False

        # Should not yet be in bookmarked list.
        r1 = requests.get(f"{API}/visits/bookmarked", headers=_hdr(admin_token), timeout=15)
        assert r1.status_code == 200
        assert vid not in {x["id"] for x in r1.json()}

        # Toggle ON.
        r2 = requests.post(f"{API}/visits/{vid}/bookmark", headers=_hdr(admin_token), timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["bookmarked"] is True

        r3 = requests.get(f"{API}/visits/bookmarked", headers=_hdr(admin_token), timeout=15)
        assert r3.status_code == 200
        ids_after = {x["id"] for x in r3.json()}
        assert vid in ids_after
        assert len(ids_after) == len(initial_ids) + 1

        # Toggle OFF.
        r4 = requests.post(f"{API}/visits/{vid}/bookmark", headers=_hdr(admin_token), timeout=15)
        assert r4.status_code == 200
        assert r4.json()["bookmarked"] is False

        r5 = requests.get(f"{API}/visits/bookmarked", headers=_hdr(admin_token), timeout=15)
        assert vid not in {x["id"] for x in r5.json()}

        # cleanup
        requests.delete(f"{API}/visits/{vid}", headers=_hdr(admin_token), timeout=15)


# ------------- 2. PATCH -------------
class TestPatch:
    def test_patch_updates_and_clears(self, admin_token):
        v = _create_visit(admin_token, customer_name="Old", notes="something")
        vid = v["id"]

        # Update customer_name.
        r = requests.patch(
            f"{API}/visits/{vid}",
            headers=_hdr(admin_token),
            json={"customer_name": "New"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["customer_name"] == "New"
        assert body["notes"] == "something"  # untouched

        # Clear notes with empty string.
        r2 = requests.patch(
            f"{API}/visits/{vid}",
            headers=_hdr(admin_token),
            json={"notes": ""},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["notes"] is None
        assert r2.json()["customer_name"] == "New"  # still preserved

        # Omitted fields keep existing values.
        r3 = requests.patch(
            f"{API}/visits/{vid}",
            headers=_hdr(admin_token),
            json={},
            timeout=15,
        )
        assert r3.status_code == 200
        assert r3.json()["customer_name"] == "New"

        # cleanup
        requests.delete(f"{API}/visits/{vid}", headers=_hdr(admin_token), timeout=15)

    def test_patch_unknown_id_returns_404(self, admin_token):
        r = requests.patch(
            f"{API}/visits/does-not-exist-{uuid.uuid4().hex}",
            headers=_hdr(admin_token),
            json={"customer_name": "x"},
            timeout=15,
        )
        assert r.status_code == 404


# ------------- 3. DELETE -------------
class TestDelete:
    def test_delete_flow(self, admin_token):
        v = _create_visit(admin_token, customer_name="TEST_Delete")
        vid = v["id"]

        r = requests.delete(f"{API}/visits/{vid}", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

        # Subsequent DELETE → 404.
        r2 = requests.delete(f"{API}/visits/{vid}", headers=_hdr(admin_token), timeout=15)
        assert r2.status_code == 404

        # /visits/today no longer includes the id.
        r3 = requests.get(f"{API}/visits/today", headers=_hdr(admin_token), timeout=15)
        assert r3.status_code == 200
        assert vid not in {x["id"] for x in r3.json()}


# ------------- 4. RBAC -------------
class TestRBAC:
    def test_production_user_forbidden_and_admin_allowed(self, admin_token, prod_creds):
        # Admin creates a visit owned by admin.
        v = _create_visit(admin_token, customer_name="TEST_RBAC")
        vid = v["id"]

        prod_tok = prod_creds["token"]
        # Production user cannot patch/delete/bookmark another user's visit.
        r_patch = requests.patch(
            f"{API}/visits/{vid}",
            headers=_hdr(prod_tok),
            json={"customer_name": "hacked"},
            timeout=15,
        )
        assert r_patch.status_code == 403, r_patch.text

        r_bm = requests.post(f"{API}/visits/{vid}/bookmark", headers=_hdr(prod_tok), timeout=15)
        assert r_bm.status_code == 403, r_bm.text

        r_del = requests.delete(f"{API}/visits/{vid}", headers=_hdr(prod_tok), timeout=15)
        assert r_del.status_code == 403, r_del.text

        # Admin can bookmark + patch + delete.
        r_a_bm = requests.post(f"{API}/visits/{vid}/bookmark", headers=_hdr(admin_token), timeout=15)
        assert r_a_bm.status_code == 200
        assert r_a_bm.json()["bookmarked"] is True

        r_a_patch = requests.patch(
            f"{API}/visits/{vid}",
            headers=_hdr(admin_token),
            json={"customer_name": "admin-touched"},
            timeout=15,
        )
        assert r_a_patch.status_code == 200
        assert r_a_patch.json()["customer_name"] == "admin-touched"

        r_a_del = requests.delete(f"{API}/visits/{vid}", headers=_hdr(admin_token), timeout=15)
        assert r_a_del.status_code == 200
        assert r_a_del.json() == {"ok": True}


# ------------- 5. No regression -------------
class TestNoRegression:
    def test_create_visit_has_weather(self, admin_token):
        v = _create_visit(admin_token, customer_name="TEST_Regr")
        assert "weather" in v
        # weather may be None if provider fails, but field should exist and refreshed_at present when weather present.
        if v.get("weather"):
            assert v.get("weather_refreshed_at")
        # cleanup
        requests.delete(f"{API}/visits/{v['id']}", headers=_hdr(admin_token), timeout=15)

    def test_end_visit(self, admin_token):
        v = _create_visit(admin_token, customer_name="TEST_End")
        vid = v["id"]
        r = requests.post(f"{API}/visits/{vid}/end", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        # cleanup
        requests.delete(f"{API}/visits/{vid}", headers=_hdr(admin_token), timeout=15)

    def test_reports_projects_include_weather_key(self, admin_token):
        # Ensure at least one report+project exists by creating a visit + report.
        v = _create_visit(admin_token, customer_name="TEST_ReportRegr", project_code="TEST_RP")
        try:
            rc = requests.post(
                f"{API}/reports",
                headers=_hdr(admin_token),
                json={"highlights": "test", "include_weather": True, "include_visits": True,
                      "include_breaks": False, "include_sms": False},
                timeout=90,
            )
            assert rc.status_code == 200, rc.text
            r = requests.get(f"{API}/reports", headers=_hdr(admin_token), timeout=30)
            assert r.status_code == 200
            reports = r.json()
            assert isinstance(reports, list) and reports
            # Find the report we just created (matches created report id)
            new_rid = rc.json()["id"]
            match = next((rep for rep in reports if rep["id"] == new_rid), reports[0])
            assert isinstance(match.get("projects", []), list)
            found_project = None
            for p in match.get("projects", []) or []:
                found_project = p
                break
            assert found_project is not None, "expected at least one project in the report"
            assert "weather" in found_project, f"project missing weather key: {list(found_project.keys())}"
        finally:
            requests.delete(f"{API}/visits/{v['id']}", headers=_hdr(admin_token), timeout=15)

    def test_report_tts_returns_voice_provider(self, admin_token):
        # Ensure at least one report exists.
        v = _create_visit(admin_token, customer_name="TEST_TTSRegr", project_code="TEST_TTS")
        rid = None
        try:
            rc = requests.post(
                f"{API}/reports",
                headers=_hdr(admin_token),
                json={"highlights": "tts test", "include_weather": True, "include_visits": True,
                      "include_breaks": False, "include_sms": False},
                timeout=90,
            )
            assert rc.status_code == 200, rc.text
            rid = rc.json()["id"]
            r2 = requests.post(f"{API}/reports/{rid}/tts", headers=_hdr(admin_token), timeout=180)
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert "voice_provider" in body, f"tts response missing voice_provider: {list(body.keys())}"
            assert body["voice_provider"] in ("elevenlabs", "openai")
        finally:
            requests.delete(f"{API}/visits/{v['id']}", headers=_hdr(admin_token), timeout=15)
            if rid:
                try:
                    requests.delete(f"{API}/reports/{rid}", headers=_hdr(admin_token), timeout=15)
                except Exception:
                    pass
