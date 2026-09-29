"""PaintOps Daily backend - FastAPI server."""
import os
import re
import ipaddress
import logging
import io
import csv
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
from fastapi.responses import StreamingResponse, Response
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


class LocationVisit(LocationVisitCreate):
    id: str
    user_id: str
    timestamp: str
    ended_at: Optional[str] = None
    photos: List[str] = []


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
    signature: Optional[dict] = None
    archived: bool = False
    archived_at: Optional[str] = None
    deleted_at: Optional[str] = None
    public_token: Optional[str] = None
    priority_level: Optional[str] = None
    priority_flags: List[dict] = []


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
@api.get("/weather")
async def get_weather(lat: float, lon: float):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
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
        data = resp.json()
        current = data.get("current", {})
        code = current.get("weather_code", 0)
        conditions_map = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
            55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 80: "Rain showers",
            81: "Moderate rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
            96: "Thunderstorm w/ slight hail", 99: "Thunderstorm w/ heavy hail",
        }
        return {
            "latitude": lat,
            "longitude": lon,
            "temperature_f": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_mph": current.get("wind_speed_10m"),
            "precipitation": current.get("precipitation"),
            "weather_code": code,
            "conditions": conditions_map.get(code, "Unknown"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        raise HTTPException(502, "Failed to fetch weather")


# ---------- Location Visits ----------
@api.post("/visits", response_model=LocationVisit)
async def create_visit(data: LocationVisitCreate, request: Request, user: dict = Depends(current_user)):
    doc = data.model_dump()
    doc.update({
        "id": str(uuid4()),
        "user_id": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
    })
    await request.app.db.visits.insert_one(doc.copy())
    doc.pop("_id", None)
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
        "- Wrap CUSTOMER names, ADDRESSES, and PROJECT CODES in double-asterisk bold, e.g. **John Doe**, **123 Main St**, **P-1042**.\n"
        "- If a priority flag reason was provided, echo it verbatim in DELAY / CONSTRAINTS on its own bullet "
        "prefixed with '[URGENT: <flag type>]' so it can be highlighted red in the app.\n"
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
        prompt_lines.append(f"Project: {context.get('project_name') or ''} {context.get('project_code') or ''}")
    prompt_lines.append(f"Date: {context.get('report_date')}")
    if context.get("weather"):
        w = context["weather"]
        prompt_lines.append(
            f"Weather at site: {w.get('conditions')}, {w.get('temperature_f')}°F, wind {w.get('wind_mph')} mph, "
            f"precipitation {w.get('precipitation')} in."
        )
    if context.get("highlights"):
        prompt_lines.append(f"Manager highlights: {context['highlights']}")
    if context.get("delays"):
        prompt_lines.append(f"Delays: {context['delays']}")
    if context.get("change_orders"):
        prompt_lines.append(f"Change orders: {context['change_orders']}")
    if context.get("material_notes"):
        prompt_lines.append(f"Material notes: {context['material_notes']}")
    if context.get("visits"):
        prompt_lines.append("Site visits today:")
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
    }
    await request.app.db.reports.insert_one(report.copy())
    report.pop("_id", None)

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
async def list_reports(request: Request, user: dict = Depends(current_user), include_archived: bool = False):
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] in FULL_ROLES or user.get("is_admin"):
        query: dict = {}
    else:
        query = {"user_id": user["id"]}
    query["deleted_at"] = None
    if not include_archived:
        query["$or"] = [{"archived": False}, {"archived": {"$exists": False}}]
    docs = await request.app.db.reports.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [DailyReport(**d) for d in docs]


@api.get("/reports/{report_id}", response_model=DailyReport)
async def get_report(report_id: str, request: Request, user: dict = Depends(current_user)):
    doc = await request.app.db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] not in FULL_ROLES and not user.get("is_admin") and doc["user_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
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


@api.get("/public/reports/{token}")
async def public_report(token: str, request: Request):
    doc = await request.app.db.reports.find_one({"public_token": token, "deleted_at": None}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    # Return a limited public view
    return {
        "report_date": doc["report_date"],
        "author_name": doc["author_name"],
        "author_role": doc["author_role"],
        "project_name": doc.get("project_name"),
        "project_code": doc.get("project_code"),
        "ai_summary": doc["ai_summary"],
        "signature": doc.get("signature"),
        "created_at": doc["created_at"],
    }


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


# Include the router (with the new routes) — must be after all routes are defined
app.include_router(api)
