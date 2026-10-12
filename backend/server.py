"""PaintOps Daily backend - FastAPI server."""
import os
import re
import ipaddress
import logging
import io
import csv
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Any
from uuid import uuid4
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import jwt
import httpx
import bcrypt
import tempfile
import secrets
import requests
import base64 as _b64
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status, Request, APIRouter, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, HTMLResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText
from emergentintegrations.llm.openai import OpenAITextToSpeech
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.getenv("JWT_ISSUER", "paintops-api")
TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "1440"))
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
EMERGENT_EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ALGORITHM = "HS256"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ---------- Enums ----------
class Role(str, Enum):
    OWNER = "Owner"
    OPERATIONS = "Operations"
    SALES = "Sales"
    PRODUCTION = "Production"
    LABOR = "Labor"
    PROJECT_MANAGER = "Project Manager"


class BreakType(str, Enum):
    BATHROOM = "Bathroom"
    LUNCH = "Lunch"
    PERSONAL = "Personal"
    ADMIN_CALL = "Admin Call"


# ---------- Models ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str
    role: Role
    job_title: Optional[str] = None
    department: Optional[str] = None
    job_code: Optional[str] = None
    is_admin: bool = False


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: Role
    job_title: Optional[str] = None
    department: Optional[str] = None
    job_code: Optional[str] = None
    is_admin: bool


class LocationVisitCreate(BaseModel):
    latitude: float
    longitude: float
    customer_name: Optional[str] = None
    address: Optional[str] = None
    project_code: Optional[str] = None
    notes: Optional[str] = None
    project_id: Optional[str] = None  # links visit to a Project inside today's report


class LocationVisit(LocationVisitCreate):
    id: str
    user_id: str
    timestamp: str
    ended_at: Optional[str] = None
    photos: List[str] = []
    weather: Optional[dict] = None  # snapshot fetched at check-in time
    weather_refreshed_at: Optional[str] = None
    bookmarked: bool = False  # marks recurring locations for quick re-log


class LocationVisitPatch(BaseModel):
    customer_name: Optional[str] = None
    address: Optional[str] = None
    project_code: Optional[str] = None
    notes: Optional[str] = None


class BreakCreate(BaseModel):
    break_type: BreakType
    reason: str
    call_details: Optional[str] = None


class BreakEntry(BreakCreate):
    id: str
    user_id: str
    started_at: str
    ended_at: Optional[str] = None
    duration_minutes: Optional[int] = None


class SmsLogCreate(BaseModel):
    contact_name: str
    contact_role: str
    direction: str  # inbound/outbound
    channel: str  # SMS/Call/Email
    category: str  # project_detail, change_order, escalation, schedule, weather_delay, material, traffic, other
    content: str
    project_code: Optional[str] = None


class SmsLog(SmsLogCreate):
    id: str
    user_id: str
    timestamp: str


class WeatherAttachment(BaseModel):
    latitude: float
    longitude: float
    temperature_f: Optional[float] = None
    conditions: Optional[str] = None
    wind_mph: Optional[float] = None
    precipitation: Optional[float] = None
    fetched_at: str


class ProjectEntry(BaseModel):
    """A single project block inside a DailyReport. A report can have many."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
    materials_used: Optional[str] = None
    start_time: Optional[str] = None  # HH:MM or ISO
    end_time: Optional[str] = None
    priority_flag: Optional[str] = None  # e.g. "Touch-Ups", "Change Order"
    touch_up: bool = False
    photos: List[str] = []
    visit_ids: List[str] = []
    weather: Optional[dict] = None  # site-specific weather snapshot at check-in
    summary: Optional[str] = None  # short "virtual layout" of the job — written at sell/conception


class ReportCreate(BaseModel):
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    highlights: str = ""
    delays: str = ""
    change_orders: str = ""
    material_notes: str = ""
    include_weather: bool = True
    include_visits: bool = True
    include_breaks: bool = True
    include_sms: bool = True
    recipient_emails: List[EmailStr] = []
    priority_level: Optional[str] = None  # "High" | "Medium" | "Low" | None
    priority_flags: List[dict] = Field(default_factory=list)  # [{"type": str, "reason": Optional[str]}]
    projects: List[ProjectEntry] = Field(default_factory=list)


class DailyReport(BaseModel):
    id: str
    user_id: str
    author_name: str
    author_role: str
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    report_date: str
    ai_summary: str
    highlights: str
    delays: str
    change_orders: str
    material_notes: str
    visits: List[dict] = []
    breaks: List[dict] = []
    sms_logs: List[dict] = []
    weather: Optional[dict] = None
    email_sent_to: List[str] = []
    created_at: str
    updated_at: Optional[str] = None
    signature: Optional[dict] = None
    archived: bool = False
    archived_at: Optional[str] = None
    deleted_at: Optional[str] = None
    public_token: Optional[str] = None
    priority_level: Optional[str] = None
    priority_flags: List[dict] = []
    projects: List[dict] = Field(default_factory=list)
    # "draft" (work-in-progress, auto-saved through the day) or "submitted" (final).
    # Legacy reports without this field are treated as "submitted" for backward compatibility.
    status: str = "submitted"
    include_weather: bool = True
    include_visits: bool = True
    include_breaks: bool = True
    include_sms: bool = True
    recipient_emails: List[str] = []


class ReportResponse(BaseModel):
    """A reply left on a shared report (typically on a flagged job) by an external recipient,
    OR an owner-side reply back out to the original respondent (direction='outbound')."""
    id: str
    report_id: str
    report_user_id: str  # owner of the report (destination inbox)
    project_id: Optional[str] = None  # which project (job) this reply targets
    project_label: Optional[str] = None  # pre-rendered project title at reply time
    project_flag: Optional[str] = None  # priority flag of the targeted project
    reporter_name: Optional[str] = None
    reporter_email: Optional[str] = None
    message: str
    created_at: str
    read_at: Optional[str] = None
    archived: bool = False
    # Threading
    parent_id: Optional[str] = None  # null for original reply; id of the parent for owner's replies
    direction: str = "inbound"  # "inbound" = from recipient; "outbound" = owner's reply
    author_user_id: Optional[str] = None  # set when owner sends a reply from the app
    email_delivered: bool = False  # true when owner's outbound reply was emailed to the respondent
    photos: List[str] = []  # object-storage paths of attachments on this reply


# ---------- Auth helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def make_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user["id"],
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_MINUTES),
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=ALGORITHM)


async def current_user(request: Request) -> dict:
    unauthorized = HTTPException(status_code=401, detail="Invalid authentication",
                                 headers={"WWW-Authenticate": "Bearer"})
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise unauthorized
    token = auth[7:]
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM], issuer=JWT_ISSUER)
        user_id = claims.get("sub")
        if not user_id:
            raise unauthorized
    except Exception:
        raise unauthorized
    user = await request.app.db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise unauthorized
    return user


async def admin_only(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return user


# ---------- Email guardrails ----------
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> Optional[str]:
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMERGENT_EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return None


# ---------- Lifespan / DB ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(MONGO_URL)
    app.mongo_client = client
    app.db = client[DB_NAME]
    await app.db.users.create_index("email", unique=True)
    await app.db.users.create_index("id", unique=True)

    # Seed admin
    admin_email = "admin@paintops.com"
    existing = await app.db.users.find_one({"email": admin_email})
    if not existing:
        admin_doc = {
            "id": str(uuid4()),
            "email": admin_email,
            "name": "Site Administrator",
            "password_hash": hash_password("Admin@12345"),
            "role": Role.OWNER.value,
            "job_title": "Owner / Admin",
            "department": "Executive",
            "job_code": "ADMIN-001",
            "is_admin": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await app.db.users.insert_one(admin_doc)
        logger.info(f"Seeded admin user: {admin_email}")

    # Start APScheduler (must be inside lifespan since @app.on_event is ignored when lifespan is set)
    scheduler = AsyncIOScheduler()
    app.scheduler = scheduler
    scheduler.start()
    try:
        await _reschedule_digest(app)
    except Exception as e:
        logger.error(f"Scheduler bootstrap failed: {e}")
    try:
        await _reschedule_mail_digest(app)
    except Exception as e:
        logger.error(f"Mail digest scheduler bootstrap failed: {e}")

    yield

    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()


app = FastAPI(title="PaintOps Daily API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


# ---------- Auth routes ----------
@api.get("/")
async def root():
    return {"message": "PaintOps Daily API", "version": "1.0"}


@api.post("/auth/login", response_model=Token)
async def login(data: LoginRequest, request: Request):
    user = await request.app.db.users.find_one({"email": data.email.lower()}, {"_id": 0})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = make_token(user)
    user_out = {k: user[k] for k in ("id", "email", "name", "role", "job_title", "department", "job_code", "is_admin") if k in user}
    return Token(access_token=token, user=user_out)


@api.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return UserOut(**user)


# ---------- User admin ----------
@api.post("/admin/users", response_model=UserOut, status_code=201)
async def create_user(data: UserCreate, request: Request, _: dict = Depends(admin_only)):
    doc = {
        "id": str(uuid4()),
        "email": str(data.email).lower(),
        "name": data.name,
        "password_hash": hash_password(data.password),
        "role": data.role.value,
        "job_title": data.job_title,
        "department": data.department,
        "job_code": data.job_code,
        "is_admin": data.is_admin,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await request.app.db.users.insert_one(doc)
    except Exception as exc:
        if "duplicate" in str(exc).lower():
            raise HTTPException(409, "Email already exists")
        raise
    return UserOut(**{k: doc[k] for k in ("id", "email", "name", "role", "job_title", "department", "job_code", "is_admin")})


@api.get("/admin/users", response_model=List[UserOut])
async def list_users(request: Request, _: dict = Depends(admin_only)):
    docs = await request.app.db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return [UserOut(**d) for d in docs]


@api.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, request: Request, admin: dict = Depends(admin_only)):
    if user_id == admin["id"]:
        raise HTTPException(400, "Cannot delete yourself")
    result = await request.app.db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}


# ---------- Weather (Open-Meteo) ----------
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 80: "Rain showers",
    81: "Moderate rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
    96: "Thunderstorm w/ slight hail", 99: "Thunderstorm w/ heavy hail",
}


async def _fetch_weather(lat: float, lon: float) -> Optional[dict]:
    """Fetch a weather snapshot from Open-Meteo. Returns None on failure so
    callers can degrade gracefully.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,precipitation,wind_speed_10m,weather_code,relative_humidity_2m",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "auto",
                },
            )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        code = current.get("weather_code", 0)
        return {
            "latitude": lat,
            "longitude": lon,
            "temperature_f": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_mph": current.get("wind_speed_10m"),
            "precipitation": current.get("precipitation"),
            "weather_code": code,
            "conditions": WEATHER_CODES.get(code, "Unknown"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"Weather fetch failed for {lat},{lon}: {e}")
        return None


@api.get("/weather")
async def get_weather(lat: float, lon: float, _: dict = Depends(current_user)):
    snapshot = await _fetch_weather(lat, lon)
    if not snapshot:
        raise HTTPException(502, "Failed to fetch weather")
    return snapshot


@api.get("/weather/hourly")
async def get_weather_hourly(
    lat: float,
    lon: float,
    hours: int = 12,
    _: dict = Depends(current_user),
):
    """Return the next N hourly forecast points (default 12) from Open-Meteo.
    Each entry: {time, temperature_f, precip_prob, precipitation, wind_mph, weather_code, conditions}.
    """
    hours = max(1, min(24, int(hours or 12)))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "auto",
                    "forecast_days": 2,
                },
            )
        resp.raise_for_status()
        j = resp.json()
    except Exception as e:
        logger.warning(f"Hourly weather failed for {lat},{lon}: {e}")
        raise HTTPException(502, "Failed to fetch hourly weather")

    hourly = j.get("hourly", {}) or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    probs = hourly.get("precipitation_probability") or []
    precs = hourly.get("precipitation") or []
    codes = hourly.get("weather_code") or []
    winds = hourly.get("wind_speed_10m") or []
    tz_offset = j.get("utc_offset_seconds", 0) or 0

    # Find the first index at or after "now" in the local timezone reported by the API
    now_local = datetime.utcnow() + timedelta(seconds=tz_offset)
    start_idx = 0
    for i, t in enumerate(times):
        try:
            ts = datetime.strptime(t, "%Y-%m-%dT%H:%M")
        except Exception:
            continue
        if ts >= now_local:
            start_idx = i
            break

    end_idx = min(len(times), start_idx + hours)
    points = []
    for i in range(start_idx, end_idx):
        code = codes[i] if i < len(codes) else None
        points.append({
            "time": times[i] if i < len(times) else None,
            "hour_label": (times[i][11:16] if i < len(times) and len(times[i]) >= 16 else ""),
            "temperature_f": temps[i] if i < len(temps) else None,
            "precip_prob": probs[i] if i < len(probs) else None,
            "precipitation": precs[i] if i < len(precs) else None,
            "wind_mph": winds[i] if i < len(winds) else None,
            "weather_code": code,
            "conditions": WEATHER_CODES.get(code, "Unknown") if code is not None else None,
        })
    return {
        "latitude": lat,
        "longitude": lon,
        "hours": len(points),
        "utc_offset_seconds": tz_offset,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "points": points,
    }


