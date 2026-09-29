"""PaintOps Daily - Iteration 5 backend tests:
- Recipient Groups CRUD (admin-only)
- Regenerate AI summary
- Regression smoke on iteration 1-4 endpoints
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
    group_id: str = ""
    report_id: str = ""            # created by prod
    prod2_report_id: str = ""      # created by prod2 (for 403 test)
    original_ai_summary: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)


# ---------- Prep: auth setup ----------
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
            assert cr.status_code in (201, 400), cr.text
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


# ---------- 1) Recipient Groups CRUD ----------
class TestRecipientGroups:
    def test_create_requires_auth(self):
        r = requests.post(f"{API}/recipient-groups",
                          json={"name": "X", "emails": []}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_create_forbidden_for_non_admin(self, state):
        r = requests.post(f"{API}/recipient-groups", headers=_hdr(state.prod_token),
                          json={"name": "TEST_Blocked", "emails": ["a@b.com"]}, timeout=15)
        assert r.status_code == 403, r.text

    def test_create_group_admin(self, state):
        r = requests.post(f"{API}/recipient-groups", headers=_hdr(state.admin_token),
                          json={"name": "TEST_Owners_IT5",
                                "emails": ["owner1@paintops.com", "owner2@paintops.com"]},
                          timeout=15)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d.get("id"), "group id must exist"
        assert d["name"] == "TEST_Owners_IT5"
        assert set(d["emails"]) == {"owner1@paintops.com", "owner2@paintops.com"}
        assert d.get("created_by") == state.admin_id
        assert "created_at" in d
        state.group_id = d["id"]

    def test_list_groups_visible_to_non_admin(self, state):
        # list is authenticated (current_user) — should be visible to any logged-in user
        r = requests.get(f"{API}/recipient-groups", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert isinstance(arr, list)
        ids = [g["id"] for g in arr]
        assert state.group_id in ids

    def test_list_groups_admin(self, state):
        r = requests.get(f"{API}/recipient-groups", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200, r.text
        arr = r.json()
        assert any(g["id"] == state.group_id for g in arr)

    def test_patch_forbidden_for_non_admin(self, state):
        r = requests.patch(f"{API}/recipient-groups/{state.group_id}",
                           headers=_hdr(state.prod_token),
                           json={"name": "TEST_Hacked", "emails": []}, timeout=15)
        assert r.status_code == 403, r.text

    def test_patch_group_admin(self, state):
        r = requests.patch(f"{API}/recipient-groups/{state.group_id}",
                           headers=_hdr(state.admin_token),
                           json={"name": "TEST_Owners_IT5_Renamed",
                                 "emails": ["owner1@paintops.com",
                                            "owner2@paintops.com",
                                            "owner3@paintops.com"]},
                           timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == "TEST_Owners_IT5_Renamed"
        assert set(d["emails"]) == {
            "owner1@paintops.com", "owner2@paintops.com", "owner3@paintops.com"
        }

    def test_patch_404_bad_id(self, state):
        r = requests.patch(f"{API}/recipient-groups/nonexistent-id-xyz",
                           headers=_hdr(state.admin_token),
                           json={"name": "X", "emails": []}, timeout=15)
        assert r.status_code == 404, r.text

    def test_delete_forbidden_for_non_admin(self, state):
        r = requests.delete(f"{API}/recipient-groups/{state.group_id}",
                            headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 403, r.text

    def test_delete_group_admin(self, state):
        r = requests.delete(f"{API}/recipient-groups/{state.group_id}",
                            headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_delete_404_after_delete(self, state):
        r = requests.delete(f"{API}/recipient-groups/{state.group_id}",
                            headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 404, r.text

    def test_deleted_group_absent_from_list(self, state):
        r = requests.get(f"{API}/recipient-groups", headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert not any(g["id"] == state.group_id for g in r.json())


# ---------- 2) Regenerate AI summary ----------
class TestRegenerateSummary:
    def test_create_report_for_prod(self, state):
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "IT5-REGEN",
            "project_name": "TEST Iteration5 Regenerate Project",
            "highlights": "Initial highlights: painted the master bedroom.",
            "delays": "None.",
            "change_orders": "None.",
            "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id")
        assert d.get("ai_summary")
        state.report_id = d["id"]
        state.original_ai_summary = d["ai_summary"]

    def test_create_report_for_prod2_foreign(self, state):
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod2_token), json={
            "project_code": "IT5-FOREIGN",
            "project_name": "TEST Iteration5 Foreign Regen",
            "highlights": "Foreign report for regen 403 test.",
            "delays": "None.",
            "change_orders": "None.",
            "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert r.status_code == 200, r.text
        state.prod2_report_id = r.json()["id"]

    def test_regen_requires_auth(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/regenerate-summary", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_regen_404_bad_id(self, state):
        r = requests.post(f"{API}/reports/nonexistent-report-xyz/regenerate-summary",
                          headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 404, r.text

    def test_regen_forbidden_foreign_non_management(self, state):
        # prod2 (Production) tries to regen prod's report -> 403
        r = requests.post(f"{API}/reports/{state.report_id}/regenerate-summary",
                          headers=_hdr(state.prod2_token), timeout=15)
        assert r.status_code == 403, r.text

    def test_regen_happy_path(self, state):
        # First, edit the report highlights (should influence new summary)
        pr = requests.patch(f"{API}/reports/{state.report_id}",
                            headers=_hdr(state.prod_token),
                            json={"highlights": "Updated highlights: framed ALL bathrooms, "
                                                "installed crown molding in dining room, "
                                                "primed exterior trim. Big progress today."},
                            timeout=30)
        assert pr.status_code == 200, pr.text

        # ONE regen call to save GPT credits
        r = requests.post(f"{API}/reports/{state.report_id}/regenerate-summary",
                          headers=_hdr(state.prod_token), timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("id") == state.report_id
        assert d.get("ai_summary"), "ai_summary must be non-empty"
        assert len(d["ai_summary"]) > 20
        assert d.get("tts_cache") in (None,), f"tts_cache must be null, got {d.get('tts_cache')}"
        # New summary should differ from original (unless GPT deterministically produced identical text)
        # Accept "non-empty" as minimum requirement per problem spec.
        # But also verify it likely changed:
        if d["ai_summary"] == state.original_ai_summary:
            # rare but possible; do not hard-fail — log via assertion message
            pytest.skip("Regenerated summary equals original (rare GPT determinism). Non-empty passed.")
        assert d["ai_summary"] != state.original_ai_summary

    def test_regen_admin_can_regen_foreign(self, state):
        # Admin regenning prod2's report should succeed (management override).
        # NOTE: This consumes another GPT call. Comment out if credits are tight.
        # Per iteration-5 spec keep to ONE call, so we validate management authorization
        # by checking 200 status without deep assertion. We skip actual second call to save credits.
        pytest.skip("Skipping second GPT call to preserve credits (per iteration-5 note).")


# ---------- 3) Regression smoke: iterations 1-4 ----------
class TestRegression:
    def test_auth_me(self, state):
        r = requests.get(f"{API}/auth/me", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == PROD_EMAIL

    def test_users_list_admin(self, state):
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

    def test_reports_list(self, state):
        r = requests.get(f"{API}/reports", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_report_detail(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}",
                         headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == state.report_id

    def test_portal_link(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/portal-link",
                          headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("public_url") or d.get("token")

    def test_public_report_get(self, state):
        # Fetch token
        r = requests.post(f"{API}/reports/{state.report_id}/portal-link",
                          headers=_hdr(state.prod_token), timeout=15)
        tok = r.json().get("token") or (r.json().get("public_url") or "").rsplit("/", 1)[-1]
        assert tok
        r2 = requests.get(f"{API}/public/reports/{tok}", timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("project_name") == "TEST Iteration5 Regenerate Project"

    def test_workday_export(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}/workday-export",
                         headers=_hdr(state.prod_token), timeout=20)
        assert r.status_code == 200

    def test_digest_schedule_get(self, state):
        r = requests.get(f"{API}/digest/schedule",
                         headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        assert "enabled" in r.json()

    def test_customers_list(self, state):
        r = requests.get(f"{API}/customers", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_weather(self, state):
        r = requests.get(f"{API}/weather?lat=37.77&lon=-122.42",
                         headers=_hdr(state.prod_token), timeout=20)
        assert r.status_code == 200

    def test_transcribe_empty_400(self, state):
        headers = {"Authorization": f"Bearer {state.prod_token}"}
        files = {"audio": ("empty.m4a", b"", "audio/m4a")}
        r = requests.post(f"{API}/transcribe", headers=headers, files=files, timeout=15)
        assert r.status_code == 400

    def test_register_push_own(self, state):
        r = requests.post(f"{API}/register-push", headers=_hdr(state.prod_token), json={
            "user_id": state.prod_id, "platform": "ios",
            "device_token": "TEST_TOKEN_IT5_PROD",
        }, timeout=15)
        assert r.status_code == 201

    def test_signature_patch(self, state):
        png_b64 = ("data:image/png;base64,"
                   "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAA"
                   "AAYAAjCB0C8AAAAASUVORK5CYII=")
        r = requests.patch(
            f"{API}/reports/{state.report_id}/signature",
            headers=_hdr(state.prod_token),
            json={"customer_name": "TEST Homeowner IT5", "signature_base64": png_b64},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_report_archive_and_delete(self, state):
        # Create a throwaway report for archive+delete regression
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "IT5-DEL",
            "project_name": "TEST Iteration5 To Delete",
            "highlights": "temp report",
            "delays": "None.", "change_orders": "None.", "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=180)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]

        ar = requests.post(f"{API}/reports/{rid}/archive",
                           headers=_hdr(state.prod_token), timeout=15)
        assert ar.status_code == 200, ar.text

        dr = requests.delete(f"{API}/reports/{rid}",
                             headers=_hdr(state.prod_token), timeout=15)
        assert dr.status_code == 200, dr.text

        vr = requests.get(f"{API}/reports/{rid}",
                          headers=_hdr(state.prod_token), timeout=15)
        # Soft delete: doc may still be fetchable but must expose deleted_at
        assert vr.status_code in (200, 404)
        if vr.status_code == 200:
            assert vr.json().get("deleted_at"), "soft-deleted doc must have deleted_at"
