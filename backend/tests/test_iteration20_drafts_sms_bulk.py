"""
Backend tests for Iteration 20:
- Draft Reports lifecycle (GET /today, PUT upsert, POST submit, DELETE)
- GET /reports include_drafts filter
- Legacy POST /reports still works + clears existing draft
- POST /sms-logs/bulk + visibility in /sms-logs/today
- Auth required on all new endpoints
- Regression on existing endpoints

Run:
  pytest /app/backend/tests/test_iteration20_drafts_sms_bulk.py -v \
         --junitxml=/app/test_reports/pytest/pytest_iteration20.xml
"""
import os
import time
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _cleanup_today_draft(admin_token):
    """Ensure no leftover draft between tests."""
    requests.delete(
        f"{BASE_URL}/api/reports/draft",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    yield
    requests.delete(
        f"{BASE_URL}/api/reports/draft",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )


# ---------- Health / Auth sanity ----------
class TestHealth:
    def test_login_returns_token(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20


# ---------- Draft lifecycle ----------
class TestDraftLifecycle:
    def _draft_payload(self):
        return {
            "project_code": "TEST_IT20_P1",
            "project_name": "Iteration 20 Draft Project",
            "highlights": "Primed west wall",
            "delays": "none",
            "change_orders": "",
            "material_notes": "2 gal zinsser",
            "include_weather": True,
            "include_visits": True,
            "include_breaks": True,
            "include_sms": True,
            "recipient_emails": ["admin@paintops.com"],
            "priority_level": "Medium",
            "priority_flags": [{"type": "Touch-Ups", "reason": "trim"}],
            "projects": [
                {
                    "project_code": "TEST_IT20_P1",
                    "project_name": "Iteration 20 Draft Project",
                    "customer_name": "Acme",
                    "notes": "Draft project notes",
                }
            ],
        }

    def test_get_todays_draft_returns_null_when_absent(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/reports/draft/today", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        # FastAPI returns `null` for None
        assert r.text.strip() in ("null", '""'), f"Expected null, got {r.text[:200]}"

    def test_put_draft_creates_then_updates_same_id(self, auth_headers):
        payload = self._draft_payload()
        r1 = requests.put(f"{BASE_URL}/api/reports/draft", headers=auth_headers, json=payload, timeout=20)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["status"] == "draft"
        assert d1["highlights"] == "Primed west wall"
        assert d1["project_code"] == "TEST_IT20_P1"
        assert d1["recipient_emails"] == ["admin@paintops.com"]
        assert d1.get("updated_at")
        first_id = d1["id"]
        first_created = d1["created_at"]
        first_updated = d1["updated_at"]

        time.sleep(1.1)

        payload2 = {**payload, "highlights": "Primed west wall + patched hole"}
        r2 = requests.put(f"{BASE_URL}/api/reports/draft", headers=auth_headers, json=payload2, timeout=20)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["id"] == first_id, "PUT should upsert same record (same id)"
        assert d2["status"] == "draft"
        assert d2["highlights"] == "Primed west wall + patched hole"
        assert d2["created_at"] == first_created, "created_at must be preserved across updates"
        assert d2["updated_at"] != first_updated, "updated_at should refresh on each PUT"

        # Verify via GET
        g = requests.get(f"{BASE_URL}/api/reports/draft/today", headers=auth_headers, timeout=15)
        assert g.status_code == 200
        gjson = g.json()
        assert gjson is not None
        assert gjson["id"] == first_id
        assert gjson["highlights"] == "Primed west wall + patched hole"

    def test_delete_draft_then_get_returns_null(self, auth_headers):
        # create first
        r = requests.put(
            f"{BASE_URL}/api/reports/draft",
            headers=auth_headers,
            json=self._draft_payload(),
            timeout=20,
        )
        assert r.status_code == 200
        # delete
        d = requests.delete(f"{BASE_URL}/api/reports/draft", headers=auth_headers, timeout=15)
        assert d.status_code == 200
        body = d.json()
        assert body.get("ok") is True
        assert body.get("removed", 0) >= 1
        # get must be null again
        g = requests.get(f"{BASE_URL}/api/reports/draft/today", headers=auth_headers, timeout=15)
        assert g.status_code == 200
        assert g.text.strip() == "null"

    def test_submit_404_when_no_draft(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/reports/draft/submit", headers=auth_headers, timeout=30)
        assert r.status_code == 404

    def test_submit_flips_status_and_populates_ai_summary(self, auth_headers):
        payload = self._draft_payload()
        # don't send recipient emails here to avoid email latency; separate test will do that
        payload["recipient_emails"] = []
        r = requests.put(f"{BASE_URL}/api/reports/draft", headers=auth_headers, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        draft_id = d["id"]
        draft_created = d["created_at"]

        # Seed one sms log via bulk so submit can attach it
        bulk = requests.post(
            f"{BASE_URL}/api/sms-logs/bulk",
            headers=auth_headers,
            json={
                "items": [
                    {
                        "contact_name": "TEST_IT20_Vendor",
                        "contact_role": "Supplier",
                        "channel": "SMS",
                        "direction": "inbound",
                        "category": "material",
                        "content": "Paint arrives at 10am",
                    }
                ]
            },
            timeout=20,
        )
        assert bulk.status_code == 200, bulk.text

        # AI summary can take a while
        s = requests.post(f"{BASE_URL}/api/reports/draft/submit", headers=auth_headers, timeout=120)
        assert s.status_code == 200, s.text
        final = s.json()
        assert final["id"] == draft_id, "submit must preserve draft id"
        assert final["status"] == "submitted"
        assert final.get("ai_summary"), "ai_summary should be populated after submit"
        assert len(final["ai_summary"]) > 20
        assert final["created_at"] == draft_created, "created_at must be preserved from draft"
        assert final.get("updated_at")
        # auto-pull sms_logs
        assert isinstance(final.get("sms_logs"), list)
        assert any(x.get("content") == "Paint arrives at 10am" for x in final["sms_logs"]), \
            "sms_logs should auto-pull today's logs"

        # After submit, draft should be gone
        g = requests.get(f"{BASE_URL}/api/reports/draft/today", headers=auth_headers, timeout=15)
        assert g.status_code == 200
        assert g.text.strip() == "null", "submitted report should no longer be a draft"

    def test_submit_with_recipient_populates_email_sent_to(self, auth_headers):
        payload = self._draft_payload()
        # Use Resend's test deliverable sandbox address so email actually goes through
        payload["recipient_emails"] = ["delivered@resend.dev"]
        r = requests.put(f"{BASE_URL}/api/reports/draft", headers=auth_headers, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        s = requests.post(f"{BASE_URL}/api/reports/draft/submit", headers=auth_headers, timeout=180)
        assert s.status_code == 200, s.text
        final = s.json()
        assert final["status"] == "submitted"
        # Email send may be slow but should populate email_sent_to on success
        assert isinstance(final.get("email_sent_to"), list)
        if final["email_sent_to"]:
            assert "delivered@resend.dev" in final["email_sent_to"]
        else:
            pytest.skip("Resend/Emergent email provider did not return an id — email_sent_to empty")


# ---------- List filtering ----------
class TestListReportsIncludeDrafts:
    def test_list_excludes_drafts_by_default_and_includes_with_flag(self, auth_headers):
        # Create a draft
        payload = {
            "project_code": "TEST_IT20_LIST",
            "project_name": "List filter",
            "highlights": "listing test",
            "delays": "",
            "change_orders": "",
            "material_notes": "",
            "include_weather": False,
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "recipient_emails": [],
            "projects": [],
        }
        r = requests.put(f"{BASE_URL}/api/reports/draft", headers=auth_headers, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        draft_id = r.json()["id"]

        # Default list — must EXCLUDE draft
        g1 = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers, timeout=20)
        assert g1.status_code == 200
        ids_default = [x["id"] for x in g1.json()]
        assert draft_id not in ids_default, "Default /api/reports MUST exclude drafts"

        # With include_drafts=true — must include draft
        g2 = requests.get(f"{BASE_URL}/api/reports?include_drafts=true", headers=auth_headers, timeout=20)
        assert g2.status_code == 200
        ids_with = [x["id"] for x in g2.json()]
        assert draft_id in ids_with, "/api/reports?include_drafts=true MUST include drafts"


# ---------- Legacy POST /reports still works + clears draft ----------
class TestLegacyReportCreate:
    def test_legacy_post_clears_existing_draft(self, auth_headers):
        # Make a draft first
        put = requests.put(
            f"{BASE_URL}/api/reports/draft",
            headers=auth_headers,
            json={
                "project_code": "TEST_IT20_LEG",
                "project_name": "Legacy clear",
                "highlights": "should be cleared",
                "delays": "",
                "change_orders": "",
                "material_notes": "",
                "include_weather": False,
                "include_visits": False,
                "include_breaks": False,
                "include_sms": False,
                "recipient_emails": [],
                "projects": [],
            },
            timeout=20,
        )
        assert put.status_code == 200

        # Legacy POST
        p = requests.post(
            f"{BASE_URL}/api/reports",
            headers=auth_headers,
            json={
                "project_code": "TEST_IT20_LEG",
                "project_name": "Legacy clear",
                "highlights": "final",
                "delays": "",
                "change_orders": "",
                "material_notes": "",
                "include_weather": False,
                "include_visits": False,
                "include_breaks": False,
                "include_sms": False,
                "recipient_emails": [],
                "projects": [],
            },
            timeout=120,
        )
        assert p.status_code in (200, 201), p.text
        body = p.json()
        assert body["status"] == "submitted"
        assert body.get("ai_summary")

        # Draft should be gone
        g = requests.get(f"{BASE_URL}/api/reports/draft/today", headers=auth_headers, timeout=15)
        assert g.status_code == 200
        assert g.text.strip() == "null", "legacy POST must clear existing draft for today"


# ---------- SMS bulk ----------
class TestSmsBulk:
    def test_bulk_empty_returns_empty_list(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/sms-logs/bulk",
            headers=auth_headers,
            json={"items": []},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_bulk_creates_many_and_show_in_today(self, auth_headers):
        items = [
            {
                "contact_name": f"TEST_IT20_Contact_{i}",
                "contact_role": "GC",
                "channel": "SMS",
                "direction": "inbound" if i % 2 == 0 else "outbound",
                "category": "project_detail",
                "content": f"bulk msg {i}",
            }
            for i in range(3)
        ]
        r = requests.post(
            f"{BASE_URL}/api/sms-logs/bulk",
            headers=auth_headers,
            json={"items": items},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        created = r.json()
        assert len(created) == 3
        for c in created:
            assert c["id"]
            assert c["timestamp"]
            assert c["user_id"]

        # Verify in /sms-logs/today
        g = requests.get(f"{BASE_URL}/api/sms-logs/today", headers=auth_headers, timeout=15)
        assert g.status_code == 200
        today_contents = [x["content"] for x in g.json()]
        for i in range(3):
            assert f"bulk msg {i}" in today_contents


# ---------- Auth required ----------
class TestAuthRequired:
    @pytest.mark.parametrize(
        "method,path,json_body",
        [
            ("GET", "/api/reports/draft/today", None),
            ("PUT", "/api/reports/draft", {"highlights": "x"}),
            ("POST", "/api/reports/draft/submit", None),
            ("DELETE", "/api/reports/draft", None),
            ("POST", "/api/sms-logs/bulk", {"items": []}),
        ],
    )
    def test_requires_auth(self, method, path, json_body):
        r = requests.request(
            method,
            f"{BASE_URL}{path}",
            json=json_body,
            timeout=15,
        )
        assert r.status_code in (401, 403), f"{method} {path} should require auth, got {r.status_code}"


# ---------- Regression on existing endpoints ----------
class TestRegression:
    def test_reports_list_ok(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_visits_today(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/visits/today", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_breaks_today(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/breaks/today", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_settings_lists(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/settings/lists", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "break_types" in body
        assert "priority_flags" in body

    def test_weather(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/weather?lat=37.77&lon=-122.42",
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_weather_hourly(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/weather/hourly?lat=37.77&lon=-122.42",
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 200

    def test_geocode(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/geocode?q=San+Francisco",
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 200