@api.get("/geocode")
async def geocode(q: str, _: dict = Depends(current_user)):
    """Search a place/address using Open-Meteo Geocoding API (free, no key)."""
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "Query cannot be empty")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": q, "count": 8, "language": "en", "format": "json"},
            )
        resp.raise_for_status()
        results = (resp.json() or {}).get("results", []) or []
    except Exception as e:
        logger.warning(f"Geocode failed for {q!r}: {e}")
        raise HTTPException(502, "Geocoding lookup failed")
    return {
        "query": q,
        "results": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "admin1": r.get("admin1"),  # state/province
                "admin2": r.get("admin2"),  # county
                "country": r.get("country"),
                "country_code": r.get("country_code"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "postcodes": r.get("postcodes") or [],
                "label": ", ".join(
                    [x for x in [r.get("name"), r.get("admin1"), r.get("country")] if x]
                ),
            }
            for r in results
        ],
    }


# ---------- Location Visits ----------
@api.post("/visits", response_model=LocationVisit)
async def create_visit(data: LocationVisitCreate, request: Request, user: dict = Depends(current_user)):
    doc = data.model_dump()
    now_iso = datetime.now(timezone.utc).isoformat()
    # Auto-fetch weather snapshot at the pin coordinates so the report can show
    # the exact conditions when work started at this site.
    weather_snapshot = await _fetch_weather(doc["latitude"], doc["longitude"])
    doc.update({
        "id": str(uuid4()),
        "user_id": user["id"],
        "timestamp": now_iso,
        "ended_at": None,
        "weather": weather_snapshot,
        "weather_refreshed_at": now_iso if weather_snapshot else None,
    })
    await request.app.db.visits.insert_one(doc.copy())
    doc.pop("_id", None)
    return LocationVisit(**doc)


