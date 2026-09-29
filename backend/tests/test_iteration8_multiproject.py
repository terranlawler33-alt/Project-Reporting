"""Iteration 8 — multi-project reports, customer history, touch-ups flag, backward-compat.

Covers:
  1. POST /api/visits with new optional project_id (persist + GET /visits/today)
  2. POST /api/reports with `projects: List[ProjectEntry]` (persist + AI summary mentions them)
  3. Backward-compat: legacy report without `projects` -> GET returns derived projects from visits
  4. GET /api/customers/history — happy path, case-insensitive, 400, 401
  5. Touch-Ups flag persisted + surfaced in AI summary
  6. Regression: GET /reports, POST /reports/{id}/tts, /regenerate-summary, GET /customers
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend env explicitly (never hardcode a URL secret)
    with open("/app/frontend/.env") as fh:
        for ln in fh:
            if ln.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------- (1) POST /visits with project_id ----------
class TestVisitProjectId:
    def test_visit_with_project_id_persists(self, admin_token):
        pid = f"proj-{uuid.uuid4().hex[:8]}"
        payload = {
            "latitude": 40.7128,
            "longitude": -74.006,
            "customer_name": "TEST_IT8_Alice",
            "address": "1 Alice Way",
            "project_code": "IT8-A",
            "notes": "TEST IT8 visit A",
            "project_id": pid,
        }
        r = requests.post(f"{API}/visits", headers=_hdr(admin_token), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["project_id"] == pid
        assert created["customer_name"] == "TEST_IT8_Alice"

        # GET today's visits and confirm project_id round-trips
        rt = requests.get(f"{API}/visits/today", headers=_hdr(admin_token), timeout=15)
        assert rt.status_code == 200
        today = rt.json()
        match = [v for v in today if v["id"] == created["id"]]
        assert match, "created visit not found in /visits/today"
        assert match[0]["project_id"] == pid

    def test_visit_without_project_id_still_ok(self, admin_token):
        payload = {
            "latitude": 41.0,
            "longitude": -75.0,
            "customer_name": "TEST_IT8_NoPid",
            "address": "2 NoPid St",
            "notes": "TEST IT8 visit w/o pid",
        }
        r = requests.post(f"{API}/visits", headers=_hdr(admin_token), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # project_id must be present in schema and be null/None
        assert "project_id" in body
        assert body["project_id"] in (None, "")


# ---------- (2) POST /reports with multiple projects ----------
@pytest.fixture(scope="module")
def multi_project_report(admin_token):
    """Create a report with 2 explicit projects (used by tests 2 + 5 + regression)."""
    payload = {
        "highlights": "Two crews out today.",
        "delays": "",
        "change_orders": "",
        "material_notes": "Restock primer tomorrow.",
        "include_weather": False,
        "include_visits": False,
        "include_breaks": False,
        "include_sms": False,
        "recipient_emails": [],
        "priority_flags": [{"type": "Touch-Ups", "reason": "Ceiling touch-up at Bob site"}],
        "projects": [
            {
                "project_code": "IT8-P1",
                "project_name": "Alice Kitchen Repaint",
                "customer_name": "TEST_IT8_Alice",
                "address": "1 Alice Way",
                "notes": "Primed kitchen walls; masked cabinets.",
                "materials_used": "2 gal Sherwin Extra White",
                "start_time": "08:00",
                "end_time": "12:00",
                "priority_flag": None,
                "touch_up": False,
            },
            {
                "project_code": "IT8-P2",
                "project_name": "Bob Living Room",
                "customer_name": "TEST_IT8_Bob",
                "address": "99 Bob Blvd",
                "notes": "Second coat on trim; small ceiling touch-up outstanding.",
                "materials_used": "1 gal Cabinet Coat",
                "start_time": "13:00",
                "end_time": "17:00",
                "priority_flag": "Touch-Ups",
                "touch_up": True,
            },
        ],
    }
    r = requests.post(f"{API}/reports", headers=_hdr(admin_token), json=payload, timeout=180)
    assert r.status_code == 200, r.text
    return r.json()


class TestMultiProjectReport:
    def test_projects_field_persisted(self, multi_project_report):
        data = multi_project_report
        projs = data.get("projects") or []
        assert len(projs) == 2, f"expected 2 projects, got {len(projs)}"
        # fields carried back for each
        by_code = {p["project_code"]: p for p in projs}
        assert set(by_code.keys()) == {"IT8-P1", "IT8-P2"}
        p1, p2 = by_code["IT8-P1"], by_code["IT8-P2"]
        assert p1["customer_name"] == "TEST_IT8_Alice"
        assert p1["address"] == "1 Alice Way"
        assert p1["notes"].startswith("Primed kitchen")
        assert p1["materials_used"] == "2 gal Sherwin Extra White"
        assert p1["start_time"] == "08:00"
        assert p1["end_time"] == "12:00"
        assert p2["customer_name"] == "TEST_IT8_Bob"
        assert p2["priority_flag"] == "Touch-Ups"
        assert p2["touch_up"] is True

    def test_ai_summary_mentions_projects(self, multi_project_report):
        summary = (multi_project_report.get("ai_summary") or "").lower()
        assert summary, "empty ai_summary"
        # Accept any of the tokens per spec
        tokens = ["test_it8_alice", "test_it8_bob", "project 1", "project 2",
                  "alice", "bob", "it8-p1", "it8-p2"]
        assert any(t in summary for t in tokens), f"summary lacks project markers: {summary[:400]}"


# ---------- (5) Touch-Ups flag persistence + AI summary ----------
class TestTouchUps:
    def test_touchups_priority_flag_persisted(self, multi_project_report):
        flags = multi_project_report.get("priority_flags") or []
        types = [f.get("type") for f in flags]
        assert "Touch-Ups" in types, f"Touch-Ups flag not persisted: {flags}"

    def test_touchup_in_ai_summary(self, multi_project_report):
        summary = (multi_project_report.get("ai_summary") or "")
        u = summary.upper()
        assert ("TOUCH-UP" in u) or ("TOUCH-UPS" in u), \
            f"AI summary missing TOUCH-UP marker. First 500 chars:\n{summary[:500]}"


# ---------- (3) Backward-compat: legacy report derives projects from visits ----------
class TestBackwardCompat:
    def test_legacy_report_derives_projects(self, admin_token):
        # Two fresh visits with distinct project_ids
        pid1 = f"legacy-{uuid.uuid4().hex[:6]}"
        pid2 = f"legacy-{uuid.uuid4().hex[:6]}"
        r1 = requests.post(f"{API}/visits", headers=_hdr(admin_token), json={
            "latitude": 42.1, "longitude": -71.1,
            "customer_name": "TEST_IT8_LegacyCarol",
            "address": "10 Carol Ct", "project_code": "L-CAROL",
            "notes": "TEST legacy Carol visit", "project_id": pid1,
        }, timeout=15)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/visits", headers=_hdr(admin_token), json={
            "latitude": 42.2, "longitude": -71.2,
            "customer_name": "TEST_IT8_LegacyDan",
            "address": "22 Dan Dr", "project_code": "L-DAN",
            "notes": "TEST legacy Dan visit", "project_id": pid2,
        }, timeout=15)
        assert r2.status_code == 200, r2.text

        # Create report WITHOUT projects (legacy client style)
        rep = requests.post(f"{API}/reports", headers=_hdr(admin_token), json={
            "highlights": "Legacy client style report.",
            "include_weather": False, "include_visits": True,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert rep.status_code == 200, rep.text
        report = rep.json()
        rid = report["id"]

        # GET the report and verify derived projects
        g = requests.get(f"{API}/reports/{rid}", headers=_hdr(admin_token), timeout=15)
        assert g.status_code == 200, g.text
        got = g.json()
        projs = got.get("projects") or []
        # Should derive one project per unique project_id (Carol and Dan) — at minimum contain them
        assert len(projs) >= 2, f"expected >=2 derived projects, got {len(projs)}"
        customers = [(p.get("customer_name") or "") for p in projs]
        assert any("Carol" in c for c in customers), f"Carol missing: {customers}"
        assert any("Dan" in c for c in customers), f"Dan missing: {customers}"


# ---------- (4) GET /customers/history ----------
class TestCustomerHistory:
    @pytest.fixture(scope="class")
    def seeded(self, admin_token):
        """Seed 1 customer + 2 visits + 1 report referencing the customer via projects."""
        cname = f"TEST_IT8_Hist_{uuid.uuid4().hex[:6]}"
        # 1 customer
        cr = requests.post(f"{API}/customers", headers=_hdr(admin_token), json={
            "name": cname, "address": "500 History Ln", "phone": "555-0100",
            "notes": "TEST customer history seed",
        }, timeout=15)
        assert cr.status_code == 201, cr.text
        customer = cr.json()

        # 2 visits with that customer name
        for i in range(2):
            rv = requests.post(f"{API}/visits", headers=_hdr(admin_token), json={
                "latitude": 40.0 + i * 0.01, "longitude": -74.0,
                "customer_name": cname, "address": "500 History Ln",
                "project_code": "HIST-01", "notes": f"TEST history visit {i}",
            }, timeout=15)
            assert rv.status_code == 200, rv.text

        # 1 report with a project block referencing that customer name
        rr = requests.post(f"{API}/reports", headers=_hdr(admin_token), json={
            "highlights": "TEST customer-history report",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
            "projects": [{
                "project_code": "HIST-01",
                "customer_name": cname,
                "address": "500 History Ln",
                "notes": "TEST history project",
                "start_time": "09:00",
                "end_time": "10:00",
            }],
        }, timeout=180)
        assert rr.status_code == 200, rr.text
        report = rr.json()
        return {"name": cname, "customer": customer, "report_id": report["id"]}

    def test_history_happy_path(self, admin_token, seeded):
        r = requests.get(f"{API}/customers/history",
                         params={"name": seeded["name"]},
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("customer") is not None, "customer directory entry missing"
        assert data["customer"]["name"] == seeded["name"]
        assert isinstance(data.get("visits"), list) and len(data["visits"]) >= 2
        assert isinstance(data.get("reports"), list) and len(data["reports"]) >= 1
        assert any(rr["id"] == seeded["report_id"] for rr in data["reports"]), \
            "seeded report id not in history reports"
        assert "photos" in data and isinstance(data["photos"], list)
        counts = data.get("counts") or {}
        assert counts.get("visits") == len(data["visits"])
        assert counts.get("reports") == len(data["reports"])
        assert counts.get("photos") == len(data["photos"])

    def test_history_case_insensitive_partial(self, admin_token, seeded):
        # Lowercased partial (strip prefix and use middle chunk)
        partial = seeded["name"].split("_")[-1].lower()  # the hex suffix
        r = requests.get(f"{API}/customers/history",
                         params={"name": partial},
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert (data.get("counts") or {}).get("visits", 0) >= 2, \
            f"case-insensitive partial should still match: {data.get('counts')}"

    def test_history_empty_name_400(self, admin_token):
        r = requests.get(f"{API}/customers/history",
                         params={"name": "   "},
                         headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_history_unauth_401(self):
        r = requests.get(f"{API}/customers/history", params={"name": "anything"}, timeout=15)
        # FastAPI returns 401 (Not authenticated) when Bearer is missing / 403 on some setups
        assert r.status_code in (401, 403), r.text


# ---------- (6) Regression ----------
class TestRegression:
    def test_list_reports_200(self, admin_token):
        r = requests.get(f"{API}/reports", headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        docs = r.json()
        assert isinstance(docs, list)
        # every doc must have `projects` field (list, possibly empty or derived)
        for d in docs:
            assert "projects" in d, f"legacy doc missing projects field: {d.get('id')}"
            assert isinstance(d["projects"], list)

    def test_tts_regression(self, admin_token, multi_project_report):
        rid = multi_project_report["id"]
        r = requests.post(f"{API}/reports/{rid}/tts", headers=_hdr(admin_token), timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("audio_data_url", "").startswith("data:audio/mpeg;base64,")
        assert body.get("voice_provider") in ("elevenlabs", "openai"), body

    def test_regenerate_summary_regression(self, admin_token, multi_project_report):
        rid = multi_project_report["id"]
        r = requests.post(f"{API}/reports/{rid}/regenerate-summary",
                          headers=_hdr(admin_token), timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == rid
        assert body.get("ai_summary")
        # projects should still be preserved
        assert isinstance(body.get("projects"), list) and len(body["projects"]) == 2

    def test_customers_directory_unchanged(self, admin_token):
        r = requests.get(f"{API}/customers", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
