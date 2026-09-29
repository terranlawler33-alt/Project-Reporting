"""PaintOps Daily - Iteration 3 backend tests: edit/archive/delete report,
portal link, digest schedule, photo upload validation, files auth."""
import io
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


class State:
    admin_token: str = ""
    prod_token: str = ""
    prod_id: str = ""
    report_id: str = ""
    other_report_id: str = ""
    portal_token: str = ""
    visit_id: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _auth_hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- Prep ----------
class TestPrep:
    def test_login_admin(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200, r.text
        state.admin_token = r.json()["access_token"]

    def test_login_or_create_prod(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": PROD_EMAIL, "password": PROD_PASSWORD}, timeout=15)
        if r.status_code != 200:
            cr = requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
                "email": PROD_EMAIL, "password": PROD_PASSWORD, "name": "Prod User",
                "role": "Production", "job_title": "Painter", "department": "Field",
                "job_code": "P-01", "is_admin": False,
            }, timeout=15)
            assert cr.status_code == 201, cr.text
            r = requests.post(f"{API}/auth/login",
                              json={"email": PROD_EMAIL, "password": PROD_PASSWORD}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        state.prod_token = data["access_token"]
        state.prod_id = data["user"]["id"]

    def test_create_reports(self, state):
        # Report to edit/archive/portal
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "TEST-IT3-A", "project_name": "TEST Iteration3 A",
            "highlights": "Initial highlights.", "delays": "None.",
            "change_orders": "None.", "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=120)
        assert r.status_code == 200, r.text
        state.report_id = r.json()["id"]

        # Second report used for delete
        r2 = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "TEST-IT3-B", "project_name": "TEST Iteration3 B",
            "highlights": "will delete.", "delays": "None.",
            "change_orders": "None.", "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=120)
        assert r2.status_code == 200, r2.text
        state.other_report_id = r2.json()["id"]


# ---------- Report edit ----------
class TestReportEdit:
    def test_patch_report(self, state):
        r = requests.patch(f"{API}/reports/{state.report_id}",
                           headers=_hdr(state.prod_token),
                           json={"highlights": "EDITED highlights", "delays": "EDITED delays"},
                           timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["highlights"] == "EDITED highlights"
        assert d["delays"] == "EDITED delays"

    def test_patch_report_persisted(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}",
                        headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["highlights"] == "EDITED highlights"

    def test_patch_report_forbidden_for_other_user(self, state):
        # Create a second prod-like user to test forbidden edit
        email = "prod2@paintops.com"
        # Ensure user
        requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
            "email": email, "password": "Prod@12345", "name": "Prod2",
            "role": "Production", "job_title": "Painter", "department": "Field",
            "job_code": "P-02", "is_admin": False,
        }, timeout=15)
        lr = requests.post(f"{API}/auth/login",
                           json={"email": email, "password": "Prod@12345"}, timeout=15)
        if lr.status_code != 200:
            pytest.skip("cannot create secondary prod user")
        tok = lr.json()["access_token"]
        r = requests.patch(f"{API}/reports/{state.report_id}",
                           headers=_hdr(tok),
                           json={"highlights": "hacked"}, timeout=15)
        assert r.status_code == 403, r.text