@api.post("/visits/{visit_id}/refresh-weather", response_model=LocationVisit)
async def refresh_visit_weather(visit_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Visit not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if doc["user_id"] != user["id"] and user["role"] not in FULL_ROLES and not user.get("is_admin"):
        raise HTTPException(403, "Not allowed")
    snapshot = await _fetch_weather(doc["latitude"], doc["longitude"])
    if not snapshot:
        raise HTTPException(502, "Weather refresh failed")
    now_iso = datetime.now(timezone.utc).isoformat()
    await request.app.db.visits.update_one(
        {"id": visit_id},
        {"$set": {"weather": snapshot, "weather_refreshed_at": now_iso}},
    )
    doc["weather"] = snapshot
    doc["weather_refreshed_at"] = now_iso
    return LocationVisit(**doc)


@api.get("/visits/today", response_model=List[LocationVisit])
async def visits_today(request: Request, user: dict = Depends(current_user)):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    docs = await request.app.db.visits.find(
        {"user_id": user["id"], "timestamp": {"$gte": start}},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(500)
    return [LocationVisit(**d) for d in docs]


@api.post("/visits/{visit_id}/end")
async def end_visit(visit_id: str, request: Request, user: dict = Depends(current_user)):
    result = await request.app.db.visits.update_one(
        {"id": visit_id, "user_id": user["id"]},
        {"$set": {"ended_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Visit not found")
    return {"ok": True}


def _can_modify_visit(doc: dict, user: dict) -> bool:
    if doc.get("user_id") == user["id"]:
        return True
    if user.get("is_admin"):
        return True
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    return user.get("role") in FULL_ROLES


@api.get("/visits/bookmarked", response_model=List[LocationVisit])
async def list_bookmarked_visits(request: Request, user: dict = Depends(current_user)):
    """All bookmarked visits for the current user (recurring locations).
    Sorted by most-recently-visited so the top hits are always current.
    """
    docs = await request.app.db.visits.find(
        {"user_id": user["id"], "bookmarked": True},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(200)
    return [LocationVisit(**d) for d in docs]


@api.post("/visits/{visit_id}/bookmark", response_model=LocationVisit)
async def toggle_bookmark(visit_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Visit not found")
    if not _can_modify_visit(doc, user):
        raise HTTPException(403, "Not allowed")
    new_val = not bool(doc.get("bookmarked", False))
    await request.app.db.visits.update_one(
        {"id": visit_id}, {"$set": {"bookmarked": new_val}}
    )
    doc["bookmarked"] = new_val
    return LocationVisit(**doc)


@api.patch("/visits/{visit_id}", response_model=LocationVisit)
async def patch_visit(
    visit_id: str,
    data: LocationVisitPatch,
    request: Request,
    user: dict = Depends(current_user),
):
    doc = await request.app.db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Visit not found")
    if not _can_modify_visit(doc, user):
        raise HTTPException(403, "Not allowed")
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    # Allow explicit empty strings from the client to CLEAR fields
    for k, v in data.model_dump(exclude_unset=True).items():
        if v == "":
            updates[k] = None
    if not updates:
        return LocationVisit(**doc)
    await request.app.db.visits.update_one({"id": visit_id}, {"$set": updates})
    doc.update(updates)
    return LocationVisit(**doc)


@api.delete("/visits/{visit_id}")
async def delete_visit(visit_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Visit not found")
    if not _can_modify_visit(doc, user):
        raise HTTPException(403, "Not allowed")
    await request.app.db.visits.delete_one({"id": visit_id})
    return {"ok": True}


# ---------- Breaks ----------
@api.post("/breaks", response_model=BreakEntry)
async def start_break(data: BreakCreate, request: Request, user: dict = Depends(current_user)):
    doc = data.model_dump()
    doc.update({
        "id": str(uuid4()),
        "user_id": user["id"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "duration_minutes": None,
    })
    await request.app.db.breaks.insert_one(doc.copy())
    doc.pop("_id", None)
    doc["break_type"] = doc["break_type"].value if hasattr(doc["break_type"], "value") else doc["break_type"]
    return BreakEntry(**doc)


@api.post("/breaks/{break_id}/end")
async def end_break(break_id: str, request: Request, user: dict = Depends(current_user)):
    br = await request.app.db.breaks.find_one({"id": break_id, "user_id": user["id"]}, {"_id": 0})
    if not br:
        raise HTTPException(404, "Break not found")
    now = datetime.now(timezone.utc)
    started = datetime.fromisoformat(br["started_at"])
    duration = int((now - started).total_seconds() / 60)
    await request.app.db.breaks.update_one(
        {"id": break_id},
        {"$set": {"ended_at": now.isoformat(), "duration_minutes": duration}},
    )
    return {"ok": True, "duration_minutes": duration}


@api.get("/breaks/today", response_model=List[BreakEntry])
async def breaks_today(request: Request, user: dict = Depends(current_user)):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    docs = await request.app.db.breaks.find(
        {"user_id": user["id"], "started_at": {"$gte": start}},
        {"_id": 0},
    ).sort("started_at", -1).to_list(500)
    return [BreakEntry(**d) for d in docs]


# ---------- SMS Logs ----------
@api.post("/sms-logs", response_model=SmsLog)
async def create_sms_log(data: SmsLogCreate, request: Request, user: dict = Depends(current_user)):
    doc = data.model_dump()
    doc.update({
        "id": str(uuid4()),
        "user_id": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    await request.app.db.sms_logs.insert_one(doc.copy())
    doc.pop("_id", None)
    return SmsLog(**doc)


@api.get("/sms-logs/today", response_model=List[SmsLog])
async def sms_today(request: Request, user: dict = Depends(current_user)):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    docs = await request.app.db.sms_logs.find(
        {"user_id": user["id"], "timestamp": {"$gte": start}},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(500)
    return [SmsLog(**d) for d in docs]


class SmsLogBulkCreate(BaseModel):
    items: List[SmsLogCreate]


@api.post("/sms-logs/bulk", response_model=List[SmsLog])
async def create_sms_logs_bulk(data: SmsLogBulkCreate, request: Request, user: dict = Depends(current_user)):
    """Create multiple SMS logs in one call (used when importing texts from the phone)."""
    if not data.items:
        return []
    now_iso = datetime.now(timezone.utc).isoformat()
    docs: List[dict] = []
    for entry in data.items:
        d = entry.model_dump()
        d.update({
            "id": str(uuid4()),
            "user_id": user["id"],
            "timestamp": now_iso,
        })
        docs.append(d)
    # insert_many copies so we don't mutate return docs with _id
    await request.app.db.sms_logs.insert_many([d.copy() for d in docs])
    return [SmsLog(**d) for d in docs]


# ---------- Reports ----------
async def build_ai_summary(context: dict) -> str:
    system = (
        "You are an experienced painting operations project manager writing a professional daily field report "
        "for the OWNER of the company. Output MUST be readable, decisive, and organized using EXACTLY the "
        "seven Markdown section headers below, in this order, each on its own line. Do NOT add or rename "
        "headers, do NOT wrap them in extra symbols, and always keep them ALL CAPS.\n\n"
        "## WORK COMPLETED\n"
        "## COMMUNICATIONS\n"
        "## WEATHER IMPACT\n"
        "## DELAY / CONSTRAINTS\n"
        "## CHANGE ORDER / MATERIALS\n"
        "## NEXT STEPS\n"
        "## OVERALL SUMMARY\n\n"
        "Formatting rules:\n"
        "- Under each header write 2-6 tight bullet points prefixed with '- '.\n"
        "- If MULTIPLE PROJECTS were worked on today (see 'Projects worked on today' section in input), "
        "  GROUP the WORK COMPLETED section by project. For each project write a sub-line "
        "  '- **Project N — <customer or code> — <address>**' followed by 1-3 indented bullet points of the "
        "  actual work for that project (prefix indented bullets with '  - ').\n"
        "- In WEATHER IMPACT: if per-project weather snapshots were provided, list one bullet per "
        "  site prefixed with '- **<address>**: <conditions>, <temp>°F, wind <mph> mph'. Otherwise "
        "  fall back to the overall day weather.\n"
        "- Wrap CUSTOMER names, ADDRESSES, and PROJECT CODES in double-asterisk bold, e.g. **John Doe**, **123 Main St**, **P-1042**.\n"
        "- If a priority flag reason was provided, echo it verbatim in DELAY / CONSTRAINTS on its own bullet "
        "prefixed with '[URGENT: <flag type>]' so it can be highlighted red in the app.\n"
        "- If any project has priority_flag='Touch-Ups' or touch_up=true, add a bullet in DELAY / CONSTRAINTS "
        "prefixed with '[TOUCH-UP: <address>]' so the owner sees pending touch-ups.\n"
        "- OVERALL SUMMARY is 2-3 concise sentences the owner can read in 10 seconds. No fluff.\n"
        "- Never invent facts. If a section has no info, write '- None reported today.'\n"
    )
    prompt_lines = [f"Author: {context.get('author_name')} ({context.get('author_role')})"]
    if context.get("priority_level"):
        prompt_lines.append(f"Priority level: {context['priority_level']}")
    if context.get("priority_flags"):
        prompt_lines.append("Priority flags:")
        for f in context["priority_flags"]:
            reason = f.get("reason")
            if reason:
                prompt_lines.append(f"- {f.get('type')} — reason: {reason}")
            else:
                prompt_lines.append(f"- {f.get('type')}")
    if context.get("project_name") or context.get("project_code"):
        prompt_lines.append(f"Primary Project: {context.get('project_name') or ''} {context.get('project_code') or ''}")
    prompt_lines.append(f"Date: {context.get('report_date')}")
    if context.get("weather"):
        w = context["weather"]
        prompt_lines.append(
            f"Weather at site: {w.get('conditions')}, {w.get('temperature_f')}°F, wind {w.get('wind_mph')} mph, "
            f"precipitation {w.get('precipitation')} in."
        )
    # NEW: projects list
    if context.get("projects"):
        prompt_lines.append("Projects worked on today:")
        for idx, p in enumerate(context["projects"], start=1):
            code = p.get("project_code") or "no code"
            addr = p.get("address") or "no address"
            cust = p.get("customer_name") or "Unknown customer"
            times = ""
            if p.get("start_time") or p.get("end_time"):
                times = f" ({p.get('start_time') or '?'} → {p.get('end_time') or 'ongoing'})"
            head = f"- Project {idx}: {cust} at {addr} [{code}]{times}"
            prompt_lines.append(head)
            if p.get("notes"):
                prompt_lines.append(f"  · Work notes: {p['notes']}")
            if p.get("materials_used"):
                prompt_lines.append(f"  · Materials used: {p['materials_used']}")
            if p.get("weather"):
                w = p["weather"]
                prompt_lines.append(
                    f"  · Weather on site: {w.get('conditions')}, "
                    f"{w.get('temperature_f')}°F, wind {w.get('wind_mph')} mph, "
                    f"precip {w.get('precipitation')} in."
                )
            if p.get("priority_flag") or p.get("touch_up"):
                flag = p.get("priority_flag") or ("Touch-Ups" if p.get("touch_up") else "")
                if flag:
                    prompt_lines.append(f"  · Flag: {flag}")
    if context.get("highlights"):
        prompt_lines.append(f"Manager highlights: {context['highlights']}")
    if context.get("delays"):
        prompt_lines.append(f"Delays: {context['delays']}")
    if context.get("change_orders"):
        prompt_lines.append(f"Change orders: {context['change_orders']}")
    if context.get("material_notes"):
        prompt_lines.append(f"Material notes: {context['material_notes']}")
    if context.get("visits"):
        prompt_lines.append("Site visits today (raw GPS log):")
        for v in context["visits"]:
            addr = v.get("address") or f"({v.get('latitude')}, {v.get('longitude')})"
            code = v.get("project_code") or "no code"
            prompt_lines.append(
                f"- {v.get('customer_name') or 'Unknown'} at {addr} [{code}]: {v.get('notes') or ''}"
            )
    if context.get("breaks"):
        prompt_lines.append("Breaks taken:")
        for b in context["breaks"]:
            duration = f"{b.get('duration_minutes', '?')} min" if b.get("duration_minutes") else "ongoing"
            extra = f" | Call details: {b['call_details']}" if b.get("call_details") else ""
            prompt_lines.append(f"- {b.get('break_type')} ({duration}): {b.get('reason', '')}{extra}")
    if context.get("sms_logs"):
        prompt_lines.append("Communications:")
        for s in context["sms_logs"]:
            prompt_lines.append(
                f"- [{s.get('channel')} {s.get('direction')}] {s.get('contact_name')} ({s.get('contact_role')}) "
                f"- {s.get('category')}: {s.get('content')}"
            )
    prompt = "\n".join(prompt_lines) + "\n\nWrite the daily report now using the required headers."

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"report-{uuid4()}",
            system_message=system,
        ).with_model("openai", "gpt-5.4")
        response = await chat.send_message(UserMessage(text=prompt))
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"AI summary failed: {e}")
        return (
            "## WORK COMPLETED\n- None reported today.\n\n"
            "## COMMUNICATIONS\n- None reported today.\n\n"
            "## WEATHER IMPACT\n- None reported today.\n\n"
            "## DELAY / CONSTRAINTS\n"
            f"- {context.get('delays') or 'None reported today.'}\n\n"
            "## CHANGE ORDER / MATERIALS\n"
            f"- {context.get('change_orders') or 'None reported today.'}\n"
            f"- {context.get('material_notes') or ''}\n\n"
            "## NEXT STEPS\n- None reported today.\n\n"
            "## OVERALL SUMMARY\n"
            f"- {context.get('highlights') or 'No summary available.'}\n"
        )


def _derive_projects_from_visits(visits: List[dict]) -> List[dict]:
    """Auto-migrate legacy visits into project entries.
    Groups visits by project_id when set; otherwise each visit becomes its own project.
    """
    projects: List[dict] = []
    by_pid: dict[str, dict] = {}
    for v in visits:
        pid = v.get("project_id")
        base = {
            "id": pid or str(uuid4()),
            "project_code": v.get("project_code"),
            "project_name": None,
            "customer_name": v.get("customer_name"),
            "address": v.get("address"),
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "notes": v.get("notes"),
            "materials_used": None,
            "start_time": v.get("timestamp"),
            "end_time": v.get("ended_at"),
            "priority_flag": None,
            "touch_up": False,
            "photos": list(v.get("photos", [])),
            "visit_ids": [v.get("id")] if v.get("id") else [],
            "weather": v.get("weather"),
        }
        if pid and pid in by_pid:
            # merge additional visit into the same project
            existing = by_pid[pid]
            existing["visit_ids"].append(v.get("id"))
            existing["photos"].extend(v.get("photos", []))
            if v.get("notes"):
                existing["notes"] = (existing.get("notes") or "") + ("\n" if existing.get("notes") else "") + v["notes"]
            # keep the earliest weather snapshot so the report reflects check-in conditions
            if not existing.get("weather") and v.get("weather"):
                existing["weather"] = v["weather"]
        elif pid:
            by_pid[pid] = base
            projects.append(base)
        else:
            projects.append(base)
    return projects


@api.post("/reports", response_model=DailyReport)
async def create_report(data: ReportCreate, request: Request, user: dict = Depends(current_user)):
    today_iso = datetime.now(timezone.utc).date().isoformat()
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    visits, breaks, sms_logs, weather = [], [], [], None
    if data.include_visits:
        visits = await request.app.db.visits.find(
            {"user_id": user["id"], "timestamp": {"$gte": day_start}}, {"_id": 0},
        ).to_list(500)
    if data.include_breaks:
        breaks = await request.app.db.breaks.find(
            {"user_id": user["id"], "started_at": {"$gte": day_start}}, {"_id": 0},
        ).to_list(500)
    if data.include_sms:
        sms_logs = await request.app.db.sms_logs.find(
            {"user_id": user["id"], "timestamp": {"$gte": day_start}}, {"_id": 0},
        ).to_list(500)
    if data.include_weather and visits:
        first = visits[-1]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": first["latitude"],
                        "longitude": first["longitude"],
                        "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
                        "temperature_unit": "fahrenheit",
                        "wind_speed_unit": "mph",
                    },
                )
            if r.status_code == 200:
                c = r.json().get("current", {})
                weather = {
                    "temperature_f": c.get("temperature_2m"),
                    "wind_mph": c.get("wind_speed_10m"),
                    "precipitation": c.get("precipitation"),
                    "conditions": "Fetched from Open-Meteo",
                    "weather_code": c.get("weather_code"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            logger.warning(f"Weather for report failed: {e}")

    # Merge user-supplied projects with any derived from visits
    user_projects = [p.model_dump() for p in (data.projects or [])]
    if user_projects:
        # trust user-provided list as authoritative
        final_projects = user_projects
    else:
        # backward compat: derive one project per visit / group by project_id
        final_projects = _derive_projects_from_visits(visits)

    ai_context = {
        "author_name": user["name"],
        "author_role": user["role"],
        "report_date": today_iso,
        "project_code": data.project_code,
        "project_name": data.project_name,
        "highlights": data.highlights,
        "delays": data.delays,
        "change_orders": data.change_orders,
        "material_notes": data.material_notes,
        "visits": visits,
        "breaks": breaks,
        "sms_logs": sms_logs,
        "weather": weather,
        "priority_level": data.priority_level,
        "priority_flags": data.priority_flags,
        "projects": final_projects,
    }
    ai_summary = await build_ai_summary(ai_context)

    report = {
        "id": str(uuid4()),
        "user_id": user["id"],
        "author_name": user["name"],
        "author_role": user["role"],
        "project_code": data.project_code,
        "project_name": data.project_name,
        "report_date": today_iso,
        "ai_summary": ai_summary,
        "highlights": data.highlights,
        "delays": data.delays,
        "change_orders": data.change_orders,
        "material_notes": data.material_notes,
        "visits": visits,
        "breaks": breaks,
        "sms_logs": sms_logs,
        "weather": weather,
        "email_sent_to": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "priority_level": data.priority_level,
        "priority_flags": data.priority_flags,
        "projects": final_projects,
        "status": "submitted",
        "include_weather": data.include_weather,
        "include_visits": data.include_visits,
        "include_breaks": data.include_breaks,
        "include_sms": data.include_sms,
        "recipient_emails": [str(e) for e in data.recipient_emails],
    }
    await request.app.db.reports.insert_one(report.copy())
    report.pop("_id", None)

    # Any existing draft for today should be cleared to avoid resurrection
    await request.app.db.reports.delete_many(
        {"user_id": user["id"], "report_date": today_iso, "status": "draft"},
    )

    # Send emails to recipients
    if data.recipient_emails:
        sent = []
        for email in data.recipient_emails:
            html = _report_email_html(report)
            subject = f"Daily Report — {report['author_name']} — {today_iso}"
            eid = await send_email(to=str(email), subject=subject, html=html)
            if eid:
                sent.append(str(email))
        if sent:
            await request.app.db.reports.update_one({"id": report["id"]}, {"$set": {"email_sent_to": sent}})
            report["email_sent_to"] = sent

    return DailyReport(**report)


# ---------- Draft Reports ----------
# One rolling draft per user per day. Auto-saved silently as the user edits.
# Submit flips status to "submitted" and triggers AI summary + email delivery.
class DraftSave(BaseModel):
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    highlights: str = ""
    delays: str = ""
    change_orders: str = ""
    material_notes: str = ""
    include_weather: bool = True
    include_visits: bool = True
    include_breaks: bool = True
    include_sms: bool = True
    recipient_emails: List[EmailStr] = []
    priority_level: Optional[str] = None
    priority_flags: List[dict] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)


def _draft_shell(user: dict, today_iso: str) -> dict:
    """Blank draft shell with just metadata for a fresh day."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "user_id": user["id"],
        "author_name": user["name"],
        "author_role": user["role"],
        "project_code": None,
        "project_name": None,
        "report_date": today_iso,
        "ai_summary": "",
        "highlights": "",
        "delays": "",
        "change_orders": "",
        "material_notes": "",
        "visits": [],
        "breaks": [],
        "sms_logs": [],
        "weather": None,
        "email_sent_to": [],
        "created_at": now_iso,
        "updated_at": now_iso,
        "priority_level": None,
        "priority_flags": [],
        "projects": [],
        "status": "draft",
        "include_weather": True,
        "include_visits": True,
        "include_breaks": True,
        "include_sms": True,
        "recipient_emails": [],
    }


@api.get("/reports/draft/today")
async def get_todays_draft(request: Request, user: dict = Depends(current_user)):
    today_iso = datetime.now(timezone.utc).date().isoformat()
    doc = await request.app.db.reports.find_one(
        {"user_id": user["id"], "report_date": today_iso, "status": "draft", "deleted_at": None},
        {"_id": 0},
    )
    if not doc:
        return None
    if not doc.get("projects"):
        doc["projects"] = []
    return DailyReport(**doc)


@api.put("/reports/draft", response_model=DailyReport)
async def save_todays_draft(data: DraftSave, request: Request, user: dict = Depends(current_user)):
    today_iso = datetime.now(timezone.utc).date().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    existing = await request.app.db.reports.find_one(
        {"user_id": user["id"], "report_date": today_iso, "status": "draft", "deleted_at": None},
        {"_id": 0},
    )
    payload_projects = [p.model_dump() for p in (data.projects or [])]
    update_fields = {
        "project_code": data.project_code,
        "project_name": data.project_name,
        "highlights": data.highlights,
        "delays": data.delays,
        "change_orders": data.change_orders,
        "material_notes": data.material_notes,
        "include_weather": data.include_weather,
        "include_visits": data.include_visits,
        "include_breaks": data.include_breaks,
        "include_sms": data.include_sms,
        "recipient_emails": [str(e) for e in data.recipient_emails],
        "priority_level": data.priority_level,
        "priority_flags": data.priority_flags,
        "projects": payload_projects,
        "updated_at": now_iso,
    }
    if existing:
        await request.app.db.reports.update_one(
            {"id": existing["id"]}, {"$set": update_fields},
        )
        fresh = await request.app.db.reports.find_one({"id": existing["id"]}, {"_id": 0})
        return DailyReport(**fresh)

    shell = _draft_shell(user, today_iso)
    shell.update(update_fields)
    await request.app.db.reports.insert_one(shell.copy())
    shell.pop("_id", None)
    return DailyReport(**shell)


@api.post("/reports/draft/submit", response_model=DailyReport)
async def submit_todays_draft(request: Request, user: dict = Depends(current_user)):
    today_iso = datetime.now(timezone.utc).date().isoformat()
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    draft = await request.app.db.reports.find_one(
        {"user_id": user["id"], "report_date": today_iso, "status": "draft", "deleted_at": None},
        {"_id": 0},
    )
    if not draft:
        raise HTTPException(404, "No draft found for today")

    # Pull latest aggregated data at submit time (fresh snapshots)
    visits, breaks, sms_logs, weather = [], [], [], None
    if draft.get("include_visits", True):
        visits = await request.app.db.visits.find(
            {"user_id": user["id"], "timestamp": {"$gte": day_start}}, {"_id": 0},
        ).to_list(500)
    if draft.get("include_breaks", True):
        breaks = await request.app.db.breaks.find(
            {"user_id": user["id"], "started_at": {"$gte": day_start}}, {"_id": 0},
        ).to_list(500)
    if draft.get("include_sms", True):
        sms_logs = await request.app.db.sms_logs.find(
            {"user_id": user["id"], "timestamp": {"$gte": day_start}}, {"_id": 0},
        ).to_list(500)
    if draft.get("include_weather", True) and visits:
        first = visits[-1]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": first["latitude"],
                        "longitude": first["longitude"],
                        "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
                        "temperature_unit": "fahrenheit",
                        "wind_speed_unit": "mph",
                    },
                )
            if r.status_code == 200:
                c = r.json().get("current", {})
                weather = {
                    "temperature_f": c.get("temperature_2m"),
                    "wind_mph": c.get("wind_speed_10m"),
                    "precipitation": c.get("precipitation"),
                    "conditions": "Fetched from Open-Meteo",
                    "weather_code": c.get("weather_code"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            logger.warning(f"Weather for draft submit failed: {e}")

    user_projects = draft.get("projects") or []
    final_projects = user_projects if user_projects else _derive_projects_from_visits(visits)

    ai_context = {
        "author_name": user["name"],
        "author_role": user["role"],
        "report_date": today_iso,
        "project_code": draft.get("project_code"),
        "project_name": draft.get("project_name"),
        "highlights": draft.get("highlights", ""),
        "delays": draft.get("delays", ""),
        "change_orders": draft.get("change_orders", ""),
        "material_notes": draft.get("material_notes", ""),
        "visits": visits,
        "breaks": breaks,
        "sms_logs": sms_logs,
        "weather": weather,
        "priority_level": draft.get("priority_level"),
        "priority_flags": draft.get("priority_flags", []),
        "projects": final_projects,
    }
    ai_summary = await build_ai_summary(ai_context)

    now_iso = datetime.now(timezone.utc).isoformat()
    submit_updates = {
        "ai_summary": ai_summary,
        "visits": visits,
        "breaks": breaks,
        "sms_logs": sms_logs,
        "weather": weather,
        "projects": final_projects,
        "status": "submitted",
        "updated_at": now_iso,
        "created_at": draft.get("created_at", now_iso),
    }
    await request.app.db.reports.update_one({"id": draft["id"]}, {"$set": submit_updates})
    final = await request.app.db.reports.find_one({"id": draft["id"]}, {"_id": 0})

    # Send emails
    recipients = final.get("recipient_emails") or []
    if recipients:
        sent = []
        for email in recipients:
            html = _report_email_html(final)
            subject = f"Daily Report — {final['author_name']} — {today_iso}"
            eid = await send_email(to=str(email), subject=subject, html=html)
            if eid:
                sent.append(str(email))
        if sent:
            await request.app.db.reports.update_one({"id": final["id"]}, {"$set": {"email_sent_to": sent}})
            final["email_sent_to"] = sent

    return DailyReport(**final)


@api.delete("/reports/draft")
async def discard_todays_draft(request: Request, user: dict = Depends(current_user)):
    today_iso = datetime.now(timezone.utc).date().isoformat()
    res = await request.app.db.reports.delete_many(
        {"user_id": user["id"], "report_date": today_iso, "status": "draft"},
    )
    return {"ok": True, "removed": res.deleted_count}


def _summary_to_email_html(summary: str) -> str:
    """Convert the structured markdown summary into styled HTML for email delivery."""
    known = [
        "WORK COMPLETED",
        "COMMUNICATIONS",
        "WEATHER IMPACT",
        "DELAY / CONSTRAINTS",
        "CHANGE ORDER / MATERIALS",
        "NEXT STEPS",
        "OVERALL SUMMARY",
    ]
    sections: List[tuple] = []  # [(header, body_lines[])]
    current_header: Optional[str] = None
    current_lines: List[str] = []
    for raw in summary.splitlines():
        line = raw.strip()
        stripped = line.lstrip("#").strip().upper()
        if stripped in known and (line.startswith("##") or line.startswith("#")):
            if current_header:
                sections.append((current_header, current_lines))
            current_header = stripped
            current_lines = []
        else:
            if current_header is None:
                continue
            current_lines.append(line)
    if current_header:
        sections.append((current_header, current_lines))

    def _fmt_bullet(text: str) -> str:
        # Style [URGENT: ...] lines red
        if text.startswith("[URGENT:") or text.upper().startswith("- [URGENT:"):
            body = escape(text.lstrip("- ").strip())
            return f'<li style="color:#DC2626;font-weight:600">{body}</li>'
        body = text.lstrip("- ").strip()
        # Bold-highlight **...** as inline-emphasis with brand color
        body_html = escape(body)
        while "**" in body_html:
            body_html = body_html.replace(
                "**",
                '<strong style="color:#B45309;background:#FEF3C7;padding:1px 4px;border-radius:4px">',
                1,
            )
            if "**" in body_html:
                body_html = body_html.replace("**", "</strong>", 1)
        return f'<li style="margin-bottom:4px">{body_html}</li>'

    blocks = []
    for header, lines in sections:
        items = [l for l in lines if l and l != "-"]
        if not items:
            body_html = '<p style="color:#6B7280;margin:0">None reported today.</p>'
        else:
            bullet_lines = [l for l in items if l.startswith("- ") or l.startswith("[URGENT:")]
            if bullet_lines:
                body_html = "<ul style=\"padding-left:20px;margin:6px 0 0 0\">" + "".join(_fmt_bullet(l) for l in bullet_lines) + "</ul>"
            else:
                paragraphs = "".join(f'<p style="margin:0 0 6px 0">{escape(l)}</p>' for l in items)
                body_html = paragraphs
        blocks.append(
            f'<section style="margin:20px 0">'
            f'<h3 style="margin:0 0 8px 0;color:#111827;font-size:14px;text-transform:uppercase;'
            f'letter-spacing:0.5px;font-weight:700;border-bottom:2px solid #D97706;padding-bottom:4px;'
            f'display:inline-block">{escape(header)}</h3>'
            f'{body_html}'
            f'</section>'
        )
    return "".join(blocks)


def _priority_badge_html(level: Optional[str], flags: List[dict]) -> str:
    if not level and not flags:
        return ""
    color = {"High": "#DC2626", "Medium": "#D97706", "Low": "#4B5563"}.get(level or "", "#4B5563")
    chips = []
    if level:
        chips.append(
            f'<span style="background:{color};color:#fff;padding:4px 10px;border-radius:999px;'
            f'font-size:12px;font-weight:700;margin-right:6px">{escape(level)} PRIORITY</span>'
        )
    for f in flags:
        t = escape(f.get("type", ""))
        chips.append(
            f'<span style="background:#FEF3C7;color:#92400E;padding:3px 8px;border-radius:999px;'
            f'font-size:11px;font-weight:700;margin-right:4px;margin-top:4px;display:inline-block">'
            f'⚑ {t}</span>'
        )
    return f'<div style="margin:12px 0">{" ".join(chips)}</div>'


def _report_email_html(report: dict) -> str:
    body_html = _summary_to_email_html(report["ai_summary"])
    priority_html = _priority_badge_html(report.get("priority_level"), report.get("priority_flags", []))
    project = report.get("project_name") or report.get("project_code") or ""
    return (
        f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif;'
        f'background:#F9FAFB;padding:0">'
        f'<tr><td align="center" style="padding:24px">'
        f'<table role="presentation" width="600" style="background:#FFFFFF;border-radius:12px;'
        f'border:1px solid #E5E7EB">'
        f'<tr><td style="padding:24px">'
        f'<h2 style="margin:0 0 4px 0;color:#111827">Daily Field Report</h2>'
        f'<p style="margin:0;color:#6B7280;font-size:13px">{escape(report["report_date"])} · '
        f'<strong>{escape(report["author_name"])}</strong> ({escape(report["author_role"])})'
        f'{" · <strong>" + escape(project) + "</strong>" if project else ""}</p>'
        f'{priority_html}'
        f'<hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0">'
        f'{body_html}'
        f'<hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0">'
        f'<p style="font-size:12px;color:#6B7280;margin:0">Sent by {escape(EMAIL_FROM_NAME)}. '
        f'We never ask for your password or card details by email.</p>'
        f'</td></tr></table>'
        f'</td></tr></table>'
    )


@api.get("/reports", response_model=List[DailyReport])
async def list_reports(request: Request, user: dict = Depends(current_user), include_archived: bool = False, include_drafts: bool = False):
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] in FULL_ROLES or user.get("is_admin"):
        query: dict = {}
    else:
        query = {"user_id": user["id"]}
    query["deleted_at"] = None
    if not include_archived:
        query["$or"] = [{"archived": False}, {"archived": {"$exists": False}}]
    if not include_drafts:
        # Treat missing status as "submitted" for legacy backward compatibility
        query["$and"] = [{"$or": [{"status": {"$ne": "draft"}}, {"status": {"$exists": False}}]}]
    docs = await request.app.db.reports.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Backward compat: if a legacy report has no `projects`, derive from visits on the fly
    for d in docs:
        if not d.get("projects"):
            d["projects"] = _derive_projects_from_visits(d.get("visits", []))
    return [DailyReport(**d) for d in docs]


@api.get("/reports/{report_id}", response_model=DailyReport)
async def get_report(report_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] not in FULL_ROLES and not user.get("is_admin") and doc["user_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    if not doc.get("projects"):
        doc["projects"] = _derive_projects_from_visits(doc.get("visits", []))
    return DailyReport(**doc)


# ---------- Workday export ----------
@api.get("/reports/{report_id}/workday-export")
async def workday_export(report_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "employee", "role", "project_code", "project_name", "location_lat", "location_lon", "customer", "notes", "duration_min"])
    for v in doc.get("visits", []):
        writer.writerow([
            doc["report_date"], doc["author_name"], doc["author_role"],
            v.get("project_code") or doc.get("project_code") or "",
            doc.get("project_name") or "",
            v.get("latitude"), v.get("longitude"),
            v.get("customer_name") or "", v.get("notes") or "", "",
        ])
    for b in doc.get("breaks", []):
        writer.writerow([
            doc["report_date"], doc["author_name"], doc["author_role"],
            doc.get("project_code") or "", "BREAK", "", "",
            f"{b.get('break_type')} — {b.get('reason','')}", b.get("call_details") or "",
            b.get("duration_minutes") or "",
        ])
    csv_data = buf.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="workday-{report_id}.csv"'},
    )


# ---------- Voice-to-Notes (Whisper) ----------
@api.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), user: dict = Depends(current_user)):
    ALLOWED_EXT = {"m4a", "mp3", "mp4", "mpeg", "mpga", "wav", "webm"}
    fname = audio.filename or "recording.m4a"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "m4a"
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Unsupported audio format: {ext}")
    data = await audio.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio must be <= 25 MB")
    if len(data) == 0:
        raise HTTPException(400, "Empty audio")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        with open(tmp_path, "rb") as f:
            response = await stt.transcribe(
                file=f, model="whisper-1", response_format="json",
                prompt="Painting field report: highlights, delays, change orders, materials, crew, weather.",
            )
        text = ""
        if hasattr(response, "text"):
            text = response.text
        elif isinstance(response, dict):
            text = response.get("text", "")
        else:
            text = str(response)
        return {"text": (text or "").strip()}
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(502, f"Transcription failed: {str(e)}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ---------- Parse Project from Voice / Text ----------
class ParseProjectRequest(BaseModel):
    text: str


@api.post("/parse-project")
async def parse_project(data: ParseProjectRequest, _: dict = Depends(current_user)):
    """Convert dictated (or free-form) text into structured project fields.
    Returns a strict JSON object with keys matching ProjectEntry.
    Fields the LLM cannot infer are returned as null. Frontend should
    only overwrite fields the user hasn't already edited manually.
    """
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(400, "Empty text")
    if len(text) > 4000:
        text = text[:4000]

    system = (
        "You are a helpful parser for a painting field-crew mobile app. Given a short "
        "voice-dictated project description, extract structured fields. Return ONLY a "
        "single JSON object (no prose, no code fences, no explanation). Use null for "
        "any field you cannot confidently infer. Never invent facts.\n\n"
        "Schema (all fields optional, string unless noted):\n"
        "{\n"
        '  "customer_name": string | null,\n'
        '  "address": string | null,\n'
        '  "project_code": string | null,   // e.g. "P-1042"\n'
        '  "project_name": string | null,\n'
        '  "notes": string | null,          // the actual work performed\n'
        '  "materials_used": string | null, // paint, brushes, drop cloths, etc.\n'
        '  "start_time": string | null,     // "8:00 AM" format if mentioned\n'
        '  "end_time": string | null,\n'
        '  "touch_up": boolean,             // true if user mentioned touch-ups needed\n'
        '  "priority_flag": string | null   // one of: "Touch-Ups","Change Order",\n'
        '                                   // "Labor Issue","Property Damage",\n'
        '                                   // "Schedule Conflict","Wrong Materials"\n'
        "}\n"
        "If the crew mentioned it needs a return visit or touch-ups, set touch_up=true "
        "AND priority_flag=\"Touch-Ups\"."
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"parse-project-{uuid4()}",
            system_message=system,
        ).with_model("openai", "gpt-5.4")
        raw = await chat.send_message(UserMessage(text=text))
    except Exception as e:
        logger.error(f"parse_project LLM call failed: {e}")
        raise HTTPException(502, f"AI parse failed: {str(e)[:120]}")

    body = raw if isinstance(raw, str) else str(raw)
    # Extract the first JSON object from the response (LLMs sometimes wrap in fences)
    import json as _json
    body = body.strip()
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z]*\n?", "", body)
        body = re.sub(r"\n?```$", "", body)
    # Grab from first { to matching last }
    first = body.find("{")
    last = body.rfind("}")
    if first == -1 or last == -1 or last <= first:
        logger.warning(f"parse_project: no JSON object in response: {body[:200]!r}")
        return {
            "customer_name": None, "address": None, "project_code": None,
            "project_name": None, "notes": text[:280], "materials_used": None,
            "start_time": None, "end_time": None, "touch_up": False,
            "priority_flag": None,
        }
    try:
        parsed = _json.loads(body[first:last + 1])
    except Exception as e:
        logger.warning(f"parse_project: JSON parse failed: {e} :: {body[:200]!r}")
        return {
            "customer_name": None, "address": None, "project_code": None,
            "project_name": None, "notes": text[:280], "materials_used": None,
            "start_time": None, "end_time": None, "touch_up": False,
            "priority_flag": None,
        }

    # Normalize
    def _s(v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    result = {
        "customer_name": _s(parsed.get("customer_name")),
        "address": _s(parsed.get("address")),
        "project_code": _s(parsed.get("project_code")),
        "project_name": _s(parsed.get("project_name")),
        "notes": _s(parsed.get("notes")) or text[:280],
        "materials_used": _s(parsed.get("materials_used")),
        "start_time": _s(parsed.get("start_time")),
        "end_time": _s(parsed.get("end_time")),
        "touch_up": bool(parsed.get("touch_up", False)),
        "priority_flag": _s(parsed.get("priority_flag")),
    }
    return result


# ---------- Customer Directory ----------
class CustomerCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notes: Optional[str] = None
    project_code: Optional[str] = None


class Customer(CustomerCreate):
    id: str
    created_by: str
    created_at: str


@api.post("/customers", response_model=Customer, status_code=201)
async def create_customer(data: CustomerCreate, request: Request, user: dict = Depends(current_user)):
    doc = data.model_dump()
    doc.update({
        "id": str(uuid4()),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await request.app.db.customers.insert_one(doc.copy())
    doc.pop("_id", None)
    return Customer(**doc)


@api.get("/customers", response_model=List[Customer])
async def list_customers(request: Request, user: dict = Depends(current_user)):
    docs = await request.app.db.customers.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    return [Customer(**d) for d in docs]


@api.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, request: Request, _: dict = Depends(admin_only)):
    result = await request.app.db.customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Customer not found")
    return {"ok": True}


@api.get("/customers/history")
async def customer_history(name: str, request: Request, user: dict = Depends(current_user)):
    """Aggregate all visits, reports, and photos for a given customer NAME.
    Case-insensitive substring match on customer_name across visits and report projects.
    Access: any authenticated user can look up (management + field crew alike).
    """
    if not name or not name.strip():
        raise HTTPException(400, "customer name is required")
    name_re = re.compile(re.escape(name.strip()), re.IGNORECASE)

    # Customer directory record (best-effort match)
    customer = await request.app.db.customers.find_one({"name": name_re}, {"_id": 0})

    # All visits ever logged for this customer
    visits = await request.app.db.visits.find(
        {"customer_name": name_re}, {"_id": 0}
    ).sort("timestamp", -1).to_list(500)

    # All reports whose projects OR visits contain this customer
    report_docs = await request.app.db.reports.find(
        {
            "deleted_at": None,
            "$or": [
                {"visits.customer_name": name_re},
                {"projects.customer_name": name_re},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)

    reports_summary = [
        {
            "id": r["id"],
            "report_date": r["report_date"],
            "author_name": r.get("author_name"),
            "author_role": r.get("author_role"),
            "priority_level": r.get("priority_level"),
            "created_at": r.get("created_at"),
        }
        for r in report_docs
    ]

    # Photos from visits (may duplicate; frontend can de-dupe)
    photos = []
    for v in visits:
        for p in v.get("photos", []):
            photos.append({"path": p, "visit_id": v.get("id"), "timestamp": v.get("timestamp")})

    return {
        "customer": customer,
        "name": name,
        "visits": visits,
        "reports": reports_summary,
        "photos": photos,
        "counts": {
            "visits": len(visits),
            "reports": len(reports_summary),
            "photos": len(photos),
        },
    }


# ---------- Weekly Digest ----------
class DigestRequest(BaseModel):
    recipient_emails: List[EmailStr]


@api.post("/digest/weekly")
async def weekly_digest(data: DigestRequest, request: Request, admin: dict = Depends(admin_only)):
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    reports = await request.app.db.reports.find(
        {"created_at": {"$gte": week_ago}}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    if not reports:
        raise HTTPException(400, "No reports in the last 7 days")

    lines = [f"Weekly Digest — {len(reports)} reports across the past 7 days.", ""]
    total_visits = sum(len(r.get("visits", [])) for r in reports)
    total_breaks = sum(len(r.get("breaks", [])) for r in reports)
    total_sms = sum(len(r.get("sms_logs", [])) for r in reports)
    change_order_notes = [r.get("change_orders") for r in reports if r.get("change_orders")]
    delay_notes = [r.get("delays") for r in reports if r.get("delays")]

    lines.append(f"Totals: {total_visits} visits, {total_breaks} breaks, {total_sms} communications")
    lines.append(f"Change orders logged: {len(change_order_notes)}")
    lines.append(f"Days with delays: {len(delay_notes)}")
    lines.append("")
    lines.append("Individual report summaries:")
    for r in reports[:20]:
        lines.append(f"[{r['report_date']}] {r['author_name']} ({r['author_role']}) — {r.get('project_name') or r.get('project_code') or 'Unspecified'}")
        lines.append(r["ai_summary"][:600])
        lines.append("")

    prompt = (
        "You are the operations manager writing a weekly executive digest to the owner. "
        "Summarize the following daily reports from the last 7 days. Highlight: "
        "1) top wins, 2) recurring delays/root causes, 3) change orders and their revenue impact if visible, "
        "4) customer or subcontractor escalations, 5) weather impact patterns, 6) recommended next-week actions. "
        "Write 400-600 words, professional and concise, with short headed sections."
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"digest-{uuid4()}",
            system_message=prompt,
        ).with_model("openai", "gpt-5.4")
        digest_text = await chat.send_message(UserMessage(text="\n".join(lines)))
        digest_text = digest_text if isinstance(digest_text, str) else str(digest_text)
    except Exception as e:
        logger.error(f"Digest AI failed: {e}")
        digest_text = "\n".join(lines)

    digest_id = str(uuid4())
    digest_doc = {
        "id": digest_id,
        "created_by": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report_ids": [r["id"] for r in reports],
        "text": digest_text,
        "totals": {"visits": total_visits, "breaks": total_breaks, "sms": total_sms,
                   "change_orders": len(change_order_notes), "delays": len(delay_notes)},
        "email_sent_to": [],
    }
    await request.app.db.digests.insert_one(digest_doc.copy())

    summary_html = escape(digest_text).replace("\n", "<br>")
    subject = f"Weekly Ops Digest — {datetime.now(timezone.utc).date().isoformat()}"
    html = (
        f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif">'
        f'<tr><td style="padding:24px">'
        f'<h2 style="margin:0 0 12px 0;color:#111827">Weekly Operations Digest</h2>'
        f'<p style="color:#374151;margin:0 0 16px 0">{len(reports)} reports · '
        f'{total_visits} visits · {total_breaks} breaks · {total_sms} comms</p>'
        f'<hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0">'
        f'<div style="color:#111827;line-height:1.6">{summary_html}</div>'
        f'<hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0">'
        f'<p style="font-size:12px;color:#6B7280;margin:0">Sent by {escape(EMAIL_FROM_NAME)}. '
        f'We never ask for your password or card details by email.</p>'
        f'</td></tr></table>'
    )

    sent = []
    for email in data.recipient_emails:
        eid = await send_email(to=str(email), subject=subject, html=html)
        if eid:
            sent.append(str(email))
    if sent:
        await request.app.db.digests.update_one({"id": digest_id}, {"$set": {"email_sent_to": sent}})
        digest_doc["email_sent_to"] = sent

    digest_doc.pop("_id", None)
    return digest_doc


# ---------- Report Signature ----------
class SignaturePayload(BaseModel):
    customer_name: str
    signature_base64: str


@api.patch("/reports/{report_id}/signature")
async def add_signature(report_id: str, data: SignaturePayload, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] not in FULL_ROLES and not user.get("is_admin") and doc["user_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    signature = {
        "customer_name": data.customer_name,
        "signature_base64": data.signature_base64,
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    await request.app.db.reports.update_one({"id": report_id}, {"$set": {"signature": signature}})
    return {"ok": True, "signature": signature}


# ---------- Recipient Groups ----------
class RecipientGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    emails: List[EmailStr] = Field(default_factory=list)


class RecipientGroup(BaseModel):
    id: str
    name: str
    emails: List[EmailStr]
    created_by: str
    created_at: str


DEFAULT_BREAK_TYPES = ["Bathroom", "Lunch", "Personal", "Admin Call"]
DEFAULT_PRIORITY_FLAGS = [
    {"type": "Change Order", "requires_reason": False},
    {"type": "Customer Escalation (Owner Level)", "requires_reason": False},
    {"type": "Customer Escalation (PM Level)", "requires_reason": False},
    {"type": "Scope of Work Dispute", "requires_reason": True},
    {"type": "Labor Issue", "requires_reason": True},
    {"type": "Property Damage", "requires_reason": True},
    {"type": "Schedule Conflict", "requires_reason": True},
    {"type": "Missing Project Details", "requires_reason": False},
    {"type": "Delay of Payment", "requires_reason": True},
    {"type": "Wrong Materials", "requires_reason": False},
    {"type": "Touch-Ups", "requires_reason": False},
]


class UserListsPayload(BaseModel):
    break_types: List[str] = Field(default_factory=list)
    priority_flags: List[dict] = Field(default_factory=list)


@api.get("/settings/lists")
async def get_user_lists(request: Request, user: dict = Depends(current_user)):
    """Return the current user's customizable pickable lists (break types + priority flags).
    Falls back to sensible defaults on first read.
    """
    doc = await request.app.db.user_settings.find_one({"user_id": user["id"]}, {"_id": 0})
    if not doc:
        return {
            "break_types": list(DEFAULT_BREAK_TYPES),
            "priority_flags": list(DEFAULT_PRIORITY_FLAGS),
            "is_default": True,
        }
    return {
        "break_types": doc.get("break_types") or list(DEFAULT_BREAK_TYPES),
        "priority_flags": doc.get("priority_flags") or list(DEFAULT_PRIORITY_FLAGS),
        "is_default": False,
    }


@api.put("/settings/lists")
async def put_user_lists(
    data: UserListsPayload,
    request: Request,
    user: dict = Depends(current_user),
):
    seen: set = set()
    breaks: List[str] = []
    for b in data.break_types:
        s = (b or "").strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        breaks.append(s[:40])

    seen_f: set = set()
    flags: List[dict] = []
    for f in data.priority_flags:
        t = str(f.get("type") or "").strip()
        if not t:
            continue
        k = t.lower()
        if k in seen_f:
            continue
        seen_f.add(k)
        flags.append({
            "type": t[:60],
            "requires_reason": bool(f.get("requires_reason", False)),
        })

    await request.app.db.user_settings.update_one(
        {"user_id": user["id"]},
        {"$set": {
            "user_id": user["id"],
            "break_types": breaks,
            "priority_flags": flags,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"break_types": breaks, "priority_flags": flags, "is_default": False}


@api.post("/settings/lists/reset")
async def reset_user_lists(request: Request, user: dict = Depends(current_user)):
    await request.app.db.user_settings.delete_one({"user_id": user["id"]})
    return {
        "break_types": list(DEFAULT_BREAK_TYPES),
        "priority_flags": list(DEFAULT_PRIORITY_FLAGS),
        "is_default": True,
    }



@api.post("/recipient-groups", response_model=RecipientGroup, status_code=201)
async def create_group(data: RecipientGroupCreate, request: Request, admin: dict = Depends(admin_only)):
    doc = {
        "id": str(uuid4()),
        "name": data.name,
        "emails": [str(e) for e in data.emails],
        "created_by": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await request.app.db.recipient_groups.insert_one(doc.copy())
    doc.pop("_id", None)
    return RecipientGroup(**doc)


@api.get("/recipient-groups", response_model=List[RecipientGroup])
async def list_groups(request: Request, user: dict = Depends(current_user)):
    docs = await request.app.db.recipient_groups.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return [RecipientGroup(**d) for d in docs]


@api.patch("/recipient-groups/{group_id}", response_model=RecipientGroup)
async def update_group(group_id: str, data: RecipientGroupCreate, request: Request, _: dict = Depends(admin_only)):
    result = await request.app.db.recipient_groups.find_one_and_update(
        {"id": group_id},
        {"$set": {"name": data.name, "emails": [str(e) for e in data.emails]}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(404, "Group not found")
    return RecipientGroup(**result)


@api.delete("/recipient-groups/{group_id}")
async def delete_group(group_id: str, request: Request, _: dict = Depends(admin_only)):
    r = await request.app.db.recipient_groups.delete_one({"id": group_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Group not found")
    return {"ok": True}


# ---------- Regenerate report summary ----------
@api.post("/reports/{report_id}/regenerate-summary", response_model=DailyReport)
async def regenerate_summary(report_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await _report_owner_check(request, report_id, user)
    ai_context = {
        "author_name": doc["author_name"],
        "author_role": doc["author_role"],
        "report_date": doc["report_date"],
        "project_code": doc.get("project_code"),
        "project_name": doc.get("project_name"),
        "highlights": doc.get("highlights", ""),
        "delays": doc.get("delays", ""),
        "change_orders": doc.get("change_orders", ""),
        "material_notes": doc.get("material_notes", ""),
        "visits": doc.get("visits", []),
        "breaks": doc.get("breaks", []),
        "sms_logs": doc.get("sms_logs", []),
        "weather": doc.get("weather"),
        "priority_level": doc.get("priority_level"),
        "priority_flags": doc.get("priority_flags", []),
    }
    new_summary = await build_ai_summary(ai_context)
    await request.app.db.reports.update_one(
        {"id": report_id},
        {"$set": {
            "ai_summary": new_summary,
            "tts_cache": None,
            "regenerated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    fresh = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    return DailyReport(**fresh)


# ---------- ElevenLabs TTS ----------
@api.post("/reports/{report_id}/tts")
async def report_tts(report_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.reports.find_one({"id": report_id, "deleted_at": None}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] not in FULL_ROLES and not user.get("is_admin") and doc["user_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    # Trim summary to something reasonable for TTS budget
    text = (doc.get("ai_summary") or "").strip()
    if not text:
        raise HTTPException(400, "Report has no summary to read")
    # Strip markdown-style marks so the voice does not read "*", "#", or "_" aloud
    tts_text = re.sub(r"[*_#>~|`]", "", text)
    tts_text = re.sub(r"https?://\S+", "", tts_text)
    tts_text = re.sub(r"\s+", " ", tts_text).strip()
    tts_text = tts_text[:2500]

    import hashlib
    summary_hash = hashlib.sha256(tts_text.encode()).hexdigest()[:16]
    cached = doc.get("tts_cache")
    if cached and cached.get("hash") == summary_hash and cached.get("audio_data_url"):
        return {
            "audio_data_url": cached["audio_data_url"],
            "bytes": cached.get("bytes", 0),
            "cached": True,
            "voice_provider": cached.get("voice_provider", "elevenlabs"),
        }

    def _synthesize_elevenlabs() -> bytes:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        stream = client.text_to_speech.convert(
            text=tts_text,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        chunks = b""
        for c in stream:
            if c:
                chunks += c
        return chunks

    async def _synthesize_openai() -> bytes:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        return await tts.generate_speech(
            text=tts_text,
            model="tts-1",
            voice="onyx",
            response_format="mp3",
        )

    audio: bytes = b""
    voice_provider = "elevenlabs"
    el_error: str | None = None

    if ELEVENLABS_API_KEY:
        try:
            audio = await run_in_threadpool(_synthesize_elevenlabs)
        except Exception as e:
            detail = ""
            body = getattr(e, "body", None)
            if isinstance(body, dict):
                d = body.get("detail")
                if isinstance(d, dict):
                    detail = d.get("message") or ""
                elif isinstance(d, str):
                    detail = d
            status_code = getattr(e, "status_code", None)
            el_error = f"status={status_code} detail={detail!r}"
            logger.warning(f"ElevenLabs TTS failed, falling back to OpenAI TTS: {el_error}")
            audio = b""

    # Fallback (or primary if no ElevenLabs key) → Emergent-managed OpenAI TTS
    if not audio:
        try:
            audio = await _synthesize_openai()
            voice_provider = "openai"
        except Exception as e:
            logger.error(f"OpenAI TTS fallback also failed: {e!r}")
            if el_error:
                raise HTTPException(
                    502,
                    "Voice generation temporarily unavailable. ElevenLabs quota exhausted "
                    "and OpenAI fallback failed. Please try again shortly.",
                )
            raise HTTPException(502, f"TTS failed: {str(e)[:160]}")

    if not audio:
        raise HTTPException(502, "TTS produced no audio")

    b64 = _b64.b64encode(audio).decode()
    audio_data_url = f"data:audio/mpeg;base64,{b64}"
    await request.app.db.reports.update_one(
        {"id": report_id},
        {"$set": {"tts_cache": {
            "hash": summary_hash,
            "audio_data_url": audio_data_url,
            "bytes": len(audio),
            "voice_provider": voice_provider,
        }}},
    )
    return {
        "audio_data_url": audio_data_url,
        "bytes": len(audio),
        "cached": False,
        "voice_provider": voice_provider,
    }


# ---------- Object Storage helpers (Emergent managed) ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "paintops-daily"
_storage_key: Optional[str] = None


def _init_storage() -> Optional[str]:
    global _storage_key
    if _storage_key:
        return _storage_key
    try:
        resp = requests.post(
            f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30
        )
        if resp.status_code >= 400:
            logger.error(f"Storage init {resp.status_code}: {resp.text[:200]}")
            return None
        _storage_key = resp.json()["storage_key"]
        return _storage_key
    except Exception as e:
        logger.error(f"Storage init exception: {e}")
        return None


def _put_object(path: str, data: bytes, content_type: str) -> Optional[dict]:
    global _storage_key
    key = _init_storage()
    if not key:
        return None
    for attempt in range(2):
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
        if resp.status_code == 503 and attempt == 0:
            _storage_key = None
            key = _init_storage()
            if not key:
                return None
            continue
        if resp.status_code >= 400:
            logger.error(f"Storage put {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()
    return None


def _get_object(path: str) -> Optional[tuple]:
    global _storage_key
    key = _init_storage()
    if not key:
        return None
    for attempt in range(2):
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key},
            timeout=60,
        )
        if resp.status_code == 503 and attempt == 0:
            _storage_key = None
            key = _init_storage()
            if not key:
                return None
            continue
        if resp.status_code >= 400:
            return None
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
    return None


# ---------- Photo Attachments ----------
@api.post("/visits/{visit_id}/photos")
async def upload_visit_photo(
    visit_id: str,
    request: Request,
    photo: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    visit = await request.app.db.visits.find_one({"id": visit_id, "user_id": user["id"]}, {"_id": 0})
    if not visit:
        raise HTTPException(404, "Visit not found")
    if len(visit.get("photos", [])) >= 3:
        raise HTTPException(400, "Max 3 photos per visit")
    data = await photo.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty photo")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Photo must be <= 8 MB")
    ext = "jpg"
    if photo.filename and "." in photo.filename:
        ext = photo.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "heic"):
        ext = "jpg"
    obj_path = f"{APP_NAME}/uploads/{user['id']}/{uuid4()}.{ext}"
    result = await run_in_threadpool(_put_object, obj_path, data, photo.content_type or f"image/{ext}")
    if not result:
        raise HTTPException(502, "Photo upload failed")
    await request.app.db.visits.update_one(
        {"id": visit_id}, {"$push": {"photos": obj_path}}
    )
    return {"ok": True, "path": obj_path}


@api.get("/files/{path:path}")
async def get_file(path: str, request: Request, token: Optional[str] = None):
    # Auth: either Bearer header (via current_user) or a short-lived token in ?token=
    auth_ok = False
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            claims = jwt.decode(auth[7:], JWT_SECRET, algorithms=[ALGORITHM], issuer=JWT_ISSUER)
            if claims.get("sub"):
                auth_ok = True
        except Exception:
            pass
    if not auth_ok and token:
        try:
            claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM], issuer=JWT_ISSUER)
            if claims.get("sub"):
                auth_ok = True
        except Exception:
            pass
    if not auth_ok:
        raise HTTPException(401, "Auth required")
    result = await run_in_threadpool(_get_object, path)
    if not result:
        raise HTTPException(404, "File not found")
    content, content_type = result
    return Response(content=content, media_type=content_type)


# ---------- Report Edit / Archive / Delete / Portal Link ----------
class ReportPatch(BaseModel):
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    highlights: Optional[str] = None
    delays: Optional[str] = None
    change_orders: Optional[str] = None
    material_notes: Optional[str] = None


async def _report_owner_check(request: Request, report_id: str, user: dict) -> dict:
    doc = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] not in FULL_ROLES and not user.get("is_admin") and doc["user_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    return doc


@api.patch("/reports/{report_id}", response_model=DailyReport)
async def edit_report(report_id: str, patch: ReportPatch, request: Request, user: dict = Depends(current_user)):
    await _report_owner_check(request, report_id, user)
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await request.app.db.reports.update_one({"id": report_id}, {"$set": updates})
    doc = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    return DailyReport(**doc)


@api.post("/reports/{report_id}/archive")
async def archive_report(report_id: str, request: Request, user: dict = Depends(current_user)):
    await _report_owner_check(request, report_id, user)
    await request.app.db.reports.update_one(
        {"id": report_id},
        {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@api.post("/reports/{report_id}/unarchive")
async def unarchive_report(report_id: str, request: Request, user: dict = Depends(current_user)):
    await _report_owner_check(request, report_id, user)
    await request.app.db.reports.update_one(
        {"id": report_id}, {"$set": {"archived": False, "archived_at": None}},
    )
    return {"ok": True}


@api.delete("/reports/{report_id}")
async def delete_report(report_id: str, request: Request, user: dict = Depends(current_user)):
    await _report_owner_check(request, report_id, user)
    # Soft delete per data management rules
    await request.app.db.reports.update_one(
        {"id": report_id}, {"$set": {"deleted_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@api.post("/reports/{report_id}/portal-link")
async def create_portal_link(report_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await _report_owner_check(request, report_id, user)
    token = doc.get("public_token")
    if not token:
        token = secrets.token_urlsafe(24)
        await request.app.db.reports.update_one({"id": report_id}, {"$set": {"public_token": token}})
    return {"token": token}


@api.delete("/reports/{report_id}/portal-link")
async def revoke_portal_link(report_id: str, request: Request, user: dict = Depends(current_user)):
    await _report_owner_check(request, report_id, user)
    await request.app.db.reports.update_one({"id": report_id}, {"$set": {"public_token": None}})
    return {"ok": True}


@api.get("/public/reports/{token}", response_class=HTMLResponse)
async def public_report(token: str, request: Request):
    doc = await request.app.db.reports.find_one({"public_token": token, "deleted_at": None}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    return HTMLResponse(_render_public_report_html(doc, token))


class PublicRespond(BaseModel):
    project_id: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_email: Optional[EmailStr] = None
    message: str = Field(min_length=1, max_length=5000)


@api.post("/public/reports/{token}/respond", response_model=ReportResponse)
async def public_respond(token: str, data: PublicRespond, request: Request):
    report = await request.app.db.reports.find_one({"public_token": token, "deleted_at": None}, {"_id": 0})
    if not report:
        raise HTTPException(404, "Report not found")

    project_label = None
    project_flag = None
    if data.project_id:
        for p in report.get("projects", []) or []:
            if p.get("id") == data.project_id:
                project_label = (
                    p.get("project_name")
                    or p.get("customer_name")
                    or p.get("project_code")
                    or (p.get("address") or "")[:60]
                    or f"Project {data.project_id[:6]}"
                )
                project_flag = p.get("priority_flag")
                break

    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid4()),
        "report_id": report["id"],
        "report_user_id": report["user_id"],
        "project_id": data.project_id,
        "project_label": project_label,
        "project_flag": project_flag,
        "reporter_name": (data.reporter_name or "").strip() or None,
        "reporter_email": str(data.reporter_email) if data.reporter_email else None,
        "message": data.message.strip(),
        "created_at": now_iso,
        "read_at": None,
        "archived": False,
    }
    await request.app.db.report_responses.insert_one(doc.copy())
    doc.pop("_id", None)

    # Notify the report author by email (best-effort)
    try:
        subject = f"New reply on your daily report — {report['report_date']}"
        who = doc["reporter_name"] or doc["reporter_email"] or "Someone"
        job_line = f"Job: <b>{escape(project_label)}</b>" + (f" · flag: {escape(project_flag)}" if project_flag else "") if project_label else "General reply"
        html_body = (
            f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif">'
            f'<tr><td style="padding:24px">'
            f'<h2 style="margin:0 0 10px 0;color:#111827">New reply on your report</h2>'
            f'<p style="color:#374151;margin:0 0 8px 0">From: <b>{escape(who)}</b></p>'
            f'<p style="color:#374151;margin:0 0 8px 0">{job_line}</p>'
            f'<div style="background:#F3F4F6;border-radius:8px;padding:14px;color:#111827;line-height:1.6">'
            f'{escape(doc["message"]).replace(chr(10), "<br>")}'
            f'</div>'
            f'<p style="font-size:12px;color:#6B7280;margin-top:16px">Open Summar-Eeze → Mail tab to reply or archive.</p>'
            f'</td></tr></table>'
        )
        # look up author email
        author = await request.app.db.users.find_one({"id": report["user_id"]}, {"_id": 0, "email": 1})
        if author and author.get("email"):
            await send_email(to=author["email"], subject=subject, html=html_body)
    except Exception as e:
        logger.warning(f"Response notification email failed: {e}")

    return ReportResponse(**doc)


@api.get("/responses", response_model=List[ReportResponse])
async def list_responses(
    request: Request,
    user: dict = Depends(current_user),
    include_archived: bool = False,
    unread_only: bool = False,
    include_outbound: bool = False,
):
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] in FULL_ROLES or user.get("is_admin"):
        query: dict = {}
    else:
        query = {"report_user_id": user["id"]}
    if not include_archived:
        query["archived"] = {"$ne": True}
    if unread_only:
        query["read_at"] = None
    if not include_outbound:
        # Hide owner's own outbound replies from the inbox list
        query["direction"] = {"$ne": "outbound"}
    docs = await request.app.db.report_responses.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [ReportResponse(**d) for d in docs]


@api.get("/responses/unread-count")
async def unread_response_count(request: Request, user: dict = Depends(current_user)):
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] in FULL_ROLES or user.get("is_admin"):
        query: dict = {}
    else:
        query = {"report_user_id": user["id"]}
    query["archived"] = {"$ne": True}
    query["read_at"] = None
    query["direction"] = {"$ne": "outbound"}
    count = await request.app.db.report_responses.count_documents(query)
    return {"count": count}


@api.get("/reports/{report_id}/responses", response_model=List[ReportResponse])
async def list_report_responses(report_id: str, request: Request, user: dict = Depends(current_user)):
    await _report_owner_check(request, report_id, user)
    docs = await request.app.db.report_responses.find({"report_id": report_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [ReportResponse(**d) for d in docs]


async def _response_owner_check(request: Request, response_id: str, user: dict) -> dict:
    doc = await request.app.db.report_responses.find_one({"id": response_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Response not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] not in FULL_ROLES and not user.get("is_admin") and doc["report_user_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    return doc


@api.patch("/responses/{response_id}/read", response_model=ReportResponse)
async def mark_response_read(response_id: str, request: Request, user: dict = Depends(current_user)):
    await _response_owner_check(request, response_id, user)
    await request.app.db.report_responses.update_one(
        {"id": response_id},
        {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
    )
    doc = await request.app.db.report_responses.find_one({"id": response_id}, {"_id": 0})
    return ReportResponse(**doc)


@api.patch("/responses/{response_id}/unread", response_model=ReportResponse)
async def mark_response_unread(response_id: str, request: Request, user: dict = Depends(current_user)):
    await _response_owner_check(request, response_id, user)
    await request.app.db.report_responses.update_one(
        {"id": response_id}, {"$set": {"read_at": None}},
    )
    doc = await request.app.db.report_responses.find_one({"id": response_id}, {"_id": 0})
    return ReportResponse(**doc)


@api.post("/responses/{response_id}/archive", response_model=ReportResponse)
async def archive_response(response_id: str, request: Request, user: dict = Depends(current_user)):
    await _response_owner_check(request, response_id, user)
    await request.app.db.report_responses.update_one(
        {"id": response_id}, {"$set": {"archived": True}},
    )
    doc = await request.app.db.report_responses.find_one({"id": response_id}, {"_id": 0})
    return ReportResponse(**doc)


class OwnerReply(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    photos: List[str] = Field(default_factory=list, max_length=4)


@api.post("/responses/upload-photo")
async def upload_response_photo(
    request: Request,
    photo: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    """Upload a single photo for an outbound reply. Returns an object-storage path the client
    then passes in POST /api/responses/{id}/reply as part of `photos`."""
    data = await photo.read()
    if len(data) == 0:
        raise HTTPException(400, "Empty photo")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Photo must be <= 8 MB")
    ext = "jpg"
    if photo.filename and "." in photo.filename:
        ext = photo.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "heic"):
        ext = "jpg"
    obj_path = f"{APP_NAME}/replies/{user['id']}/{uuid4()}.{ext}"
    result = await run_in_threadpool(_put_object, obj_path, data, photo.content_type or f"image/{ext}")
    if not result:
        raise HTTPException(502, "Photo upload failed")
    return {"ok": True, "path": obj_path}


@api.get("/responses/{response_id}/thread", response_model=List[ReportResponse])
async def get_response_thread(response_id: str, request: Request, user: dict = Depends(current_user)):
    """Return the full thread for a response: parent (root inbound reply) + all owner follow-ups,
    sorted oldest → newest."""
    root = await _response_owner_check(request, response_id, user)
    root_id = root.get("parent_id") or root["id"]
    docs = await request.app.db.report_responses.find(
        {"$or": [{"id": root_id}, {"parent_id": root_id}]}, {"_id": 0},
    ).sort("created_at", 1).to_list(500)
    return [ReportResponse(**d) for d in docs]


@api.post("/responses/{response_id}/reply", response_model=ReportResponse)
async def reply_to_response(
    response_id: str, data: OwnerReply, request: Request, user: dict = Depends(current_user),
):
    """Owner-side reply back to the original respondent.

    - Verifies the current user owns the response (or is in a privileged role).
    - Creates a new ReportResponse with direction='outbound', parent_id=root, author_user_id=user.id.
    - If the original respondent left an email, sends them the reply as a plain email.
    """
    root = await _response_owner_check(request, response_id, user)
    root_id = root.get("parent_id") or root["id"]
    parent = root
    if root.get("parent_id"):
        parent = await request.app.db.report_responses.find_one({"id": root_id}, {"_id": 0}) or root

    report = await request.app.db.reports.find_one({"id": root["report_id"]}, {"_id": 0})
    now_iso = datetime.now(timezone.utc).isoformat()
    author_name = user.get("name") or "Field team"
    recipient_email = parent.get("reporter_email")

    doc = {
        "id": str(uuid4()),
        "report_id": root["report_id"],
        "report_user_id": root["report_user_id"],
        "project_id": parent.get("project_id"),
        "project_label": parent.get("project_label"),
        "project_flag": parent.get("project_flag"),
        "reporter_name": author_name,
        "reporter_email": None,
        "message": data.message.strip(),
        "created_at": now_iso,
        "read_at": now_iso,  # own replies are implicitly read
        "archived": False,
        "parent_id": root_id,
        "direction": "outbound",
        "author_user_id": user["id"],
        "email_delivered": False,
        "photos": data.photos or [],
    }

    # Resolve attachment images once (so we only hit storage per unique path)
    attachment_imgs_html = ""
    if doc["photos"]:
        imgs = []
        for p in doc["photos"][:4]:
            try:
                fetched = await run_in_threadpool(_get_object, p)
                if not fetched:
                    continue
                content, content_type = fetched
                b64 = _b64.b64encode(content).decode()
                imgs.append(
                    f'<img src="data:{content_type};base64,{b64}" '
                    f'style="max-width:260px;max-height:260px;border-radius:8px;'
                    f'margin:6px 6px 0 0;border:1px solid #E5E7EB;object-fit:cover" />'
                )
            except Exception as e:
                logger.warning(f"Reply attachment embed failed for {p}: {e}")
        if imgs:
            attachment_imgs_html = (
                '<div style="margin-top:12px;display:flex;flex-wrap:wrap">'
                + "".join(imgs)
                + "</div>"
            )

    delivered = False
    if recipient_email:
        try:
            report_date = (report or {}).get("report_date") or ""
            job_line = (
                f'<p style="color:#374151;margin:0 0 8px 0">Job: <b>{escape(parent.get("project_label") or "General")}</b></p>'
                if parent.get("project_label") else ""
            )
            portal_token = (report or {}).get("public_token")
            portal_line = ""
            if portal_token:
                base = (os.getenv("EXPO_PUBLIC_BACKEND_URL") or os.getenv("BACKEND_PUBLIC_URL") or "").rstrip("/")
                if not base:
                    # fall back to Request's base URL
                    base = str(request.base_url).rstrip("/")
                portal_line = (
                    f'<p style="font-size:12px;color:#6B7280;margin-top:16px">'
                    f'View the full report: <a href="{base}/api/public/reports/{portal_token}">open report →</a>'
                    f'</p>'
                )
            prev_block = ""
            if parent.get("message"):
                prev_block = (
                    f'<div style="margin-top:16px;padding-top:12px;border-top:1px solid #E5E7EB;color:#6B7280;font-size:12px">'
                    f'<div style="margin-bottom:6px">On {escape(parent.get("created_at", "")[:10])}, you wrote:</div>'
                    f'<div style="padding:10px;background:#F3F4F6;border-radius:6px;color:#374151;line-height:1.55">'
                    f'{escape(parent["message"]).replace(chr(10), "<br>")}'
                    f'</div></div>'
                )
            subject = f"Reply from {author_name} — Daily Report {report_date}".strip()
            html_body = (
                f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif">'
                f'<tr><td style="padding:24px">'
                f'<h2 style="margin:0 0 10px 0;color:#111827">{escape(author_name)} replied</h2>'
                f'{job_line}'
                f'<div style="background:#FFF7ED;border-left:3px solid #F97316;border-radius:6px;'
                f'padding:14px;color:#111827;line-height:1.6">'
                f'{escape(doc["message"]).replace(chr(10), "<br>")}'
                f'</div>'
                f'{attachment_imgs_html}'
                f'{portal_line}'
                f'{prev_block}'
                f'</td></tr></table>'
            )
            eid = await send_email(to=recipient_email, subject=subject, html=html_body)
            delivered = bool(eid)
        except Exception as e:
            logger.warning(f"Owner reply email failed: {e}")

    doc["email_delivered"] = delivered
    await request.app.db.report_responses.insert_one(doc.copy())
    doc.pop("_id", None)

    # Mark the parent as read if it wasn't already
    if parent and not parent.get("read_at"):
        await request.app.db.report_responses.update_one(
            {"id": parent["id"]}, {"$set": {"read_at": now_iso}},
        )

    return ReportResponse(**doc)


@api.delete("/responses/{response_id}")
async def delete_response(response_id: str, request: Request, user: dict = Depends(current_user)):
    await _response_owner_check(request, response_id, user)
    await request.app.db.report_responses.delete_one({"id": response_id})
    return {"ok": True}


# Project-level summary PATCH — update a single project's `summary` on a report
class ProjectSummaryPatch(BaseModel):
    summary: Optional[str] = Field(default=None, max_length=1000)


@api.patch("/reports/{report_id}/projects/{project_id}/summary", response_model=DailyReport)
async def patch_project_summary(
    report_id: str,
    project_id: str,
    patch: ProjectSummaryPatch,
    request: Request,
    user: dict = Depends(current_user),
):
    doc = await _report_owner_check(request, report_id, user)
    projects = doc.get("projects") or []
    hit = False
    for p in projects:
        if p.get("id") == project_id:
            p["summary"] = (patch.summary or "").strip() or None
            hit = True
            break
    if not hit:
        raise HTTPException(404, "Project not found on this report")
    await request.app.db.reports.update_one(
        {"id": report_id},
        {"$set": {"projects": projects, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    fresh = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    return DailyReport(**fresh)


def _render_public_report_html(doc: dict, token: str) -> str:
    """Render a lightweight public-view HTML page with per-flagged-job Respond buttons."""
    report_date = escape(str(doc.get("report_date") or ""))
    author = escape(str(doc.get("author_name") or ""))
    role = escape(str(doc.get("author_role") or ""))
    title = escape(str(doc.get("project_name") or doc.get("project_code") or "Daily Report"))
    ai_summary = escape(str(doc.get("ai_summary") or "")).replace("\n", "<br>")
    projects = doc.get("projects") or []

    def flag_badge(flag: Optional[str]) -> str:
        if not flag:
            return ""
        return (
            f'<span style="display:inline-block;padding:2px 8px;background:#FEE2E2;color:#B91C1C;'
            f'border-radius:999px;font-size:11px;font-weight:700;margin-left:6px">{escape(flag)}</span>'
        )

    projects_html = ""
    for p in projects:
        pid = escape(str(p.get("id") or ""))
        plabel = escape(str(
            p.get("project_name") or p.get("customer_name") or p.get("project_code") or (p.get("address") or "")[:60] or "Job site"
        ))
        paddr = escape(str(p.get("address") or ""))
        pnotes = escape(str(p.get("notes") or "")).replace("\n", "<br>")
        psummary = escape(str(p.get("summary") or "")).replace("\n", "<br>")
        pflag = p.get("priority_flag")
        flagged = bool(pflag)
        notes_block = (
            f'<p style="margin:6px 0;color:#374151;line-height:1.55">{pnotes}</p>' if pnotes else ""
        )
        summary_block = (
            f'<div style="margin-top:6px;padding:10px 12px;background:#FFF7ED;border-left:3px solid #F97316;'
            f'border-radius:6px;color:#7C2D12;line-height:1.5;font-size:13px"><b>Job overview:</b> {psummary}</div>'
            if psummary else ""
        )
        respond_button = (
            f'<button class="respond-btn" data-pid="{pid}" data-plabel="{plabel}"'
            f' style="margin-top:10px;padding:10px 16px;background:#F97316;color:#fff;border:none;'
            f'border-radius:8px;font-weight:700;cursor:pointer">Respond to this job →</button>'
            if flagged else ""
        )
        addr_html = (
            f'<div style="color:#6B7280;font-size:12px;margin-top:2px">{paddr}</div>'
            if paddr else ""
        )
        projects_html += (
            f'<div class="card" style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;'
            f'padding:16px;margin-bottom:12px">'
            f'<div style="font-weight:700;color:#111827;font-size:15px">{plabel}{flag_badge(pflag)}</div>'
            f'{addr_html}'
            f'{summary_block}'
            f'{notes_block}'
            f'{respond_button}'
            f'</div>'
        )

    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {report_date}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
          background:#F9FAFB; margin:0; padding:0; color:#111827; }}
  .wrap {{ max-width: 720px; margin: 0 auto; padding: 24px 16px 60px; }}
  h1 {{ font-size: 22px; margin:0 0 4px 0; }}
  .meta {{ color:#6B7280; font-size: 13px; margin-bottom:16px }}
  .summary {{ background:#F3F4F6; border-radius:12px; padding:16px; line-height:1.6; color:#111827; }}
  .section-title {{ font-size:13px; letter-spacing:0.5px; text-transform:uppercase; color:#6B7280;
                   margin:24px 0 10px; font-weight:700; }}
  .modal-backdrop {{ position:fixed; inset:0; background:rgba(0,0,0,0.45); display:none;
                    align-items:center; justify-content:center; padding:16px; z-index:50 }}
  .modal {{ background:#fff; border-radius:16px; width:100%; max-width:460px; padding:20px;
           box-shadow:0 20px 40px rgba(0,0,0,0.2) }}
  .modal h3 {{ margin:0 0 2px 0; font-size:17px }}
  .modal label {{ display:block; font-size:12px; font-weight:700; color:#6B7280; margin-top:12px }}
  .modal input, .modal textarea {{ width:100%; padding:10px 12px; border:1px solid #E5E7EB;
    border-radius:8px; font-size:14px; margin-top:4px; box-sizing:border-box; font-family:inherit }}
  .modal textarea {{ min-height:110px; resize:vertical }}
  .modal .row {{ display:flex; gap:10px; margin-top:16px; justify-content:flex-end }}
  .btn {{ padding:10px 16px; border-radius:8px; font-weight:700; border:none; cursor:pointer; font-size:14px }}
  .btn.secondary {{ background:#F3F4F6; color:#111827 }}
  .btn.primary {{ background:#F97316; color:#fff }}
  .status {{ margin-top:12px; font-size:13px }}
  .status.ok {{ color:#059669 }}
  .status.err {{ color:#B91C1C }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <div class="meta">{author} · {role} · {report_date}</div>
  <div class="summary">{ai_summary}</div>
  {f'<div class="section-title">Jobs on this report</div>{projects_html}' if projects else ""}
  <div class="section-title">General reply</div>
  <button class="respond-btn btn primary" data-pid="" data-plabel="General reply"
    style="padding:12px 18px">Send a general reply</button>
</div>

<div class="modal-backdrop" id="mb">
  <div class="modal">
    <h3 id="mTitle">Reply</h3>
    <div style="color:#6B7280;font-size:12px" id="mSub"></div>
    <label>Your name</label>
    <input id="mName" placeholder="e.g. Jane Smith" />
    <label>Your email</label>
    <input id="mEmail" type="email" placeholder="you@example.com" />
    <label>Message</label>
    <textarea id="mMsg" placeholder="Your reply, questions, approvals…"></textarea>
    <div class="status" id="mStatus"></div>
    <div class="row">
      <button class="btn secondary" id="mCancel">Cancel</button>
      <button class="btn primary" id="mSend">Send reply</button>
    </div>
  </div>
</div>

<script>
(function() {{
  var token = {json.dumps(token)};
  var mb = document.getElementById('mb');
  var currentPid = null;
  function open(pid, plabel) {{
    currentPid = pid || null;
    document.getElementById('mTitle').innerText = pid ? 'Reply to flagged job' : 'Send a general reply';
    document.getElementById('mSub').innerText = plabel || '';
    document.getElementById('mStatus').innerText = '';
    document.getElementById('mStatus').className = 'status';
    document.getElementById('mMsg').value = '';
    mb.style.display = 'flex';
  }}
  function close() {{ mb.style.display = 'none'; }}
  document.querySelectorAll('.respond-btn').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      open(btn.getAttribute('data-pid'), btn.getAttribute('data-plabel'));
    }});
  }});
  document.getElementById('mCancel').addEventListener('click', close);
  mb.addEventListener('click', function(e) {{ if (e.target === mb) close(); }});
  document.getElementById('mSend').addEventListener('click', async function() {{
    var name = document.getElementById('mName').value.trim();
    var email = document.getElementById('mEmail').value.trim();
    var msg = document.getElementById('mMsg').value.trim();
    var status = document.getElementById('mStatus');
    if (!msg) {{ status.className = 'status err'; status.innerText = 'Message is required.'; return; }}
    status.className = 'status'; status.innerText = 'Sending…';
    try {{
      var r = await fetch('/api/public/reports/' + encodeURIComponent(token) + '/respond', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          project_id: currentPid || null,
          reporter_name: name || null,
          reporter_email: email || null,
          message: msg,
        }})
      }});
      if (!r.ok) {{
        var t = await r.text();
        throw new Error(t || ('HTTP ' + r.status));
      }}
      status.className = 'status ok';
      status.innerText = '✓ Reply delivered to the field team.';
      setTimeout(close, 1400);
    }} catch (e) {{
      status.className = 'status err';
      status.innerText = 'Could not send: ' + (e.message || e);
    }}
  }});
}})();
</script>
</body></html>
"""
    return body


# ---------- Digest Scheduler ----------
class DigestScheduleCreate(BaseModel):
    enabled: bool
    hour: int = Field(ge=0, le=23, default=8)
    minute: int = Field(ge=0, le=59, default=0)
    day_of_week: str = "mon"  # apscheduler cron day: mon..sun
    recipient_emails: List[EmailStr]


@api.get("/digest/schedule")
async def get_schedule(request: Request, _: dict = Depends(admin_only)):
    doc = await request.app.db.digest_schedule.find_one({"id": "singleton"}, {"_id": 0})
    return doc or {"enabled": False, "hour": 8, "minute": 0, "day_of_week": "mon", "recipient_emails": []}


@api.put("/digest/schedule")
async def set_schedule(data: DigestScheduleCreate, request: Request, admin: dict = Depends(admin_only)):
    doc = {
        "id": "singleton",
        "enabled": data.enabled,
        "hour": data.hour,
        "minute": data.minute,
        "day_of_week": data.day_of_week,
        "recipient_emails": [str(e) for e in data.recipient_emails],
        "updated_by": admin["id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await request.app.db.digest_schedule.update_one({"id": "singleton"}, {"$set": doc}, upsert=True)
    await _reschedule_digest(request.app)
    return {"ok": True, "schedule": doc}


async def _run_scheduled_digest(app: FastAPI):
    schedule = await app.db.digest_schedule.find_one({"id": "singleton"}, {"_id": 0})
    if not schedule or not schedule.get("enabled") or not schedule.get("recipient_emails"):
        return
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    reports = await app.db.reports.find(
        {"created_at": {"$gte": week_ago}, "deleted_at": None}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    if not reports:
        return
    total_visits = sum(len(r.get("visits", [])) for r in reports)
    total_breaks = sum(len(r.get("breaks", [])) for r in reports)
    total_sms = sum(len(r.get("sms_logs", [])) for r in reports)
    lines = [f"Weekly Digest (auto): {len(reports)} reports, {total_visits} visits, {total_breaks} breaks, {total_sms} comms.", ""]
    for r in reports[:20]:
        lines.append(f"[{r['report_date']}] {r['author_name']} — {r.get('project_name') or ''}")
        lines.append(r["ai_summary"][:500])
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"digest-auto-{uuid4()}",
            system_message="Weekly executive digest for a painting operations owner. Concise, headed sections, 300-500 words.",
        ).with_model("openai", "gpt-5.4")
        digest_text = await chat.send_message(UserMessage(text="\n".join(lines)))
        digest_text = digest_text if isinstance(digest_text, str) else str(digest_text)
    except Exception as e:
        logger.error(f"Auto digest AI failed: {e}")
        digest_text = "\n".join(lines)
    subject = f"Weekly Ops Digest — {datetime.now(timezone.utc).date().isoformat()}"
    summary_html = escape(digest_text).replace("\n", "<br>")
    html = (
        f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif">'
        f'<tr><td style="padding:24px">'
        f'<h2 style="margin:0 0 12px 0;color:#111827">Weekly Ops Digest (Auto)</h2>'
        f'<div style="color:#111827;line-height:1.6">{summary_html}</div>'
        f'<p style="font-size:12px;color:#6B7280;margin-top:16px">Sent by {escape(EMAIL_FROM_NAME)}.</p>'
        f'</td></tr></table>'
    )
    sent = []
    for email in schedule["recipient_emails"]:
        eid = await send_email(to=email, subject=subject, html=html)
        if eid:
            sent.append(email)
    await app.db.digests.insert_one({
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "text": digest_text,
        "email_sent_to": sent,
        "report_ids": [r["id"] for r in reports],
        "auto": True,
    })


async def _reschedule_digest(app: FastAPI):
    schedule = await app.db.digest_schedule.find_one({"id": "singleton"}, {"_id": 0})
    scheduler: AsyncIOScheduler = app.scheduler
    try:
        scheduler.remove_job("weekly-digest")
    except Exception:
        pass
    if schedule and schedule.get("enabled"):
        trigger = CronTrigger(
            day_of_week=schedule.get("day_of_week", "mon"),
            hour=schedule.get("hour", 8),
            minute=schedule.get("minute", 0),
        )
        scheduler.add_job(_run_scheduled_digest, trigger, args=[app], id="weekly-digest", replace_existing=True)


# ---------- Daily Mail Digest ----------
# Singleton schedule — each morning, every user who owns reports with unread, non-archived
# inbound replies from the last 24h gets a single email listing those replies grouped by job.
class MailDigestScheduleCreate(BaseModel):
    enabled: bool
    hour: int = Field(ge=0, le=23, default=7)
    minute: int = Field(ge=0, le=59, default=0)


@api.get("/digest/mail-schedule")
async def get_mail_schedule(request: Request, _: dict = Depends(admin_only)):
    doc = await request.app.db.mail_digest_schedule.find_one({"id": "singleton"}, {"_id": 0})
    return doc or {"enabled": False, "hour": 7, "minute": 0}


@api.put("/digest/mail-schedule")
async def set_mail_schedule(
    data: MailDigestScheduleCreate, request: Request, admin: dict = Depends(admin_only),
):
    doc = {
        "id": "singleton",
        "enabled": data.enabled,
        "hour": data.hour,
        "minute": data.minute,
        "updated_by": admin["id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await request.app.db.mail_digest_schedule.update_one(
        {"id": "singleton"}, {"$set": doc}, upsert=True,
    )
    await _reschedule_mail_digest(request.app)
    return {"ok": True, "schedule": doc}


@api.post("/digest/mail-send-now")
async def send_mail_digest_now(request: Request, _: dict = Depends(admin_only)):
    """Trigger the daily mail digest run immediately (admin test action)."""
    result = await _run_mail_digest(request.app)
    return {"ok": True, **result}


async def _run_mail_digest(app: FastAPI) -> dict:
    """For each report-owning user with unread inbound replies in the last 24h, send a single
    digest email grouped by report → job. Returns a small summary dict."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    unread = await app.db.report_responses.find(
        {
            "direction": {"$ne": "outbound"},
            "archived": {"$ne": True},
            "read_at": None,
            "created_at": {"$gte": since},
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(2000)
    if not unread:
        return {"emails_sent": 0, "owners": 0, "replies": 0}

    # Group by report_user_id → report_id → list of replies
    by_user: dict = {}
    for r in unread:
        by_user.setdefault(r["report_user_id"], {}).setdefault(r["report_id"], []).append(r)

    sent_count = 0
    owner_count = 0
    for user_id, by_report in by_user.items():
        user = await app.db.users.find_one({"id": user_id}, {"_id": 0})
        if not user or not user.get("email"):
            continue
        owner_count += 1

        # Build email body
        total_replies = sum(len(v) for v in by_report.values())
        rows_html = []
        for report_id, reps in by_report.items():
            report = await app.db.reports.find_one({"id": report_id}, {"_id": 0}) or {}
            report_label = (
                report.get("project_name")
                or report.get("project_code")
                or report.get("report_date")
                or "Daily report"
            )
            # Group by project_id within report
            by_project: dict = {}
            for rp in reps:
                by_project.setdefault(rp.get("project_id") or "__general__", []).append(rp)
            section_rows = []
            for pid, prs in by_project.items():
                plabel = prs[0].get("project_label") or "General reply"
                flag = prs[0].get("project_flag")
                flag_html = (
                    f'<span style="display:inline-block;padding:2px 8px;background:#FEE2E2;color:#B91C1C;'
                    f'border-radius:999px;font-size:11px;font-weight:700;margin-left:6px">{escape(flag)}</span>'
                    if flag else ""
                )
                reply_items = []
                for rp in prs:
                    who = escape(rp.get("reporter_name") or rp.get("reporter_email") or "Anonymous")
                    when = (rp.get("created_at") or "")[11:16]
                    body = escape(rp.get("message") or "")
                    reply_items.append(
                        f'<div style="padding:10px 12px;background:#F3F4F6;border-radius:8px;margin-bottom:6px;line-height:1.55">'
                        f'<div style="font-weight:700;color:#111827;font-size:13px">{who} <span style="color:#6B7280;font-weight:400">· {when}</span></div>'
                        f'<div style="color:#374151;font-size:13px;margin-top:4px">{body}</div>'
                        f'</div>'
                    )
                section_rows.append(
                    f'<div style="margin:14px 0 8px 0">'
                    f'<div style="font-weight:700;color:#111827;font-size:14px">{escape(plabel)}{flag_html}</div>'
                    f'</div>'
                    + "".join(reply_items)
                )
            rows_html.append(
                f'<div style="margin:20px 0 0 0;padding-top:14px;border-top:1px solid #E5E7EB">'
                f'<div style="color:#6B7280;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;font-weight:700">Report</div>'
                f'<div style="color:#111827;font-weight:800;font-size:15px;margin-top:2px">{escape(str(report_label))}</div>'
                + "".join(section_rows)
                + "</div>"
            )
        subject = f"Your morning digest — {total_replies} unread repl{'ies' if total_replies != 1 else 'y'}"
        html_body = (
            f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif;background:#F9FAFB">'
            f'<tr><td style="padding:24px">'
            f'<h2 style="margin:0 0 6px 0;color:#111827">Good morning</h2>'
            f'<p style="color:#374151;margin:0 0 4px 0">You have <b>{total_replies}</b> unread repl{"ies" if total_replies != 1 else "y"} across {len(by_report)} report{"s" if len(by_report) != 1 else ""} from the last 24 hours.</p>'
            + "".join(rows_html)
            + f'<p style="font-size:12px;color:#6B7280;margin-top:20px">Open Summar-Eeze → Mail to reply or archive.</p>'
            f'</td></tr></table>'
        )
        try:
            eid = await send_email(to=user["email"], subject=subject, html=html_body)
            if eid:
                sent_count += 1
        except Exception as e:
            logger.warning(f"Mail digest to {user.get('email')} failed: {e}")

    await app.db.mail_digest_runs.insert_one({
        "id": str(uuid4()),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "emails_sent": sent_count,
        "owners": owner_count,
        "replies": sum(len(v) for v in [reps for by_report in by_user.values() for reps in by_report.values()]),
    })

    return {
        "emails_sent": sent_count,
        "owners": owner_count,
        "replies": sum(len(v) for v in [reps for by_report in by_user.values() for reps in by_report.values()]),
    }


async def _reschedule_mail_digest(app: FastAPI):
    schedule = await app.db.mail_digest_schedule.find_one({"id": "singleton"}, {"_id": 0})
    scheduler: AsyncIOScheduler = app.scheduler
    try:
        scheduler.remove_job("mail-digest-daily")
    except Exception:
        pass
    if schedule and schedule.get("enabled"):
        trigger = CronTrigger(hour=schedule.get("hour", 7), minute=schedule.get("minute", 0))
        scheduler.add_job(
            _run_mail_digest, trigger, args=[app], id="mail-digest-daily", replace_existing=True,
        )


# Include the router (with the new routes) — must be after all routes are defined
app.include_router(api)
