"""
Iteration 21 backend tests:
  - Public HTML portal (GET /api/public/reports/{token})
  - Public respond (POST /api/public/reports/{token}/respond)
  - Mail inbox (GET /api/responses, /api/responses/unread-count,
    /api/reports/{id}/responses, PATCH read/unread, POST archive, DELETE)
  - Project summary PATCH (PATCH /api/reports/{id}/projects/{pid}/summary)
  - Regression on legacy POST /api/reports (ProjectEntry.summary added) and drafts
  - Auth gating

Run serially (autouse cleanup wipes shared admin draft/responses between tests):
  pytest /app/backend/tests/test_iteration21_responses_summary.py -v -o addopts=""
"""

import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

# Load frontend .env (EXPO_PUBLIC_BACKEND_URL lives there)
load_dotenv("/app/frontend/.env")

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or ""
).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASS = "Admin@12345"


# ---------- shared fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def admin_user(admin_token):
    r = requests.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def labor_user(auth_headers):
    """Create a non-FULL_ROLES user (Labor) to test 403s. Reuse if exists."""
    email = f"test_it21_labor_{uuid.uuid4().hex[:6]}@paintops.com"
    password = "Labor@12345"
    r = requests.post(
        f"{API}/admin/users",
        headers=auth_headers,
        json={
            "email": email,
            "name": "IT21 Labor",
            "password": password,
            "role": "Labor",
            "is_admin": False,
        },
        timeout=15,
    )
    assert r.status_code in (201, 409), f"User create failed: {r.status_code} {r.text}"
    user_id = r.json().get("id") if r.status_code == 201 else None

    login = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert login.status_code == 200, f"Labor login failed: {login.text}"
    tok = login.json().get("access_token") or login.json().get("token")

    yield {"email": email, "password": password, "token": tok, "id": user_id}

    # Cleanup
    if user_id:
        requests.delete(f"{API}/admin/users/{user_id}", headers=auth_headers, timeout=15)


def _create_report_with_projects(auth_headers, flagged: bool = True):
    """POST /api/reports to create a submitted report with a project (optionally flagged)."""
    pid_flagged = str(uuid.uuid4())
    pid_normal = str(uuid.uuid4())
    projects = [
        {
            "id": pid_flagged,
            "project_code": "TEST_IT21_P1",
            "project_name": "TEST_IT21 Flagged Job",
            "customer_name": "ACME",
            "address": "123 Flagged St",
            "notes": "Touch up on front door",
            "priority_flag": "Touch-Ups" if flagged else None,
        },
        {
            "id": pid_normal,
            "project_code": "TEST_IT21_P2",
            "project_name": "TEST_IT21 Normal Job",
            "customer_name": "Other",
            "address": "456 Normal Ave",
            "notes": "All good",
            "priority_flag": None,
        },
    ]
    payload = {
        "highlights": "TEST_IT21 highlights",
        "delays": "",
        "change_orders": "",
        "material_notes": "",
        "include_weather": False,
        "include_visits": False,
        "include_breaks": False,
        "include_sms": False,
        "recipient_emails": [],
        "projects": projects,
    }
    r = requests.post(f"{API}/reports", headers=auth_headers, json=payload, timeout=60)
    assert r.status_code == 200, f"Legacy POST /reports failed: {r.status_code} {r.text}"
    rep = r.json()
    return rep, pid_flagged, pid_normal


