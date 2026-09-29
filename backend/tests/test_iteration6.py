"""PaintOps Daily - Iteration 6 backend tests:
- Priority Flag support in POST /api/reports (priority_level + priority_flags)
- Structured AI summary with 7 mandatory headers
- Backward compat when no priority fields
- GET list/detail return priority_level + priority_flags
- Regenerate summary preserves priority context ([URGENT: ...] persists)
- Email path exercised via delivered@resend.dev recipient (Resend sink)
- Regression smoke on iteration 1-5 endpoints
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
PROD_EMAIL = "production@paintops.com"
PROD_PASSWORD = "Prod@12345"

REQUIRED_HEADERS = [
    "## WORK COMPLETED",
    "## COMMUNICATIONS",
    "## WEATHER IMPACT",
    "## DELAY / CONSTRAINTS",
    "## CHANGE ORDER / MATERIALS",
    "## NEXT STEPS",
    "## OVERALL SUMMARY",
]


class State:
    admin_token: str = ""
    prod_token: str = ""
    prod_id: str = ""
    report_id_flagged: str = ""
    report_id_plain: str = ""
    report_id_email: str = ""
    ai_summary_flagged: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)


def _assert_headers_in_order(summary: str):
    positions = []
    for h in REQUIRED_HEADERS:
        idx = summary.find(h)
        assert idx != -1, f"Missing header {h!r} in ai_summary:\n{summary}"
        positions.append(idx)
    assert positions == sorted(positions), f"Headers not in order. Positions={positions}\n{summary}"


# ---------- Prep ----------
class TestPrep:
    def test_admin_login(self, state):
        r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert r.status_code == 200, r.text
        state.admin_token = r.json()["access_token"]

    def test_prod_login(self, state):
        r = _login(PROD_EMAIL, PROD_PASSWORD)
        assert r.status_code == 200, r.text
        d = r.json()
        state.prod_token = d["access_token"]
        state.prod_id = d["user"]["id"]


# ---------- Feature 1: priority flag report with 2 flags ----------
class TestPriorityFlaggedReport:
    def test_create_with_priority_and_flags(self, state):
        payload = {
            "project_name": "TEST_IT6_Priority",
            "project_code": "P-IT6-1",
            "customer_name": "Iteration Six Customer",
            "address": "600 Iteration Ave",
            "highlights": "Testing priority + labor issue flag",
            "delays": "Sub arrived one man short",
            "change_orders": "Owner approved trim upgrade",
            "material_notes": "Extra 2 gal Sherwin-Williams primer needed",
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "include_weather": False,
            "recipient_emails": [],
            "priority_level": "High",
            "priority_flags": [
                {"type": "Labor Issue", "reason": "Sub short 1 man for 4 hours"},
                {"type": "Change Order", "reason": None},
            ],
        }
        r = requests.post(f"{API}/reports", json=payload, headers=_hdr(state.prod_token), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("priority_level") == "High"
        assert isinstance(d.get("priority_flags"), list)
        types = [f.get("type") for f in d["priority_flags"]]
        assert "Labor Issue" in types and "Change Order" in types
        summary = d.get("ai_summary") or ""
        state.report_id_flagged = d["id"]
        state.ai_summary_flagged = summary
        _assert_headers_in_order(summary)

    def test_urgent_bullet_under_delay(self, state):
        summary = state.ai_summary_flagged
        # Locate DELAY / CONSTRAINTS section and next header (CHANGE ORDER / MATERIALS)
        start = summary.index("## DELAY / CONSTRAINTS")
        end = summary.index("## CHANGE ORDER / MATERIALS", start)
        section = summary[start:end]
        assert re.search(r"\[URGENT:\s*Labor Issue", section, re.IGNORECASE), (
            f"[URGENT: Labor Issue ...] not found under DELAY / CONSTRAINTS section:\n{section}"
        )


# ---------- Feature 2: backward compat, no priority fields ----------
class TestPlainReportBackwardCompat:
    def test_create_no_priority(self, state):
        payload = {
            "project_name": "TEST_IT6_NoPriority",
            "project_code": "P-IT6-2",
            "customer_name": "Plain Test Customer",
            "address": "700 Plain St",
            "highlights": "Regular day painting exterior trim",
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "include_weather": False,
            "recipient_emails": [],
        }
        r = requests.post(f"{API}/reports", json=payload, headers=_hdr(state.prod_token), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("priority_level") in (None, "")
        assert d.get("priority_flags") == []
        summary = d.get("ai_summary") or ""
        state.report_id_plain = d["id"]
        _assert_headers_in_order(summary)


# ---------- Feature 3: GET returns priority fields ----------
class TestGetReturnsPriority:
    def test_list_contains_priority(self, state):
        r = requests.get(f"{API}/reports", headers=_hdr(state.prod_token), timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        target = next((x for x in items if x.get("id") == state.report_id_flagged), None)
        assert target is not None, "flagged report not in list"
        assert target.get("priority_level") == "High"
        assert isinstance(target.get("priority_flags"), list)
        types = [f.get("type") for f in target["priority_flags"]]
        assert "Labor Issue" in types

    def test_detail_contains_priority(self, state):
        r = requests.get(
            f"{API}/reports/{state.report_id_flagged}",
            headers=_hdr(state.prod_token),
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("priority_level") == "High"
        types = [f.get("type") for f in d.get("priority_flags", [])]
        assert "Labor Issue" in types


# ---------- Feature 4: regenerate preserves priority context ----------
class TestRegeneratePreservesPriority:
    def test_regenerate_keeps_urgent(self, state):
        r = requests.post(
            f"{API}/reports/{state.report_id_flagged}/regenerate-summary",
            headers=_hdr(state.prod_token),
            timeout=120,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        summary = d.get("ai_summary") or ""
        _assert_headers_in_order(summary)
        start = summary.index("## DELAY / CONSTRAINTS")
        end = summary.index("## CHANGE ORDER / MATERIALS", start)
        section = summary[start:end]
        assert re.search(r"\[URGENT:\s*Labor Issue", section, re.IGNORECASE), (
            f"After regenerate, [URGENT: Labor Issue ...] missing under DELAY / CONSTRAINTS:\n{section}"
        )


# ---------- Feature 5: email path with delivered@resend.dev ----------
class TestEmailSink:
    def test_report_email_path_exercised(self, state):
        payload = {
            "project_name": "TEST_IT6_EmailSink",
            "project_code": "P-IT6-3",
            "customer_name": "Email Sink Customer",
            "address": "800 Sink Blvd",
            "highlights": "Verifying email HTML renders 7 sections with priority badge",
            "delays": "Rain in AM",
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "include_weather": False,
            "recipient_emails": ["delivered@resend.dev"],
            "priority_level": "Medium",
            "priority_flags": [{"type": "Property Damage", "reason": "Scratched siding by ladder"}],
        }
        r = requests.post(f"{API}/reports", json=payload, headers=_hdr(state.prod_token), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        state.report_id_email = d["id"]
        summary = d.get("ai_summary") or ""
        _assert_headers_in_order(summary)
        assert d.get("priority_level") == "Medium"
        types = [f.get("type") for f in d.get("priority_flags", [])]
        assert "Property Damage" in types


# ---------- Regression smoke on iterations 1-5 ----------
class TestRegressionIter1to5:
    def test_auth_me(self, state):
        r = requests.get(f"{API}/auth/me", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN_EMAIL

    def test_admin_users_list(self, state):
        r = requests.get(f"{API}/admin/users", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_visits_today(self, state):
        r = requests.get(f"{API}/visits/today", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_breaks_today(self, state):
        r = requests.get(f"{API}/breaks/today", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_sms_today(self, state):
        r = requests.get(f"{API}/sms-logs/today", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_customers_list(self, state):
        r = requests.get(f"{API}/customers", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_digest_schedule_get(self, state):
        r = requests.get(f"{API}/digest/schedule", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200

    def test_workday_export(self, state):
        r = requests.get(
            f"{API}/reports/{state.report_id_flagged}/workday-export",
            headers=_hdr(state.prod_token),
            timeout=15,
        )
        assert r.status_code == 200

    def test_transcribe_400_on_empty(self, state):
        r = requests.post(
            f"{API}/transcribe",
            headers={"Authorization": f"Bearer {state.prod_token}"},
            timeout=15,
        )
        # No file → validation error (400/422)
        assert r.status_code in (400, 422)

    def test_recipient_groups_list_authenticated(self, state):
        r = requests.get(f"{API}/recipient-groups", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_portal_link_generation(self, state):
        r = requests.post(
            f"{API}/reports/{state.report_id_flagged}/portal-link",
            headers=_hdr(state.prod_token),
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        # Response contains a token/url field
        assert any(k in d for k in ("url", "portal_url", "token"))

    def test_signature_endpoint(self, state):
        # Signature endpoint is PATCH /api/reports/{id}/signature — send tiny valid base64
        r = requests.patch(
            f"{API}/reports/{state.report_id_flagged}/signature",
            json={"signature_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="},
            headers=_hdr(state.prod_token),
            timeout=15,
        )
        assert r.status_code in (200, 400, 422), r.text
