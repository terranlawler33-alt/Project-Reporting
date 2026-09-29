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
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from emergentintegrations.llm.chat import LlmChat, UserMessage

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
    yield
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
        "You are an experienced painting operations manager writing a professional daily field report. "
        "Write a concise, professional summary (250-400 words) covering: tasks completed, communications, "
        "site visits, weather impact, delays, and next steps. Use short paragraphs and clear headers. "
        "Focus on facts a business owner needs to run the operation."
    )
    prompt_lines = [f"Author: {context.get('author_name')} ({context.get('author_role')})"]
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
    prompt = "\n".join(prompt_lines) + "\n\nWrite the daily summary now."

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
            f"[AI summary unavailable] Manual notes:\n"
            f"Highlights: {context.get('highlights', 'None')}\n"
            f"Delays: {context.get('delays', 'None')}\n"
            f"Change orders: {context.get('change_orders', 'None')}\n"
            f"Material notes: {context.get('material_notes', 'None')}"
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


def _report_email_html(report: dict) -> str:
    summary_html = escape(report["ai_summary"]).replace("\n", "<br>")
    return (
        f'<table role="presentation" width="100%" style="font-family:Arial,sans-serif">'
        f'<tr><td style="padding:24px">'
        f'<h2 style="margin:0 0 12px 0;color:#111827">Daily Report — {escape(report["report_date"])}</h2>'
        f'<p style="margin:0 0 8px 0;color:#374151">'
        f'From: <strong>{escape(report["author_name"])}</strong> ({escape(report["author_role"])})'
        f'{" • Project: " + escape(report.get("project_name") or report.get("project_code") or "") if report.get("project_name") or report.get("project_code") else ""}'
        f'</p>'
        f'<hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0">'
        f'<div style="color:#111827;line-height:1.6">{summary_html}</div>'
        f'<hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0">'
        f'<p style="font-size:12px;color:#6B7280;margin:0">Sent by {escape(EMAIL_FROM_NAME)}. '
        f'We never ask for your password or card details by email.</p>'
        f'</td></tr></table>'
    )


@api.get("/reports", response_model=List[DailyReport])
async def list_reports(request: Request, user: dict = Depends(current_user)):
    FULL_ROLES = {Role.OWNER.value, Role.OPERATIONS.value, Role.PROJECT_MANAGER.value}
    if user["role"] in FULL_ROLES or user.get("is_admin"):
        query = {}
    else:
        query = {"user_id": user["id"]}
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


app.include_router(api)
