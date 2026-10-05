"""
Iteration 22 backend tests:
  - Reply Threads: POST /api/responses/{response_id}/reply + GET .../thread
  - Inbox filter: list_responses + unread-count EXCLUDE direction='outbound' by default
  - Daily Mail Digest: GET/PUT /api/digest/mail-schedule, POST /api/digest/mail-send-now
  - Regression: iteration 20 drafts & iteration 21 responses/public portal still work

Run serially (shared admin user, shared mail_digest_schedule singleton):
  pytest /app/backend/tests/test_iteration22_reply_threads_mail_digest.py -v -o addopts=""
"""

import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

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
    """Non-FULL_ROLES user (Labor) to test 403s."""
    email = f"test_it22_labor_{uuid.uuid4().hex[:6]}@paintops.com"
    password = "Labor@12345"
    r = requests.post(
        f"{API}/admin/users",
        headers=auth_headers,
        json={
            "email": email,
            "name": "IT22 Labor",
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

    if user_id:
        requests.delete(f"{API}/admin/users/{user_id}", headers=auth_headers, timeout=15)


def _create_report_with_projects(auth_headers):
    """POST /api/reports to create a submitted report with a flagged project."""
    pid_flagged = str(uuid.uuid4())
    projects = [
        {
            "id": pid_flagged,
            "project_code": "TEST_IT22_P1",
            "project_name": "TEST_IT22 Flagged Job",
            "customer_name": "ACME",
            "address": "123 Flagged St",
            "notes": "Fix hinge",
            "priority_flag": "Touch-Ups",
        },
    ]
    payload = {
        "highlights": "TEST_IT22 highlights",
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
    return r.json(), pid_flagged


def _mint_token(auth_headers, report_id):
    r = requests.post(
        f"{API}/reports/{report_id}/portal-link", headers=auth_headers, timeout=15,
    )
    assert r.status_code == 200, f"portal-link failed: {r.text}"
    return r.json()["token"]


def _create_inbound_reply(auth_headers, project_id=None, reporter_email="jane@example.com"):
    """Create a report + mint token + create an inbound (public) reply. Returns the reply doc."""
    rep, pid = _create_report_with_projects(auth_headers)
    token = _mint_token(auth_headers, rep["id"])
    payload = {
        "project_id": project_id or pid,
        "reporter_name": "External Jane",
        "reporter_email": reporter_email,
        "message": "Original inbound reply from external user.",
    }
    r = requests.post(f"{API}/public/reports/{token}/respond", json=payload, timeout=20)
    assert r.status_code == 200, f"respond failed: {r.text}"
    return rep, pid, r.json()


# ---------- autouse cleanup ----------
@pytest.fixture(autouse=True)
def _wipe_between_tests(auth_headers):
    yield
    # Wipe responses visible to admin (admin sees all) including outbound.
    try:
        r = requests.get(
            f"{API}/responses?include_archived=true&include_outbound=true",
            headers=auth_headers,
            timeout=15,
        )
        if r.status_code == 200:
            for item in r.json():
                requests.delete(
                    f"{API}/responses/{item['id']}", headers=auth_headers, timeout=10,
                )
    except Exception:
        pass
    # Reset mail-digest-schedule singleton so each test starts clean.
    try:
        requests.put(
            f"{API}/digest/mail-schedule",
            headers=auth_headers,
            json={"enabled": False, "hour": 7, "minute": 0},
            timeout=10,
        )
    except Exception:
        pass


# ============================================================
# 1. POST /api/responses/{response_id}/reply — owner reply back
# ============================================================
class TestOwnerReply:
    def test_reply_creates_outbound_with_correct_fields(self, auth_headers, admin_user):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        inbound_id = inbound["id"]
        # Precondition: inbound reply is unread
        assert inbound["read_at"] is None
        assert inbound.get("direction", "inbound") == "inbound"

        r = requests.post(
            f"{API}/responses/{inbound_id}/reply",
            headers=auth_headers,
            json={"message": "Thanks — crew booked for 9am."},
            timeout=20,
        )
        assert r.status_code == 200, f"reply failed: {r.status_code} {r.text}"
        d = r.json()
        assert d["direction"] == "outbound"
        assert d["parent_id"] == inbound_id
        assert d["author_user_id"] == admin_user["id"]
        assert d["reporter_name"] == admin_user["name"]
        assert d["reporter_email"] is None
        # Own replies are implicitly read
        assert d["read_at"] is not None
        # Project info copied from parent inbound reply
        assert d["project_id"] == pid
        assert d["project_label"] == "TEST_IT22 Flagged Job"
        assert d["project_flag"] == "Touch-Ups"
        assert d["report_id"] == rep["id"]
        assert d["report_user_id"] == admin_user["id"]
        assert d["message"] == "Thanks — crew booked for 9am."
        # email_delivered is boolean (may be True if Resend accepted, False otherwise — don't assert exact)
        assert isinstance(d["email_delivered"], bool)

    def test_reply_marks_parent_as_read(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        inbound_id = inbound["id"]
        assert inbound["read_at"] is None
        r = requests.post(
            f"{API}/responses/{inbound_id}/reply",
            headers=auth_headers,
            json={"message": "Replying — this should mark parent read."},
            timeout=20,
        )
        assert r.status_code == 200
        # Fetch inbound via list (admin) and verify parent is now read
        lst = requests.get(
            f"{API}/responses?include_outbound=true", headers=auth_headers, timeout=15,
        )
        assert lst.status_code == 200
        parent = next((x for x in lst.json() if x["id"] == inbound_id), None)
        assert parent is not None, "parent inbound reply not found"
        assert parent["read_at"] is not None, "parent reply should be marked read"

    def test_reply_without_recipient_email_still_saves(self, auth_headers):
        # Inbound reply with no reporter_email → owner reply cannot email, but must still save
        rep, pid = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r = requests.post(
            f"{API}/public/reports/{token}/respond",
            json={"project_id": pid, "reporter_name": "Anonymous", "message": "no email given"},
            timeout=15,
        )
        assert r.status_code == 200
        inbound = r.json()
        assert inbound["reporter_email"] is None

        rr = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "Replying with no recipient email."},
            timeout=15,
        )
        assert rr.status_code == 200, f"reply failed: {rr.text}"
        d = rr.json()
        assert d["direction"] == "outbound"
        assert d["email_delivered"] is False

    def test_reply_from_outbound_child_resolves_to_root(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        inbound_id = inbound["id"]
        # First reply (child)
        r1 = requests.post(
            f"{API}/responses/{inbound_id}/reply",
            headers=auth_headers,
            json={"message": "First outbound reply."},
            timeout=15,
        )
        assert r1.status_code == 200
        child_id = r1.json()["id"]
        assert r1.json()["parent_id"] == inbound_id

        # Reply on the outbound child — should still link to the same root (inbound_id)
        r2 = requests.post(
            f"{API}/responses/{child_id}/reply",
            headers=auth_headers,
            json={"message": "Second outbound reply (from child)."},
            timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json()["parent_id"] == inbound_id, "both outbound replies should share the inbound root as parent"

    def test_reply_404_for_bad_id(self, auth_headers):
        r = requests.post(
            f"{API}/responses/does-not-exist-xyz/reply",
            headers=auth_headers,
            json={"message": "hello"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_reply_422_for_empty_message(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": ""},
            timeout=15,
        )
        assert r.status_code == 422

    def test_reply_403_for_non_owner_labor(self, auth_headers, labor_user):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        labor_headers = {
            "Authorization": f"Bearer {labor_user['token']}",
            "Content-Type": "application/json",
        }
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=labor_headers,
            json={"message": "I shouldn't be allowed."},
            timeout=15,
        )
        assert r.status_code == 403


# ============================================================
# 2. GET /api/responses/{response_id}/thread
# ============================================================
class TestResponseThread:
    def test_thread_returns_parent_plus_children_sorted(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        inbound_id = inbound["id"]
        # Create 2 outbound replies
        for i in range(2):
            r = requests.post(
                f"{API}/responses/{inbound_id}/reply",
                headers=auth_headers,
                json={"message": f"Outbound reply {i}"},
                timeout=15,
            )
            assert r.status_code == 200

        # Fetch thread
        r = requests.get(
            f"{API}/responses/{inbound_id}/thread", headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        thread = r.json()
        assert len(thread) == 3, f"expected 3 docs (1 inbound + 2 outbound), got {len(thread)}"
        # Sorted ASC by created_at: inbound first, then outbound children in order
        assert thread[0]["id"] == inbound_id
        assert thread[0]["direction"] == "inbound"
        assert thread[1]["direction"] == "outbound"
        assert thread[2]["direction"] == "outbound"
        # Monotonic non-decreasing
        assert thread[0]["created_at"] <= thread[1]["created_at"] <= thread[2]["created_at"]

    def test_thread_from_outbound_child_returns_same_full_thread(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        r1 = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "child outbound"},
            timeout=15,
        )
        assert r1.status_code == 200
        child_id = r1.json()["id"]

        r = requests.get(
            f"{API}/responses/{child_id}/thread", headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        thread = r.json()
        # Must still include inbound root + outbound child
        ids = [t["id"] for t in thread]
        assert inbound["id"] in ids
        assert child_id in ids

    def test_thread_404_for_bad_id(self, auth_headers):
        r = requests.get(
            f"{API}/responses/does-not-exist/thread", headers=auth_headers, timeout=15,
        )
        assert r.status_code == 404

    def test_thread_403_for_non_owner_labor(self, auth_headers, labor_user):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        labor_headers = {"Authorization": f"Bearer {labor_user['token']}"}
        r = requests.get(
            f"{API}/responses/{inbound['id']}/thread",
            headers=labor_headers,
            timeout=15,
        )
        assert r.status_code == 403


# ============================================================
# 3. Inbox filter — outbound excluded by default
# ============================================================
class TestInboxOutboundFilter:
    def test_list_responses_default_excludes_outbound(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        rr = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "owner reply"},
            timeout=15,
        )
        assert rr.status_code == 200
        outbound_id = rr.json()["id"]

        # Default — inbound only
        lst = requests.get(f"{API}/responses", headers=auth_headers, timeout=15)
        assert lst.status_code == 200
        items = lst.json()
        ids = {x["id"] for x in items}
        assert inbound["id"] in ids
        assert outbound_id not in ids, "outbound reply must be excluded by default"
        for x in items:
            assert x.get("direction", "inbound") != "outbound"

    def test_list_responses_include_outbound_true(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        rr = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "owner reply"},
            timeout=15,
        )
        assert rr.status_code == 200
        outbound_id = rr.json()["id"]

        lst = requests.get(
            f"{API}/responses?include_outbound=true", headers=auth_headers, timeout=15,
        )
        assert lst.status_code == 200
        ids = {x["id"] for x in lst.json()}
        assert inbound["id"] in ids
        assert outbound_id in ids

    def test_unread_count_excludes_outbound(self, auth_headers):
        # Baseline count
        base = requests.get(f"{API}/responses/unread-count", headers=auth_headers, timeout=15).json()["count"]

        rep, pid, inbound = _create_inbound_reply(auth_headers)
        # Now +1 unread inbound
        c1 = requests.get(f"{API}/responses/unread-count", headers=auth_headers, timeout=15).json()["count"]
        assert c1 == base + 1

        # Owner reply → inbound gets marked read AND outbound is own (read)
        rr = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "owner reply"},
            timeout=15,
        )
        assert rr.status_code == 200
        # Unread count should drop back to baseline — parent is now read, outbound is read-and-outbound
        c2 = requests.get(f"{API}/responses/unread-count", headers=auth_headers, timeout=15).json()["count"]
        assert c2 == base, f"expected {base} unread after owner reply, got {c2}"

        # Now explicitly mark parent unread again. The outbound owner reply has read_at set,
        # but even if it were unread, unread_response_count MUST exclude outbound.
        ur = requests.patch(
            f"{API}/responses/{inbound['id']}/unread", headers=auth_headers, timeout=15,
        )
        assert ur.status_code == 200
        c3 = requests.get(f"{API}/responses/unread-count", headers=auth_headers, timeout=15).json()["count"]
        assert c3 == base + 1, "unread count should count the inbound-only (not outbound)"


# ============================================================
# 4. GET /api/digest/mail-schedule — admin only
# ============================================================
class TestGetMailSchedule:
    def test_defaults_when_no_doc(self, auth_headers):
        # Our autouse teardown PUTs enabled=False/hour=7/minute=0 — effectively a reset.
        r = requests.get(f"{API}/digest/mail-schedule", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is False
        assert d["hour"] == 7
        assert d["minute"] == 0

    def test_non_admin_403(self, labor_user):
        headers = {"Authorization": f"Bearer {labor_user['token']}"}
        r = requests.get(f"{API}/digest/mail-schedule", headers=headers, timeout=15)
        assert r.status_code == 403


# ============================================================
# 5. PUT /api/digest/mail-schedule — admin only
# ============================================================
class TestPutMailSchedule:
    def test_set_schedule_persists(self, auth_headers):
        r = requests.put(
            f"{API}/digest/mail-schedule",
            headers=auth_headers,
            json={"enabled": True, "hour": 8, "minute": 30},
            timeout=15,
        )
        assert r.status_code == 200, f"PUT failed: {r.text}"
        d = r.json()
        assert d["ok"] is True
        sched = d["schedule"]
        assert sched["enabled"] is True
        assert sched["hour"] == 8
        assert sched["minute"] == 30

        # GET must reflect the change
        g = requests.get(f"{API}/digest/mail-schedule", headers=auth_headers, timeout=15)
        assert g.status_code == 200
        gd = g.json()
        assert gd["enabled"] is True
        assert gd["hour"] == 8
        assert gd["minute"] == 30

    def test_hour_24_returns_422(self, auth_headers):
        r = requests.put(
            f"{API}/digest/mail-schedule",
            headers=auth_headers,
            json={"enabled": True, "hour": 24, "minute": 0},
            timeout=15,
        )
        assert r.status_code == 422

    def test_minute_60_returns_422(self, auth_headers):
        r = requests.put(
            f"{API}/digest/mail-schedule",
            headers=auth_headers,
            json={"enabled": True, "hour": 7, "minute": 60},
            timeout=15,
        )
        assert r.status_code == 422

    def test_non_admin_403(self, labor_user):
        headers = {
            "Authorization": f"Bearer {labor_user['token']}",
            "Content-Type": "application/json",
        }
        r = requests.put(
            f"{API}/digest/mail-schedule",
            headers=headers,
            json={"enabled": True, "hour": 7, "minute": 0},
            timeout=15,
        )
        assert r.status_code == 403


# ============================================================
# 6. POST /api/digest/mail-send-now — fire _run_mail_digest immediately
# ============================================================
class TestSendMailDigestNow:
    def test_no_unread_returns_zeros(self, auth_headers):
        # Clean slate (autouse teardown already wipes responses after each test),
        # so start by ensuring there are no unread inbound replies first.
        lst = requests.get(
            f"{API}/responses?include_archived=true&include_outbound=true",
            headers=auth_headers,
            timeout=15,
        )
        if lst.status_code == 200:
            for item in lst.json():
                requests.delete(
                    f"{API}/responses/{item['id']}", headers=auth_headers, timeout=10,
                )

        r = requests.post(f"{API}/digest/mail-send-now", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"mail-send-now failed: {r.text}"
        d = r.json()
        assert d["ok"] is True
        assert d["emails_sent"] == 0
        assert d["owners"] == 0
        assert d["replies"] == 0

    def test_with_unread_sends_digest(self, auth_headers, admin_user):
        # Admin owns the report → admin has an email → digest should attempt to send.
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        assert inbound["read_at"] is None

        r = requests.post(f"{API}/digest/mail-send-now", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"mail-send-now failed: {r.text}"
        d = r.json()
        assert d["ok"] is True
        assert d["owners"] >= 1, f"expected at least 1 owner, got {d}"
        assert d["replies"] >= 1, f"expected at least 1 reply, got {d}"
        # emails_sent depends on Resend accepting the admin email — don't assert >=1 strictly,
        # but it must be an int in [0, owners].
        assert isinstance(d["emails_sent"], int)
        assert 0 <= d["emails_sent"] <= d["owners"]

    def test_non_admin_403(self, labor_user):
        headers = {"Authorization": f"Bearer {labor_user['token']}"}
        r = requests.post(f"{API}/digest/mail-send-now", headers=headers, timeout=15)
        assert r.status_code == 403


# ============================================================
# 7. Regression — iteration 20 & 21 endpoints
# ============================================================
class TestRegression:
    def test_draft_get_put_submit_delete(self, auth_headers):
        # GET draft/today (initial — may be empty / 404 if none)
        r = requests.get(f"{API}/reports/draft/today", headers=auth_headers, timeout=15)
        assert r.status_code in (200, 404)
        # PUT draft
        pid = str(uuid.uuid4())
        payload = {
            "highlights": "TEST_IT22 draft",
            "delays": "",
            "change_orders": "",
            "material_notes": "",
            "include_weather": False,
            "include_visits": False,
            "include_breaks": False,
            "include_sms": False,
            "recipient_emails": [],
            "projects": [
                {
                    "id": pid,
                    "project_code": "TEST_IT22_DRAFT",
                    "project_name": "TEST_IT22 Draft Job",
                    "customer_name": "ACME",
                    "address": "1 draft st",
                    "notes": "draft notes",
                    "priority_flag": None,
                }
            ],
        }
        pr = requests.put(f"{API}/reports/draft", headers=auth_headers, json=payload, timeout=15)
        assert pr.status_code == 200, pr.text
        # DELETE draft
        dr = requests.delete(f"{API}/reports/draft", headers=auth_headers, timeout=15)
        assert dr.status_code == 200

    def test_public_html_portal_and_respond(self, auth_headers):
        rep, pid = _create_report_with_projects(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        # HTML portal
        hp = requests.get(f"{API}/public/reports/{token}", timeout=15)
        assert hp.status_code == 200
        assert "text/html" in hp.headers.get("content-type", "").lower()
        # Public respond (inbound)
        rr = requests.post(
            f"{API}/public/reports/{token}/respond",
            json={"project_id": pid, "message": "regression inbound reply"},
            timeout=15,
        )
        assert rr.status_code == 200
        d = rr.json()
        assert d["message"] == "regression inbound reply"
        assert d.get("direction", "inbound") == "inbound"

    def test_project_summary_patch(self, auth_headers):
        rep, pid = _create_report_with_projects(auth_headers)
        pr = requests.patch(
            f"{API}/reports/{rep['id']}/projects/{pid}/summary",
            headers=auth_headers,
            json={"summary": "TEST_IT22 patched summary"},
            timeout=15,
        )
        assert pr.status_code == 200, pr.text
        updated = pr.json()
        proj = next((p for p in updated["projects"] if p["id"] == pid), None)
        assert proj is not None
        assert proj.get("summary") == "TEST_IT22 patched summary"

    def test_response_crud_read_unread_archive_delete(self, auth_headers):
        rep, pid, inbound = _create_inbound_reply(auth_headers)
        iid = inbound["id"]
        # Mark read
        r1 = requests.patch(f"{API}/responses/{iid}/read", headers=auth_headers, timeout=15)
        assert r1.status_code == 200
        assert r1.json()["read_at"] is not None
        # Mark unread
        r2 = requests.patch(f"{API}/responses/{iid}/unread", headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["read_at"] is None
        # Archive
        r3 = requests.post(f"{API}/responses/{iid}/archive", headers=auth_headers, timeout=15)
        assert r3.status_code == 200
        assert r3.json()["archived"] is True
        # Delete
        r4 = requests.delete(f"{API}/responses/{iid}", headers=auth_headers, timeout=15)
        assert r4.status_code == 200
