"""Iteration 19 backend tests: Custom-Lists Settings endpoints.

Endpoints under test (all auth-required):
- GET  /api/settings/lists
- PUT  /api/settings/lists
- POST /api/settings/lists/reset
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@paintops.com"
ADMIN_PASSWORD = "Admin@12345"


# ---------- helpers ----------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _admin_token() -> str:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def _create_user(admin_tok: str, prefix: str) -> tuple:
    """Create fresh user + return (email, password, token)."""
    email = f"TEST_it19_{prefix}_{uuid.uuid4().hex[:8]}@paintops.com"
    password = "Test@12345"
    body = {
        "email": email,
        "password": password,
        "name": f"Test User {prefix}",
        "role": "Production",
    }
    r = requests.post(f"{API}/admin/users", json=body, headers=_headers(admin_tok), timeout=30)
    assert r.status_code == 201, f"create user failed: {r.status_code} {r.text}"
    tok = _login(email, password)
    return email, password, tok, r.json()["id"]


def _delete_user(admin_tok: str, uid: str) -> None:
    requests.delete(f"{API}/admin/users/{uid}", headers=_headers(admin_tok), timeout=30)


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_tok():
    return _admin_token()


@pytest.fixture
def fresh_user(admin_tok):
    email, pwd, tok, uid = _create_user(admin_tok, "u")
    yield {"email": email, "password": pwd, "token": tok, "id": uid}
    # cleanup
    _delete_user(admin_tok, uid)


# ---------- 1. Defaults on first read ----------
class TestDefaultsOnFirstRead:
    def test_defaults(self, fresh_user):
        r = requests.get(f"{API}/settings/lists", headers=_headers(fresh_user["token"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("is_default") is True
        assert isinstance(j.get("break_types"), list)
        assert len(j["break_types"]) >= 4
        for name in ("Bathroom", "Lunch", "Personal", "Admin Call"):
            assert name in j["break_types"], f"missing default break type: {name}"
        assert isinstance(j.get("priority_flags"), list)
        assert len(j["priority_flags"]) >= 11
        # each flag has type + requires_reason
        for f in j["priority_flags"]:
            assert "type" in f and isinstance(f["type"], str) and f["type"]
            assert "requires_reason" in f and isinstance(f["requires_reason"], bool)


# ---------- 2. PUT roundtrip with dedupe/trim ----------
class TestPutRoundtrip:
    def test_put_then_get(self, fresh_user):
        payload = {
            "break_types": ["Coffee", "Coffee", "  ", "Lunch"],
            "priority_flags": [
                {"type": "X", "requires_reason": True},
                {"type": "x"},
            ],
        }
        r = requests.put(f"{API}/settings/lists", json=payload,
                         headers=_headers(fresh_user["token"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["break_types"] == ["Coffee", "Lunch"], j["break_types"]
        assert len(j["priority_flags"]) == 1
        assert j["priority_flags"][0]["type"] == "X"
        assert j["priority_flags"][0]["requires_reason"] is True
        assert j.get("is_default") is False

        # follow-up GET
        r2 = requests.get(f"{API}/settings/lists", headers=_headers(fresh_user["token"]), timeout=30)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["break_types"] == ["Coffee", "Lunch"]
        assert len(j2["priority_flags"]) == 1
        assert j2["priority_flags"][0]["type"] == "X"
        assert j2["priority_flags"][0]["requires_reason"] is True
        assert j2["is_default"] is False


# ---------- 3. Clamping long strings ----------
class TestPutClamps:
    def test_break_type_clamped_to_40(self, fresh_user):
        long_name = "A" * 100
        payload = {"break_types": [long_name], "priority_flags": []}
        r = requests.put(f"{API}/settings/lists", json=payload,
                         headers=_headers(fresh_user["token"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["break_types"]) == 1
        assert len(j["break_types"][0]) <= 40, f"got length {len(j['break_types'][0])}"

    def test_flag_type_clamped_to_60(self, fresh_user):
        long_type = "B" * 200
        payload = {"break_types": [], "priority_flags": [{"type": long_type, "requires_reason": False}]}
        r = requests.put(f"{API}/settings/lists", json=payload,
                         headers=_headers(fresh_user["token"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["priority_flags"]) == 1
        assert len(j["priority_flags"][0]["type"]) <= 60


# ---------- 4. Reset ----------
class TestResetClearsCustom:
    def test_reset_after_put(self, fresh_user):
        put_body = {
            "break_types": ["Custom1", "Custom2"],
            "priority_flags": [{"type": "MyFlag", "requires_reason": True}],
        }
        r = requests.put(f"{API}/settings/lists", json=put_body,
                         headers=_headers(fresh_user["token"]), timeout=30)
        assert r.status_code == 200
        assert r.json()["is_default"] is False

        r2 = requests.post(f"{API}/settings/lists/reset",
                           headers=_headers(fresh_user["token"]), timeout=30)
        assert r2.status_code == 200, r2.text
        j = r2.json()
        assert j["is_default"] is True
        assert "Bathroom" in j["break_types"]
        assert len(j["priority_flags"]) >= 11

        r3 = requests.get(f"{API}/settings/lists", headers=_headers(fresh_user["token"]), timeout=30)
        assert r3.status_code == 200
        j3 = r3.json()
        assert j3["is_default"] is True
        assert "Bathroom" in j3["break_types"]


# ---------- 5. Auth required ----------
class TestAuthRequired:
    def test_get_requires_auth(self):
        r = requests.get(f"{API}/settings/lists", timeout=30)
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_put_requires_auth(self):
        r = requests.put(f"{API}/settings/lists",
                         json={"break_types": [], "priority_flags": []}, timeout=30)
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_reset_requires_auth(self):
        r = requests.post(f"{API}/settings/lists/reset", timeout=30)
        assert r.status_code in (401, 403), f"got {r.status_code}"


# ---------- 6. User isolation ----------
class TestUserIsolation:
    def test_two_users_isolated(self, admin_tok):
        _, _, tok_a, uid_a = _create_user(admin_tok, "isoA")
        _, _, tok_b, uid_b = _create_user(admin_tok, "isoB")
        try:
            requests.put(f"{API}/settings/lists",
                         json={"break_types": ["A-Break"],
                               "priority_flags": [{"type": "A-Flag", "requires_reason": False}]},
                         headers=_headers(tok_a), timeout=30).raise_for_status()
            requests.put(f"{API}/settings/lists",
                         json={"break_types": ["B-Break-1", "B-Break-2"],
                               "priority_flags": [{"type": "B-Flag", "requires_reason": True}]},
                         headers=_headers(tok_b), timeout=30).raise_for_status()

            a = requests.get(f"{API}/settings/lists", headers=_headers(tok_a), timeout=30).json()
            b = requests.get(f"{API}/settings/lists", headers=_headers(tok_b), timeout=30).json()

            assert a["break_types"] == ["A-Break"]
            assert len(a["priority_flags"]) == 1
            assert a["priority_flags"][0]["type"] == "A-Flag"

            assert b["break_types"] == ["B-Break-1", "B-Break-2"]
            assert len(b["priority_flags"]) == 1
            assert b["priority_flags"][0]["type"] == "B-Flag"
        finally:
            _delete_user(admin_tok, uid_a)
            _delete_user(admin_tok, uid_b)
