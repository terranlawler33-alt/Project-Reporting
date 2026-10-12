"""
Iteration 23 backend tests — Attach photos to owner reply.

Tested behavior:
  - POST /api/responses/upload-photo (Bearer required):
      * multipart form field name `photo` → {ok: true, path: "<app>/replies/<user_id>/<uuid>.<ext>"}
      * extension whitelist: jpg/jpeg/png/webp/heic (unknown → jpg)
      * 400 for empty file
      * 413 for files > 8 MB
      * 401 without token
      * 502 is tolerated if object storage is down (endpoint still reachable, no 500 crash)
  - POST /api/responses/{id}/reply with optional `photos: List[str]` (max 4):
      * returned ReportResponse.photos equals posted list
      * list of 5 → 422
      * empty message → 422
      * omitting photos or [] preserves iteration-22 behavior
  - ReportResponse now exposes `photos: List[str] = []` on every returned response (GET /responses,
    GET /responses/{id}/thread), and legacy docs without `photos` deserialize with [].
  - Regressions on iterations 20/21/22 still green.

Run serially (shared admin session + autouse teardown):
  pytest /app/backend/tests/test_iteration23_reply_photos.py -v -o addopts=""
"""

import io
import os
import struct
import uuid
import zlib

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


# ---------- helpers ----------
def _tiny_png_bytes() -> bytes:
    """Return a valid 1x1 PNG (~ 67 bytes) so object storage won't reject it as empty/corrupt."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00" + b"\xff\xff\xff"  # one row, filter=none + white RGB pixel
    idat = chunk(b"IDAT", zlib.compress(raw, 9))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


TINY_PNG = _tiny_png_bytes()


# ---------- shared fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("access_token") or j.get("token")
    assert tok, f"No token in login response: {j}"
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
def bearer_only(admin_token):
    """Headers without Content-Type (safe for multipart file uploads)."""
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- report + inbound-reply builders ----------
def _create_report_with_project(auth_headers):
    pid_flagged = str(uuid.uuid4())
    projects = [
        {
            "id": pid_flagged,
            "project_code": "TEST_IT23_P1",
            "project_name": "TEST_IT23 Flagged Job",
            "customer_name": "ACME",
            "address": "123 Flagged St",
            "notes": "Fix hinge",
            "priority_flag": "Touch-Ups",
        },
    ]
    payload = {
        "highlights": "TEST_IT23 highlights",
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
    assert r.status_code == 200, f"POST /reports failed: {r.status_code} {r.text}"
    return r.json(), pid_flagged


def _mint_token(auth_headers, report_id):
    r = requests.post(
        f"{API}/reports/{report_id}/portal-link", headers=auth_headers, timeout=15,
    )
    assert r.status_code == 200, f"portal-link failed: {r.text}"
    return r.json()["token"]


def _create_inbound_reply(auth_headers, project_id=None, reporter_email="jane@example.com"):
    rep, pid = _create_report_with_project(auth_headers)
    token = _mint_token(auth_headers, rep["id"])
    payload = {
        "project_id": project_id or pid,
        "reporter_name": "External Jane",
        "reporter_email": reporter_email,
        "message": "Original inbound reply from external user.",
    }
    r = requests.post(f"{API}/public/reports/{token}/respond", json=payload, timeout=20)
    assert r.status_code == 200, f"respond failed: {r.text}"
    return rep, pid, token, r.json()


# ---------- autouse cleanup ----------
@pytest.fixture(autouse=True)
def _wipe_between_tests(auth_headers):
    yield
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


# ============================================================
# 1. POST /api/responses/upload-photo
# ============================================================
class TestUploadPhoto:
    def test_upload_photo_requires_auth(self):
        files = {"photo": ("a.png", TINY_PNG, "image/png")}
        r = requests.post(f"{API}/responses/upload-photo", files=files, timeout=20)
        assert r.status_code == 401, f"expected 401 without token, got {r.status_code}: {r.text}"

    def test_upload_photo_png_returns_path(self, bearer_only, admin_user):
        files = {"photo": ("snap.png", TINY_PNG, "image/png")}
        r = requests.post(
            f"{API}/responses/upload-photo", headers=bearer_only, files=files, timeout=30,
        )
        if r.status_code == 502:
            pytest.skip("Object storage unavailable (502) — endpoint reachable, feature can't be verified now.")
        assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
        j = r.json()
        assert j.get("ok") is True
        assert "path" in j and isinstance(j["path"], str)
        parts = j["path"].split("/")
        # <app>/replies/<user_id>/<uuid>.<ext>
        assert len(parts) == 4, f"path shape unexpected: {j['path']}"
        assert parts[1] == "replies", f"expected 'replies' segment, got {parts[1]}"
        assert parts[2] == admin_user["id"], f"user id segment mismatch: {parts[2]} vs {admin_user['id']}"
        assert parts[3].lower().endswith(".png"), f"expected .png ext, got {parts[3]}"

    @pytest.mark.parametrize("filename,expected_ext", [
        ("foo.jpg", "jpg"),
        ("foo.jpeg", "jpeg"),
        ("foo.PNG", "png"),
        ("foo.webp", "webp"),
        ("foo.heic", "heic"),
    ])
    def test_upload_photo_extension_whitelist(self, bearer_only, filename, expected_ext):
        files = {"photo": (filename, TINY_PNG, "application/octet-stream")}
        # Retry once on preview-tunnel timeout (ReadTimeout) to tame flakiness.
        last_exc = None
        r = None
        for _ in range(2):
            try:
                r = requests.post(
                    f"{API}/responses/upload-photo", headers=bearer_only, files=files, timeout=60,
                )
                break
            except requests.exceptions.ReadTimeout as exc:
                last_exc = exc
                continue
        if r is None:
            pytest.skip(f"upload timed out twice: {last_exc}")
        if r.status_code == 502:
            pytest.skip("Storage unavailable")
        assert r.status_code == 200, f"{filename}: {r.status_code} {r.text}"
        path = r.json()["path"]
        assert path.lower().endswith("." + expected_ext), (
            f"{filename}: expected .{expected_ext} ending, got {path}"
        )

    def test_upload_photo_unknown_ext_falls_back_to_jpg(self, bearer_only):
        files = {"photo": ("mystery.gif", TINY_PNG, "image/gif")}
        r = requests.post(
            f"{API}/responses/upload-photo", headers=bearer_only, files=files, timeout=30,
        )
        if r.status_code == 502:
            pytest.skip("Storage unavailable")
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        path = r.json()["path"]
        assert path.lower().endswith(".jpg"), f"expected .jpg fallback, got {path}"

    def test_upload_photo_no_filename_falls_back_to_jpg(self, bearer_only):
        files = {"photo": ("", TINY_PNG, "image/png")}
        r = requests.post(
            f"{API}/responses/upload-photo", headers=bearer_only, files=files, timeout=30,
        )
        if r.status_code == 502:
            pytest.skip("Storage unavailable")
        # some servers reject empty filename at multipart level — accept 422/400 as valid too.
        if r.status_code in (400, 422):
            return
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        assert r.json()["path"].lower().endswith(".jpg")

    def test_upload_photo_empty_file_400(self, bearer_only):
        files = {"photo": ("empty.png", b"", "image/png")}
        r = requests.post(
            f"{API}/responses/upload-photo", headers=bearer_only, files=files, timeout=20,
        )
        assert r.status_code == 400, f"expected 400 for empty photo, got {r.status_code}: {r.text}"

    def test_upload_photo_oversize_413(self, bearer_only):
        # 8 MB + 1 byte of filler — stays in memory just briefly.
        big = b"\x00" * (8 * 1024 * 1024 + 1)
        files = {"photo": ("huge.png", big, "image/png")}
        r = requests.post(
            f"{API}/responses/upload-photo", headers=bearer_only, files=files, timeout=60,
        )
        assert r.status_code == 413, f"expected 413 for oversize, got {r.status_code}: {r.text[:200]}"


# ============================================================
# 2. POST /api/responses/{id}/reply with photos
# ============================================================
class TestReplyWithPhotos:
    def test_reply_with_photos_returns_them(self, auth_headers, bearer_only, admin_user):
        rep, pid, token, inbound = _create_inbound_reply(auth_headers)
        # Upload two tiny photos first (skip whole test if storage down)
        p1 = requests.post(
            f"{API}/responses/upload-photo",
            headers=bearer_only,
            files={"photo": ("a.png", TINY_PNG, "image/png")},
            timeout=30,
        )
        p2 = requests.post(
            f"{API}/responses/upload-photo",
            headers=bearer_only,
            files={"photo": ("b.jpg", TINY_PNG, "image/jpeg")},
            timeout=30,
        )
        if p1.status_code == 502 or p2.status_code == 502:
            pytest.skip("Object storage unavailable for upload step")
        assert p1.status_code == 200 and p2.status_code == 200
        photos = [p1.json()["path"], p2.json()["path"]]

        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "Thanks — see attached touch-up pics.", "photos": photos},
            timeout=30,
        )
        assert r.status_code == 200, f"reply failed: {r.status_code} {r.text}"
        d = r.json()
        assert d["direction"] == "outbound"
        assert d["parent_id"] == inbound["id"]
        assert d["author_user_id"] == admin_user["id"]
        assert d["read_at"] is not None
        assert d.get("photos") == photos, f"photos mismatch: {d.get('photos')} vs {photos}"
        assert isinstance(d["email_delivered"], bool)

    def test_reply_without_photos_defaults_to_empty_list(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "No pics this time."},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "photos" in d, "ReportResponse must always include `photos` field"
        assert d["photos"] == [], f"expected [], got {d['photos']}"
        # Iter22 behavior preserved
        assert d["direction"] == "outbound"
        assert d["parent_id"] == inbound["id"]
        assert d["read_at"] is not None

    def test_reply_with_empty_photos_list(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "Still no pics.", "photos": []},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["photos"] == []

    def test_reply_with_five_photos_422(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        # Paths don't need to actually exist in storage — Pydantic should reject on length.
        fake = [f"paintops/replies/x/{uuid.uuid4()}.png" for _ in range(5)]
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "too many", "photos": fake},
            timeout=20,
        )
        assert r.status_code == 422, f"expected 422 for 5 photos, got {r.status_code}: {r.text[:200]}"

    def test_reply_empty_message_422(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "", "photos": []},
            timeout=20,
        )
        assert r.status_code == 422, f"expected 422 for empty msg, got {r.status_code}: {r.text[:200]}"

    def test_reply_with_four_photos_ok(self, auth_headers):
        """4 is the exact max — must succeed (we use fake paths; _get_object will fail
        gracefully and just omit from the email body, but the DB write still succeeds)."""
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        fake = [f"paintops/replies/x/{uuid.uuid4()}.png" for _ in range(4)]
        r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "exactly four", "photos": fake},
            timeout=25,
        )
        assert r.status_code == 200, f"expected 200 for 4 photos, got {r.status_code}: {r.text[:200]}"
        assert r.json()["photos"] == fake


# ============================================================
# 3. ReportResponse model regression (photos always present)
# ============================================================
class TestReportResponseModel:
    def test_inbound_response_has_photos_field_default_empty(self, auth_headers):
        """Inbound replies never set photos; must still deserialize to []."""
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        assert "photos" in inbound, "inbound ReportResponse missing `photos`"
        assert inbound["photos"] == []

    def test_list_responses_all_have_photos_field(self, auth_headers):
        _create_inbound_reply(auth_headers)
        _create_inbound_reply(auth_headers)
        r = requests.get(
            f"{API}/responses?include_outbound=true",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2
        for it in items:
            assert "photos" in it, f"response {it.get('id')} missing photos"
            assert isinstance(it["photos"], list)


# ============================================================
# 4. Thread listing surfaces outbound replies with photos
# ============================================================
class TestThreadListing:
    def test_thread_includes_outbound_reply_with_photos(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        fake = [f"paintops/replies/x/{uuid.uuid4()}.png", f"paintops/replies/x/{uuid.uuid4()}.jpg"]
        reply_r = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "Here are the pics.", "photos": fake},
            timeout=25,
        )
        assert reply_r.status_code == 200
        outbound_id = reply_r.json()["id"]

        th = requests.get(
            f"{API}/responses/{inbound['id']}/thread", headers=auth_headers, timeout=15,
        )
        assert th.status_code == 200, th.text
        thread = th.json()
        # Must contain both parent inbound + outbound reply, oldest → newest
        ids = [t["id"] for t in thread]
        assert inbound["id"] in ids
        assert outbound_id in ids
        assert ids.index(inbound["id"]) < ids.index(outbound_id)
        # Outbound reply surfaces its photos
        out = next(t for t in thread if t["id"] == outbound_id)
        assert out["direction"] == "outbound"
        assert out["photos"] == fake
        # Inbound still has empty photos
        inb = next(t for t in thread if t["id"] == inbound["id"])
        assert inb["photos"] == []


# ============================================================
# 5. Regression on iterations 20/21/22
# ============================================================
class TestRegression:
    def test_draft_today_still_works(self, auth_headers):
        r = requests.get(f"{API}/reports/draft/today", headers=auth_headers, timeout=15)
        assert r.status_code in (200, 404), f"draft/today returned {r.status_code}: {r.text[:150]}"
        # 200 may return null (no draft) or a draft doc — both are valid.
        if r.status_code == 200:
            body = r.json()
            assert body is None or isinstance(body, dict), f"unexpected body type: {type(body)}"

    def test_public_respond_creates_inbound_without_photos(self, auth_headers):
        rep, pid = _create_report_with_project(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r = requests.post(
            f"{API}/public/reports/{token}/respond",
            json={
                "project_id": pid,
                "reporter_name": "Public Jane",
                "reporter_email": "pjane@example.com",
                "message": "Public reply — no photos.",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("direction", "inbound") == "inbound"
        assert d["photos"] == []
        assert d["parent_id"] is None
        assert d["read_at"] is None

    def test_public_portal_returns_html(self, auth_headers):
        rep, _ = _create_report_with_project(auth_headers)
        token = _mint_token(auth_headers, rep["id"])
        r = requests.get(f"{API}/public/reports/{token}", timeout=20)
        assert r.status_code == 200, r.text[:200]
        ctype = r.headers.get("content-type", "")
        assert "text/html" in ctype.lower(), f"expected HTML, got {ctype}"
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()

    def test_project_summary_patch_still_works(self, auth_headers):
        rep, pid = _create_report_with_project(auth_headers)
        r = requests.patch(
            f"{API}/reports/{rep['id']}/projects/{pid}/summary",
            headers=auth_headers,
            json={"summary": "TEST_IT23 updated summary"},
            timeout=20,
        )
        assert r.status_code == 200, f"PATCH summary failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        # Accept either {ok: true} or the updated report doc
        assert body is not None

    def test_mail_schedule_get_and_put(self, auth_headers):
        g = requests.get(f"{API}/digest/mail-schedule", headers=auth_headers, timeout=15)
        assert g.status_code == 200, g.text
        gd = g.json()
        assert "enabled" in gd and "hour" in gd and "minute" in gd

        p = requests.put(
            f"{API}/digest/mail-schedule",
            headers=auth_headers,
            json={"enabled": True, "hour": 9, "minute": 15},
            timeout=15,
        )
        assert p.status_code == 200, p.text
        pd = p.json()
        # Endpoint returns {"ok": True, "schedule": {...}}
        sched = pd.get("schedule", pd)
        assert sched["enabled"] is True and sched["hour"] == 9 and sched["minute"] == 15

        # Restore to default
        requests.put(
            f"{API}/digest/mail-schedule",
            headers=auth_headers,
            json={"enabled": False, "hour": 7, "minute": 0},
            timeout=10,
        )

    def test_response_read_unread_archive_delete(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        rid = inbound["id"]

        r1 = requests.patch(f"{API}/responses/{rid}/read", headers=auth_headers, timeout=10)
        assert r1.status_code == 200
        assert r1.json()["read_at"] is not None

        r2 = requests.patch(f"{API}/responses/{rid}/unread", headers=auth_headers, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["read_at"] is None

        r3 = requests.post(f"{API}/responses/{rid}/archive", headers=auth_headers, timeout=10)
        assert r3.status_code == 200
        assert r3.json()["archived"] is True

        r4 = requests.delete(f"{API}/responses/{rid}", headers=auth_headers, timeout=10)
        assert r4.status_code in (200, 204)

    def test_list_responses_default_excludes_outbound(self, auth_headers):
        _, _, _, inbound = _create_inbound_reply(auth_headers)
        rpl = requests.post(
            f"{API}/responses/{inbound['id']}/reply",
            headers=auth_headers,
            json={"message": "outbound reply (should NOT appear in default list)"},
            timeout=20,
        )
        assert rpl.status_code == 200
        outbound_id = rpl.json()["id"]

        default = requests.get(f"{API}/responses", headers=auth_headers, timeout=15)
        assert default.status_code == 200
        ids_default = [x["id"] for x in default.json()]
        assert outbound_id not in ids_default, "default /responses must EXCLUDE outbound"
        assert inbound["id"] in ids_default

        included = requests.get(
            f"{API}/responses?include_outbound=true", headers=auth_headers, timeout=15,
        )
        assert included.status_code == 200
        ids_inc = [x["id"] for x in included.json()]
        assert outbound_id in ids_inc
