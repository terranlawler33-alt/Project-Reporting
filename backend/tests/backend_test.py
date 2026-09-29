"""PaintOps Daily - Backend API tests using pytest."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://project-digest-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"
PROD_EMAIL = "production@paintops.com"
PROD_PASSWORD = "Prod@12345"


# ---------- Shared state ----------
class State:
    admin_token: str = ""
    admin_id: str = ""
    prod_token: str = ""
    prod_id: str = ""
    visit_id: str = ""
    break_id: str = ""
    sms_id: str = ""
    report_id: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Auth ----------
class TestAuth:
    def test_login_admin(self, state):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data and data["access_token"]
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["is_admin"] is True
        state.admin_token = data["access_token"]
        state.admin_id = data["user"]["id"]

    def test_me(self, state):
        r = requests.get(f"{API}/auth/me", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["email"] == ADMIN_EMAIL

    def test_login_wrong_pw(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401


# ---------- Admin user mgmt ----------
class TestAdminUsers:
    def test_create_production_user(self, state):
        # Delete if pre-existing
        rlist = requests.get(f"{API}/admin/users", headers=_hdr(state.admin_token), timeout=15)
        for u in rlist.json():
            if u["email"] == PROD_EMAIL:
                requests.delete(f"{API}/admin/users/{u['id']}", headers=_hdr(state.admin_token), timeout=15)
        r = requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
            "email": PROD_EMAIL, "password": PROD_PASSWORD, "name": "Prod User",
            "role": "Production", "job_title": "Painter", "department": "Field", "job_code": "P-01",
            "is_admin": False,
        }, timeout=15)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["email"] == PROD_EMAIL
        assert data["role"] == "Production"
        state.prod_id = data["id"]

    def test_list_users(self, state):
        r = requests.get(f"{API}/admin/users", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()]
        assert ADMIN_EMAIL in emails
        assert PROD_EMAIL in emails

    def test_login_production(self, state):
        r = requests.post(f"{API}/auth/login", json={"email": PROD_EMAIL, "password": PROD_PASSWORD}, timeout=15)
        assert r.status_code == 200, r.text
        state.prod_token = r.json()["access_token"]

    def test_non_admin_forbidden(self, state):
        r = requests.get(f"{API}/admin/users", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 403


# ---------- Weather ----------
class TestWeather:
    def test_weather(self, state):
        r = requests.get(f"{API}/weather", params={"lat": 40.7128, "lon": -74.006},
                         headers=_hdr(state.admin_token), timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "temperature_f" in d and "conditions" in d
        assert d["temperature_f"] is not None


# ---------- Visits ----------
class TestVisits:
    def test_create_visit(self, state):
        r = requests.post(f"{API}/visits", headers=_hdr(state.prod_token), json={
            "latitude": 40.7128, "longitude": -74.006,
            "customer_name": "TEST_Customer", "address": "123 Test St",
            "project_code": "TEST-001", "notes": "TEST visit",
        }, timeout=15)
        assert r.status_code == 200, r.text
        state.visit_id = r.json()["id"]

    def test_visits_today(self, state):
        r = requests.get(f"{API}/visits/today", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert state.visit_id in ids

    def test_end_visit(self, state):
        r = requests.post(f"{API}/visits/{state.visit_id}/end", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------- Breaks ----------
class TestBreaks:
    def test_start_admin_call_break(self, state):
        r = requests.post(f"{API}/breaks", headers=_hdr(state.prod_token), json={
            "break_type": "Admin Call", "reason": "TEST call w/ supplier",
            "call_details": "Called ABC Paint — pricing on 5gal Sherwin",
        }, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["break_type"] == "Admin Call"
        assert data["call_details"]
        state.break_id = data["id"]

    def test_end_break(self, state):
        r = requests.post(f"{API}/breaks/{state.break_id}/end", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert "duration_minutes" in r.json()


# ---------- SMS logs ----------
class TestSmsLogs:
    def test_create_sms(self, state):
        r = requests.post(f"{API}/sms-logs", headers=_hdr(state.prod_token), json={
            "contact_name": "TEST Customer", "contact_role": "Homeowner",
            "direction": "inbound", "channel": "SMS", "category": "schedule",
            "content": "TEST: Can you push tomorrow to 10am?",
            "project_code": "TEST-001",
        }, timeout=15)
        assert r.status_code == 200, r.text
        state.sms_id = r.json()["id"]

    def test_sms_today(self, state):
        r = requests.get(f"{API}/sms-logs/today", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert any(s["id"] == state.sms_id for s in r.json())


# ---------- Reports ----------
class TestReports:
    def test_create_report_with_ai_and_email(self, state):
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "TEST-001", "project_name": "TEST Project",
            "highlights": "Primed 2 rooms.", "delays": "None.",
            "change_orders": "None.", "material_notes": "Need 2 more gallons.",
            "include_weather": True, "include_visits": True,
            "include_breaks": True, "include_sms": True,
            "recipient_emails": ["delivered@resend.dev"],
        }, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ai_summary"] and len(data["ai_summary"]) > 20
        # Weather + email may be optional if provider fails, but must be lists/dicts
        assert isinstance(data["email_sent_to"], list)
        state.report_id = data["id"]
        # email_sent_to may include delivered@resend.dev (Emergent email provider)
        print(f"email_sent_to: {data['email_sent_to']}")

    def test_list_reports_prod_sees_own(self, state):
        r = requests.get(f"{API}/reports", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        docs = r.json()
        assert all(d["user_id"] == state.prod_id for d in docs), "Production must only see own reports"

    def test_list_reports_admin_sees_all(self, state):
        r = requests.get(f"{API}/reports", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert state.report_id in ids

    def test_get_report_detail(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == state.report_id

    def test_workday_export(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}/workday-export",
                         headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "date,employee,role" in r.text