# ---------- Archive / Unarchive ----------
class TestArchive:
    def test_archive(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/archive",
                          headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_list_excludes_archived(self, state):
        r = requests.get(f"{API}/reports", headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert state.report_id not in ids

    def test_list_include_archived(self, state):
        r = requests.get(f"{API}/reports?include_archived=true",
                        headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert state.report_id in ids

    def test_unarchive(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/unarchive",
                          headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/reports", headers=_auth_hdr(state.prod_token), timeout=15)
        assert state.report_id in [d["id"] for d in r2.json()]


# ---------- Soft Delete ----------
class TestSoftDelete:
    def test_delete_report(self, state):
        r = requests.delete(f"{API}/reports/{state.other_report_id}",
                            headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_delete_report_hidden_from_list(self, state):
        r = requests.get(f"{API}/reports", headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert state.other_report_id not in ids

    def test_delete_hidden_even_with_include_archived(self, state):
        r = requests.get(f"{API}/reports?include_archived=true",
                        headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        assert state.other_report_id not in [d["id"] for d in r.json()]


# ---------- Portal Link ----------
class TestPortalLink:
    def test_create_portal_link(self, state):
        r = requests.post(f"{API}/reports/{state.report_id}/portal-link",
                          headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("token")
        state.portal_token = d["token"]

    def test_public_report_no_auth(self, state):
        # No Authorization header - should still work
        r = requests.get(f"{API}/public/reports/{state.portal_token}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # limited public view
        assert "ai_summary" in d
        assert "report_date" in d
        assert "author_name" in d
        # Should NOT contain user_id or emails
        assert "user_id" not in d
        assert "recipient_emails" not in d

    def test_public_report_bad_token(self):
        r = requests.get(f"{API}/public/reports/notarealtoken12345", timeout=15)
        assert r.status_code == 404

    def test_revoke_portal_link(self, state):
        r = requests.delete(f"{API}/reports/{state.report_id}/portal-link",
                            headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200
        # Now public GET should 404
        r2 = requests.get(f"{API}/public/reports/{state.portal_token}", timeout=15)
        assert r2.status_code == 404


# ---------- Digest Schedule ----------
class TestDigestSchedule:
    def test_get_schedule_admin(self, state):
        r = requests.get(f"{API}/digest/schedule",
                        headers=_auth_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "enabled" in d
        assert "hour" in d
        assert "minute" in d
        assert "day_of_week" in d

    def test_get_schedule_non_admin_forbidden(self, state):
        r = requests.get(f"{API}/digest/schedule",
                        headers=_auth_hdr(state.prod_token), timeout=15)
        assert r.status_code == 403

    def test_put_schedule_admin(self, state):
        r = requests.put(f"{API}/digest/schedule",
                         headers=_hdr(state.admin_token),
                         json={
                             "enabled": True,
                             "hour": 8,
                             "minute": 30,
                             "day_of_week": "mon",
                             "recipient_emails": ["delivered@resend.dev"],
                         },
                         timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d["schedule"]["enabled"] is True
        assert d["schedule"]["hour"] == 8
        assert d["schedule"]["minute"] == 30
        assert d["schedule"]["day_of_week"] == "mon"

    def test_put_schedule_persisted(self, state):
        r = requests.get(f"{API}/digest/schedule",
                        headers=_auth_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True
        assert d["hour"] == 8
        assert d["minute"] == 30
        assert d["day_of_week"] == "mon"
        assert "delivered@resend.dev" in d["recipient_emails"]

    def test_put_schedule_non_admin_forbidden(self, state):
        r = requests.put(f"{API}/digest/schedule",
                         headers=_hdr(state.prod_token),
                         json={
                             "enabled": False, "hour": 8, "minute": 0,
                             "day_of_week": "tue", "recipient_emails": ["a@b.com"],
                         }, timeout=15)
        assert r.status_code == 403


# ---------- Photo upload validation (do NOT hit real object storage) ----------
class TestPhotoUploadValidation:
    def test_photos_bad_visit_404(self, state):
        headers = {"Authorization": f"Bearer {state.prod_token}"}
        files = {"photo": ("a.jpg", b"abc", "image/jpeg")}
        r = requests.post(f"{API}/visits/nonexistent-visit-id/photos",
                          headers=headers, files=files, timeout=15)
        assert r.status_code == 404, r.text

    def test_photos_empty_400(self, state):
        # Need real visit id owned by prod user
        vr = requests.post(f"{API}/visits", headers=_hdr(state.prod_token), json={
            "latitude": 40.0, "longitude": -74.0,
            "customer_name": "TEST_PhotoCust", "address": "1 Test Ave",
            "project_code": "TEST-PHOTO", "notes": "",
        }, timeout=15)
        assert vr.status_code == 200, vr.text
        state.visit_id = vr.json()["id"]

        headers = {"Authorization": f"Bearer {state.prod_token}"}
        files = {"photo": ("empty.jpg", b"", "image/jpeg")}
        r = requests.post(f"{API}/visits/{state.visit_id}/photos",
                          headers=headers, files=files, timeout=15)
        assert r.status_code == 400, r.text

    def test_photos_requires_auth(self, state):
        files = {"photo": ("a.jpg", b"abc", "image/jpeg")}
        r = requests.post(f"{API}/visits/{state.visit_id or 'x'}/photos",
                          files=files, timeout=15)
        assert r.status_code in (401, 403), r.text


# ---------- File retrieval auth (do NOT test real object retrieval) ----------
class TestFilesAuth:
    def test_files_requires_auth(self):
        r = requests.get(f"{API}/files/some/path.jpg", timeout=15)
        assert r.status_code == 401, r.text

    def test_files_bad_token(self):
        r = requests.get(f"{API}/files/some/path.jpg",
                        headers={"Authorization": "Bearer notavalidtoken"}, timeout=15)
        assert r.status_code == 401
