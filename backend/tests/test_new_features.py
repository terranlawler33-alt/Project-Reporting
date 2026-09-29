"""PaintOps Daily - Backend tests for new features:
customers, weekly digest, signature capture, transcribe validation."""
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
    customer_id: str = ""
    report_id: str = ""


@pytest.fixture(scope="module")
def state():
    return State()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Prep ----------
class TestPrep:
    def test_login_admin(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=15)
        assert r.status_code == 200, r.text
        state.admin_token = r.json()["access_token"]

    def test_login_or_create_prod(self, state):
        r = requests.post(f"{API}/auth/login",
                          json={"email": PROD_EMAIL, "password": PROD_PASSWORD},
                          timeout=15)
        if r.status_code != 200:
            # Create it
            cr = requests.post(f"{API}/admin/users", headers=_hdr(state.admin_token), json={
                "email": PROD_EMAIL, "password": PROD_PASSWORD, "name": "Prod User",
                "role": "Production", "job_title": "Painter", "department": "Field",
                "job_code": "P-01", "is_admin": False,
            }, timeout=15)
            assert cr.status_code == 201, cr.text
            r = requests.post(f"{API}/auth/login",
                              json={"email": PROD_EMAIL, "password": PROD_PASSWORD},
                              timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        state.prod_token = data["access_token"]
        state.prod_id = data["user"]["id"]


# ---------- Customer Directory ----------
class TestCustomers:
    def test_create_customer_auth(self, state):
        r = requests.post(f"{API}/customers", headers=_hdr(state.prod_token), json={
            "name": "TEST_Acme Painters",
            "address": "123 Main St",
            "phone": "555-1212",
            "email": "acme@example.com",
            "project_code": "ACME-01",
            "notes": "TEST customer",
        }, timeout=15)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "TEST_Acme Painters"
        assert d["address"] == "123 Main St"
        assert d["project_code"] == "ACME-01"
        assert "id" in d and d["id"]
        assert d["created_by"] == state.prod_id
        state.customer_id = d["id"]

    def test_create_customer_requires_auth(self):
        r = requests.post(f"{API}/customers", json={"name": "NoAuth"}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_list_customers(self, state):
        r = requests.get(f"{API}/customers", headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        docs = r.json()
        assert isinstance(docs, list)
        assert any(c["id"] == state.customer_id for c in docs)

    def test_delete_customer_non_admin_forbidden(self, state):
        r = requests.delete(f"{API}/customers/{state.customer_id}",
                            headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 403, r.text

    def test_delete_customer_admin(self, state):
        # Create a throwaway customer to delete
        c = requests.post(f"{API}/customers", headers=_hdr(state.admin_token),
                          json={"name": "TEST_ToDelete"}, timeout=15)
        assert c.status_code == 201, c.text
        cid = c.json()["id"]
        r = requests.delete(f"{API}/customers/{cid}",
                            headers=_hdr(state.admin_token), timeout=15)
        assert r.status_code == 200, r.text
        # Verify gone
        listing = requests.get(f"{API}/customers", headers=_hdr(state.admin_token), timeout=15)
        assert not any(x["id"] == cid for x in listing.json())


# ---------- Transcribe validation (do NOT burn credits) ----------
class TestTranscribeValidation:
    def test_transcribe_requires_auth(self):
        files = {"audio": ("a.m4a", b"", "audio/m4a")}
        r = requests.post(f"{API}/transcribe", files=files, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_transcribe_empty_audio_400(self, state):
        headers = {"Authorization": f"Bearer {state.prod_token}"}
        files = {"audio": ("empty.m4a", b"", "audio/m4a")}
        r = requests.post(f"{API}/transcribe", headers=headers, files=files, timeout=15)
        assert r.status_code == 400, r.text

    def test_transcribe_bad_extension_415(self, state):
        headers = {"Authorization": f"Bearer {state.prod_token}"}
        files = {"audio": ("evil.txt", b"not audio", "text/plain")}
        r = requests.post(f"{API}/transcribe", headers=headers, files=files, timeout=15)
        assert r.status_code == 415, r.text


# ---------- Signature ----------
class TestSignature:
    def test_create_report_for_signature(self, state):
        r = requests.post(f"{API}/reports", headers=_hdr(state.prod_token), json={
            "project_code": "SIG-TEST",
            "project_name": "TEST Signature Project",
            "highlights": "TEST report for signature.",
            "delays": "None.",
            "change_orders": "None.",
            "material_notes": "None.",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }, timeout=120)
        assert r.status_code == 200, r.text
        state.report_id = r.json()["id"]
        assert state.report_id

    def test_patch_signature(self, state):
        # A tiny valid-ish base64 png (1x1 transparent pixel)
        png_b64 = ("data:image/png;base64,"
                   "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        r = requests.patch(
            f"{API}/reports/{state.report_id}/signature",
            headers=_hdr(state.prod_token),
            json={"customer_name": "TEST Homeowner", "signature_base64": png_b64},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        sig = d["signature"]
        assert sig["customer_name"] == "TEST Homeowner"
        assert sig["signature_base64"].startswith("data:image/png;base64,")
        assert "signed_at" in sig and sig["signed_at"]

    def test_get_report_includes_signature(self, state):
        r = requests.get(f"{API}/reports/{state.report_id}",
                         headers=_hdr(state.prod_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "signature" in d and d["signature"], "report must include signature after PATCH"
        assert d["signature"]["customer_name"] == "TEST Homeowner"


# ---------- Weekly Digest ----------
class TestWeeklyDigest:
    def test_digest_non_admin_forbidden(self, state):
        r = requests.post(f"{API}/digest/weekly",
                          headers=_hdr(state.prod_token),
                          json={"recipient_emails": ["delivered@resend.dev"]},
                          timeout=30)
        assert r.status_code == 403, r.text

    def test_digest_admin_success(self, state):
        r = requests.post(f"{API}/digest/weekly",
                          headers=_hdr(state.admin_token),
                          json={"recipient_emails": ["delivered@resend.dev"]},
                          timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("text"), "digest text must be non-empty"
        assert len(d["text"]) > 20
        assert "email_sent_to" in d and isinstance(d["email_sent_to"], list)
        # Must have delivered@resend.dev in email_sent_to for verified provider
        print(f"digest email_sent_to: {d['email_sent_to']}")
        assert "report_ids" in d and isinstance(d["report_ids"], list)
        assert len(d["report_ids"]) >= 1, "should have >= 1 report id from last 7 days"
