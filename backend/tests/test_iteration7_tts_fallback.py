"""
Iteration 7 — TTS OpenAI-fallback regression tests.

Verifies POST /api/reports/{report_id}/tts returns 200 with the OpenAI
fallback engine when ElevenLabs quota is exhausted, plus caching, error
cases, RBAC, and light regression on /reports CRUD + regenerate-summary.
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"

ADMIN = ("admin@paintops.com", "Admin@12345")
PROD  = ("production@paintops.com", "Prod@12345")  # Role.PRODUCTION -> NOT in FULL_ROLES


# ---------------- fixtures ----------------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def prod_token(admin_token) -> str:
    # ensure production@paintops.com exists (seeded by earlier iterations); create if missing
    try:
        return _login(*PROD)
    except AssertionError:
        r = requests.post(
            f"{BASE}/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": PROD[0], "password": PROD[1], "name": "TEST_Prod User", "role": "Production"},
            timeout=30,
        )
        assert r.status_code in (201, 409), r.text
        return _login(*PROD)


@pytest.fixture(scope="module")
def h_admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def h_prod(prod_token):
    return {"Authorization": f"Bearer {prod_token}"}


def _create_report(headers, name_suffix: str) -> dict:
    payload = {
        "project_name": f"TEST_IT7_{name_suffix}",
        "project_code": "IT7-TTS",
        "highlights": f"TTS fallback smoke run {name_suffix}. Crew of 3 completed 60% of the ceiling prep.",
        "delays": "Minor delay on primer delivery.",
        "change_orders": "None.",
        "material_notes": "Primer, tape, drop cloths.",
        "include_weather": False,
        "include_visits": False,
        "include_breaks": False,
        "include_sms": False,
        "recipient_emails": [],
    }
    r = requests.post(f"{BASE}/reports", headers=headers, json=payload, timeout=120)
    assert r.status_code == 200, f"create_report {r.status_code}: {r.text[:200]}"
    body = r.json()
    assert body.get("id") and body.get("ai_summary"), "report missing id/ai_summary"
    return body


@pytest.fixture(scope="module")
def fresh_report(h_admin) -> dict:
    """Create a brand-new report under admin — never had TTS synthesized."""
    return _create_report(h_admin, "FreshTTS")


@pytest.fixture(scope="module")
def author_report(h_prod) -> dict:
    """A report authored by the production user (used for RBAC 403/allow tests)."""
    return _create_report(h_prod, "ProdAuthored")


# -------- 1. TTS returns 200 with OpenAI fallback --------
class TestTTSFallback:
    def test_fresh_generation_returns_200_and_valid_body(self, fresh_report, h_admin):
        """Endpoint must return 200 regardless of ElevenLabs quota state.
        voice_provider can be either 'elevenlabs' or 'openai'; both are valid.
        """
        rid = fresh_report["id"]
        r = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=180)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert "audio_data_url" in body and body["audio_data_url"].startswith("data:audio/mpeg;base64,")
        assert isinstance(body.get("bytes"), int) and body["bytes"] > 1000, f"bytes={body.get('bytes')}"
        assert body.get("cached") is False
        assert body.get("voice_provider") in ("elevenlabs", "openai"), body
        # record which engine served this run for report visibility
        fresh_report["_tts"] = body
        print(f"[iter7] fresh_report served by voice_provider={body['voice_provider']} bytes={body['bytes']}")

    def test_second_call_returns_cached(self, fresh_report, h_admin):
        rid = fresh_report["id"]
        first = fresh_report.get("_tts")
        assert first, "prior test must have populated first tts"
        r = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=60)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("cached") is True
        assert body.get("audio_data_url") == first["audio_data_url"]
        assert body.get("bytes") == first["bytes"]
        assert body.get("voice_provider") == first["voice_provider"]

    def test_openai_fallback_triggers_when_elevenlabs_fails(self, h_admin):
        """
        Directly forces the fallback path by installing an ai_summary that is
        long enough to exceed the remaining ElevenLabs quota (~1775 credits).
        The endpoint is expected to still return 200 with voice_provider='openai'.
        """
        # create a placeholder report
        payload = {
            "project_name": "TEST_IT7_LongSummary",
            "highlights": "trigger fallback",
            "delays": "", "change_orders": "", "material_notes": "",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }
        r = requests.post(f"{BASE}/reports", headers=h_admin, json=payload, timeout=120)
        assert r.status_code == 200, r.text[:200]
        rid = r.json()["id"]

        # Overwrite ai_summary with a long paragraph (~2200 chars). Endpoint trims to 2500
        # chars; ElevenLabs bills 1 credit/char at multilingual_v2, so this exceeds the
        # remaining 1775-credit quota and forces the OpenAI fallback branch.
        long_sentence = (
            "The crew arrived on site at seven a.m. sharp and reviewed the daily plan with the foreman "
            "before splitting into three teams to cover ceiling prep, wall priming, and trim cutting. "
        )
        long_summary = (long_sentence * 12).strip()  # ~ 2200 chars
        assert len(long_summary) > 1900

        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "paintops_daily")

        async def _set():
            client = AsyncIOMotorClient(mongo_url)
            await client[db_name].reports.update_one(
                {"id": rid}, {"$set": {"ai_summary": long_summary, "tts_cache": None}}
            )
            client.close()
        asyncio.get_event_loop().run_until_complete(_set())

        r2 = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=240)
        assert r2.status_code == 200, f"expected 200, got {r2.status_code} {r2.text[:300]}"
        body = r2.json()
        assert body["audio_data_url"].startswith("data:audio/mpeg;base64,")
        assert body["bytes"] > 1000
        assert body["cached"] is False
        # THIS is the core assertion of the E1 fix: OpenAI fallback engaged
        assert body["voice_provider"] == "openai", (
            f"Long summary should have exhausted EL quota and fallen back to OpenAI; got {body['voice_provider']}"
        )
        print(f"[iter7] long-summary fallback: voice_provider={body['voice_provider']} bytes={body['bytes']}")


# -------- 2. Error cases --------
class TestTTSErrorCases:
    def test_404_for_missing_report(self, h_admin):
        r = requests.post(f"{BASE}/reports/does-not-exist-xyz/tts", headers=h_admin, timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_400_when_summary_empty(self, h_admin, fresh_report):
        """
        Directly clear ai_summary in Mongo and confirm 400.
        We use a small helper endpoint chain: create a report, then PATCH via mongo shell? No — we do it
        via a Python driver connection to keep the test self-contained.
        """
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa
        import asyncio
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "paintops_daily")

        # create a throw-away report
        payload = {
            "project_name": "TEST_IT7_EmptySummary",
            "highlights": "temp",
            "delays": "",
            "change_orders": "",
            "material_notes": "",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }
        r = requests.post(f"{BASE}/reports", headers=h_admin, json=payload, timeout=120)
        assert r.status_code == 200, r.text[:200]
        rid = r.json()["id"]

        async def _clear():
            client = AsyncIOMotorClient(mongo_url)
            await client[db_name].reports.update_one(
                {"id": rid}, {"$set": {"ai_summary": "", "tts_cache": None}}
            )
            client.close()

        asyncio.get_event_loop().run_until_complete(_clear())

        r2 = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=30)
        assert r2.status_code == 400, f"{r2.status_code} {r2.text[:200]}"
        assert "summary" in r2.text.lower()


# -------- 3. RBAC --------
class TestTTSRbac:
    def test_non_full_role_non_author_403(self, author_report, h_admin, h_prod):
        """
        Create a report under ADMIN (Owner). Production user is not the author, not admin,
        not in FULL_ROLES -> should be 403.
        """
        # produce a report owned by admin (Owner) — NOT authored by production user
        owner_report = _create_report(h_admin, "OwnerAuthored")
        rid = owner_report["id"]
        r = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_prod, timeout=60)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"

    def test_author_can_tts_own_report(self, author_report, h_prod):
        """Production user is not in FULL_ROLES but IS the author -> allowed."""
        rid = author_report["id"]
        r = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_prod, timeout=180)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        body = r.json()
        assert body["audio_data_url"].startswith("data:audio/mpeg;base64,")
        assert body["voice_provider"] in ("openai", "elevenlabs")

    def test_admin_can_tts_any_report(self, author_report, h_admin):
        rid = author_report["id"]
        r = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=180)
        assert r.status_code == 200, r.text[:200]


# -------- 4. Regression: list, create, regen invalidates tts_cache --------
class TestRegression:
    def test_list_reports(self, h_admin):
        r = requests.get(f"{BASE}/reports", headers=h_admin, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_report_still_works(self, h_admin):
        payload = {
            "project_name": "TEST_IT7_RegressionCreate",
            "highlights": "regression create smoke",
            "delays": "",
            "change_orders": "",
            "material_notes": "",
            "include_weather": False, "include_visits": False,
            "include_breaks": False, "include_sms": False,
            "recipient_emails": [],
        }
        r = requests.post(f"{BASE}/reports", headers=h_admin, json=payload, timeout=120)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["ai_summary"] and body["id"]

    def test_regen_invalidates_tts_cache(self, fresh_report, h_admin):
        """
        After a fresh TTS (cached) call, hit /reports/{id}/regenerate-summary; the next TTS call
        should return cached=false again (new synthesis).
        Note: real endpoint is /regenerate-summary (request note used /regen).
        """
        rid = fresh_report["id"]

        # Confirm current TTS is cached
        r0 = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=60)
        assert r0.status_code == 200
        assert r0.json().get("cached") is True, "pre-regen: expected cached=true"

        # Regenerate summary (burns 1 GPT credit)
        rg = requests.post(f"{BASE}/reports/{rid}/regenerate-summary", headers=h_admin, timeout=180)
        assert rg.status_code == 200, f"regen {rg.status_code} {rg.text[:200]}"
        assert rg.json().get("ai_summary"), "regen returned empty summary"

        # Small settle
        time.sleep(1)

        # Next TTS call must NOT be cached (tts_cache was invalidated)
        r1 = requests.post(f"{BASE}/reports/{rid}/tts", headers=h_admin, timeout=180)
        assert r1.status_code == 200, r1.text[:200]
        body = r1.json()
        assert body.get("cached") is False, f"post-regen expected cached=false, got {body}"
        assert body.get("voice_provider") in ("elevenlabs", "openai")
        assert body["audio_data_url"].startswith("data:audio/mpeg;base64,")