def _mint_token(auth_headers, report_id):
    r = requests.post(
        f"{API}/reports/{report_id}/portal-link",
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 200, f"portal-link failed: {r.text}"
    return r.json()["token"]


# ---------- autouse cleanup — wipe admin responses/drafts between tests ----------
@pytest.fixture(autouse=True)
def _wipe_responses_between_tests(auth_headers):
    yield
    # purge all responses visible to admin (admin sees all)
    try:
        r = requests.get(
            f"{API}/responses?include_archived=true",
            headers=auth_headers,
            timeout=15,
        )
        if r.status_code == 200:
            for item in r.json():
                requests.delete(
                    f"{API}/responses/{item['id']}",
                    headers=auth_headers,
                    timeout=10,
                )
    except Exception:
        pass


# ============================================================
# 1. Public HTML portal — GET /api/public/reports/{token}
# ============================================================
class TestPublicPortalHTML:
    def test_bogus_token_returns_404(self):
        r = requests.get(f"{API}/public/reports/this-token-does-not-exist-xyz", timeout=15)
        assert r.status_code == 404

    def test_returns_html_200_with_ai_summary_and_respond_for_flagged(self, auth_headers):
        rep, pid_flagged, pid_normal = _create_report_with_projects(auth_headers, flagged=True)
        token = _mint_token(auth_headers, rep["id"])

        r = requests.get(f"{API}/public/reports/{token}", timeout=15)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct.lower(), f"Expected text/html, got {ct}"
        body = r.text
        assert "<html" in body.lower()
        assert rep["ai_summary"][:30] in body or rep["ai_summary"][:10] in body
        # flagged project must render a respond button or anchor
        assert "respond-btn" in body or "Respond" in body
        # project id should be referenced on the respond button
        assert pid_flagged in body


# ============================================================
# 2. Public respond — POST /api/public/reports/{token}/respond
# ============================================================
class TestPublicRespond:
    def test_bad_token_404(self):
        r = requests.post(
            f"{API}/public/reports/does-not-exist/respond",
            json={"message": "hi"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_empty_message_422(self, auth_headers):
        rep, pid_flagged, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r = requests.post(
            f"{API}/public/reports/{token}/respond",
            json={"message": ""},
            timeout=15,
        )
        assert r.status_code == 422, f"Expected 422, got {r.status_code} {r.text}"

    def test_valid_response_matches_project(self, auth_headers, admin_user):
        rep, pid_flagged, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])

        payload = {
            "project_id": pid_flagged,
            "reporter_name": "External Jane",
            "reporter_email": "jane@example.com",
            "message": "We will send a crew tomorrow at 9am.",
        }
        # IMPORTANT: public endpoint — NO auth header
        r = requests.post(
            f"{API}/public/reports/{token}/respond",
            json=payload,
            timeout=20,
        )
        assert r.status_code == 200, f"respond failed: {r.status_code} {r.text}"
        d = r.json()
        assert d["report_id"] == rep["id"]
        assert d["report_user_id"] == admin_user["id"]
        assert d["project_id"] == pid_flagged
        assert d["project_label"] == "TEST_IT21 Flagged Job"
        assert d["project_flag"] == "Touch-Ups"
        assert d["reporter_name"] == "External Jane"
        assert d["reporter_email"] == "jane@example.com"
        assert d["message"] == payload["message"]
        assert d["read_at"] is None
        assert d["archived"] is False

    def test_nonmatching_project_id_returns_null_label(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r = requests.post(
            f"{API}/public/reports/{token}/respond",
            json={"project_id": "not-a-real-pid-abc", "message": "general msg"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["project_label"] is None
        assert d["project_flag"] is None

    def test_only_message_required(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r = requests.post(
            f"{API}/public/reports/{token}/respond",
            json={"message": "just a message"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["message"] == "just a message"
        assert d["reporter_name"] is None
        assert d["reporter_email"] is None


# ============================================================
# 3. Mail inbox — GET /api/responses
# ============================================================
class TestResponsesInbox:
    def test_list_responses_sorted_desc(self, auth_headers):
        rep, pid, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        # create two responses
        requests.post(f"{API}/public/reports/{token}/respond", json={"message": "first", "project_id": pid}, timeout=15)
        requests.post(f"{API}/public/reports/{token}/respond", json={"message": "second"}, timeout=15)

        r = requests.get(f"{API}/responses", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2
        # newest first
        assert items[0]["created_at"] >= items[1]["created_at"]
        # none archived in default list
        assert all(not it["archived"] for it in items)

    def test_unread_only_filter(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r1 = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "unread msg"}, timeout=15).json()
        r2 = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "will be read"}, timeout=15).json()

        # mark r2 as read
        requests.patch(f"{API}/responses/{r2['id']}/read", headers=auth_headers, timeout=15)

        r = requests.get(f"{API}/responses?unread_only=true", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()]
        assert r1["id"] in ids
        assert r2["id"] not in ids

    def test_include_archived_flag(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        resp = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "archive me"}, timeout=15).json()
        # archive it
        requests.post(f"{API}/responses/{resp['id']}/archive", headers=auth_headers, timeout=15)

        default_list = requests.get(f"{API}/responses", headers=auth_headers, timeout=15).json()
        assert resp["id"] not in [x["id"] for x in default_list]

        with_arch = requests.get(f"{API}/responses?include_archived=true", headers=auth_headers, timeout=15).json()
        assert resp["id"] in [x["id"] for x in with_arch]

    def test_requires_auth(self):
        r = requests.get(f"{API}/responses", timeout=15)
        assert r.status_code in (401, 403)


# ============================================================
# 4. Unread count
# ============================================================
class TestUnreadCount:
    def test_unread_count_excludes_archived(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        a = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "A"}, timeout=15).json()
        b = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "B"}, timeout=15).json()
        c = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "C"}, timeout=15).json()

        # archive one, mark one read
        requests.post(f"{API}/responses/{a['id']}/archive", headers=auth_headers, timeout=15)
        requests.patch(f"{API}/responses/{b['id']}/read", headers=auth_headers, timeout=15)

        r = requests.get(f"{API}/responses/unread-count", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        count = r.json().get("count")
        # Only c should be unread + unarchived
        assert count == 1, f"Expected 1 unread (c only), got {count}"


# ============================================================
# 5. Per-report responses + ownership
# ============================================================
class TestPerReportResponses:
    def test_owner_can_list_sorted_asc(self, auth_headers):
        rep, pid, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        requests.post(f"{API}/public/reports/{token}/respond", json={"message": "first", "project_id": pid}, timeout=15)
        requests.post(f"{API}/public/reports/{token}/respond", json={"message": "second"}, timeout=15)

        r = requests.get(f"{API}/reports/{rep['id']}/responses", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2
        # ASC
        assert items[0]["created_at"] <= items[-1]["created_at"]
        assert items[0]["message"] == "first"

    def test_non_fullrole_non_owner_gets_403(self, auth_headers, labor_user):
        rep, _, _ = _create_report_with_projects(auth_headers)
        labor_hdr = {"Authorization": f"Bearer {labor_user['token']}"}
        r = requests.get(f"{API}/reports/{rep['id']}/responses", headers=labor_hdr, timeout=15)
        assert r.status_code == 403, f"Expected 403 for Labor user, got {r.status_code} {r.text}"


# ============================================================
# 6. PATCH read/unread, POST archive, DELETE + auth/ownership
# ============================================================
class TestResponseLifecycle:
    def _mk(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        resp = requests.post(f"{API}/public/reports/{token}/respond", json={"message": "lifecycle"}, timeout=15).json()
        return resp

    def test_mark_read_then_unread(self, auth_headers):
        resp = self._mk(auth_headers)
        r = requests.patch(f"{API}/responses/{resp['id']}/read", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["read_at"] is not None

        r = requests.patch(f"{API}/responses/{resp['id']}/unread", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["read_at"] is None

    def test_archive_sets_archived_true(self, auth_headers):
        resp = self._mk(auth_headers)
        r = requests.post(f"{API}/responses/{resp['id']}/archive", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["archived"] is True

    def test_delete_removes(self, auth_headers):
        resp = self._mk(auth_headers)
        r = requests.delete(f"{API}/responses/{resp['id']}", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        # Verify no longer in include_archived list
        all_list = requests.get(f"{API}/responses?include_archived=true", headers=auth_headers, timeout=15).json()
        assert resp["id"] not in [x["id"] for x in all_list]

    def test_bad_id_404(self, auth_headers):
        for path in [
            f"{API}/responses/{uuid.uuid4()}/read",
            f"{API}/responses/{uuid.uuid4()}/unread",
        ]:
            r = requests.patch(path, headers=auth_headers, timeout=15)
            assert r.status_code == 404, f"{path} => {r.status_code}"
        r = requests.post(f"{API}/responses/{uuid.uuid4()}/archive", headers=auth_headers, timeout=15)
        assert r.status_code == 404
        r = requests.delete(f"{API}/responses/{uuid.uuid4()}", headers=auth_headers, timeout=15)
        assert r.status_code == 404

    def test_non_owner_non_fullrole_403(self, auth_headers, labor_user):
        resp = self._mk(auth_headers)
        labor_hdr = {"Authorization": f"Bearer {labor_user['token']}"}
        r = requests.patch(f"{API}/responses/{resp['id']}/read", headers=labor_hdr, timeout=15)
        assert r.status_code == 403, f"Expected 403 got {r.status_code} {r.text}"
        r = requests.post(f"{API}/responses/{resp['id']}/archive", headers=labor_hdr, timeout=15)
        assert r.status_code == 403
        r = requests.delete(f"{API}/responses/{resp['id']}", headers=labor_hdr, timeout=15)
        assert r.status_code == 403

    def test_no_auth_401(self, auth_headers):
        resp = self._mk(auth_headers)
        for m, path in [
            ("patch", f"{API}/responses/{resp['id']}/read"),
            ("patch", f"{API}/responses/{resp['id']}/unread"),
            ("post", f"{API}/responses/{resp['id']}/archive"),
            ("delete", f"{API}/responses/{resp['id']}"),
        ]:
            r = requests.request(m, path, timeout=15)
            assert r.status_code in (401, 403), f"{m} {path} => {r.status_code}"


# ============================================================
# 7. Project summary PATCH
# ============================================================
class TestProjectSummaryPatch:
    def test_set_and_clear_summary(self, auth_headers):
        rep, pid, _ = _create_report_with_projects(auth_headers)
        new_summary = "Virtual layout: 2 coats, trim BM white, 3-day job"

        r = requests.patch(
            f"{API}/reports/{rep['id']}/projects/{pid}/summary",
            headers=auth_headers,
            json={"summary": new_summary},
            timeout=15,
        )
        assert r.status_code == 200, f"PATCH summary failed: {r.text}"
        updated = r.json()
        matched = next((p for p in updated["projects"] if p["id"] == pid), None)
        assert matched is not None
        assert matched["summary"] == new_summary

        # Clear with empty string → stores null
        r2 = requests.patch(
            f"{API}/reports/{rep['id']}/projects/{pid}/summary",
            headers=auth_headers,
            json={"summary": ""},
            timeout=15,
        )
        assert r2.status_code == 200
        cleared = next((p for p in r2.json()["projects"] if p["id"] == pid), None)
        assert cleared["summary"] is None

    def test_unknown_project_id_404(self, auth_headers):
        rep, _, _ = _create_report_with_projects(auth_headers)
        r = requests.patch(
            f"{API}/reports/{rep['id']}/projects/not-real-pid/summary",
            headers=auth_headers,
            json={"summary": "x"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_max_length_1000(self, auth_headers):
        rep, pid, _ = _create_report_with_projects(auth_headers)
        huge = "x" * 1001
        r = requests.patch(
            f"{API}/reports/{rep['id']}/projects/{pid}/summary",
            headers=auth_headers,
            json={"summary": huge},
            timeout=15,
        )
        assert r.status_code == 422, f"Expected 422 for >1000 chars, got {r.status_code}"

    def test_requires_auth(self, auth_headers):
        rep, pid, _ = _create_report_with_projects(auth_headers)
        r = requests.patch(
            f"{API}/reports/{rep['id']}/projects/{pid}/summary",
            json={"summary": "no auth"},
            timeout=15,
        )
        assert r.status_code in (401, 403)


# ============================================================
# 8. Regression — legacy /reports, draft lifecycle still work
# ============================================================
class TestRegression:
    def test_get_reports_still_works(self, auth_headers):
        r = requests.get(f"{API}/reports", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_legacy_post_reports_has_summary_field_default_null(self, auth_headers):
        rep, pid, _ = _create_report_with_projects(auth_headers, flagged=False)
        proj = next((p for p in rep["projects"] if p["id"] == pid), None)
        assert proj is not None
        # new field exists and defaults to null
        assert "summary" in proj
        assert proj["summary"] is None

    def test_draft_lifecycle_still_works(self, auth_headers):
        # ensure clean
        requests.delete(f"{API}/reports/draft", headers=auth_headers, timeout=15)
        # GET today → null
        r = requests.get(f"{API}/reports/draft/today", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json() is None

        # PUT draft
        payload = {
            "highlights": "TEST_IT21 draft hl",
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
        r = requests.put(f"{API}/reports/draft", headers=auth_headers, json=payload, timeout=20)
        assert r.status_code == 200
        draft = r.json()
        assert draft["status"] == "draft"

        # GET today returns the draft
        r = requests.get(f"{API}/reports/draft/today", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == draft["id"]

        # DELETE draft
        r = requests.delete(f"{API}/reports/draft", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        r = requests.get(f"{API}/reports/draft/today", headers=auth_headers, timeout=15)
        assert r.json() is None
