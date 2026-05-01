import csv
import json
import os
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import jwt
from dotenv import load_dotenv
import asyncpg
import requests
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from passlib.context import CryptContext

load_dotenv()

# Standard logger for any backend errors or debugging information.
logger = logging.getLogger(__name__)

# FastAPI application instance that defines our HTTP API surface.
app = FastAPI(title="AlloyFinance API", version="0.1.0")

# Allowed origins for browser-based requests. We read these from env vars
# so the same backend can be deployed locally and in production safely.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware

class COOPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cross-Origin-Opener-Policy"] = "unsafe-none"
        return response

app.add_middleware(COOPMiddleware)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET is not set")

DATABASE_SSL_MODE = os.getenv("DATABASE_SSL_MODE", "disable").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)

# JWT configuration for user session tokens.
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEV_USER_EMAIL = "foo@bar.com"
DEV_USER_PASSWORD = "password"

# Path to the shared transaction seed dataset used for new users.
# We only need this file when a user logs in for the first time.
SEED_TRANSACTIONS_FILE = Path(__file__).resolve().parents[1] / "synthetic-data" / "output_data" / "transactions.csv"
_cached_seed_transactions: list[dict] = []

# Connection pool for the PostgreSQL/AlloyDB database.
pool: asyncpg.Pool = None

def _load_seed_transactions() -> list[dict]:
    """Read the seed CSV once and cache it for use by subsequent users.

    This function converts the CSV rows into Python dicts with typed
    values so they can be inserted into the database directly.
    """
    global _cached_seed_transactions
    if _cached_seed_transactions:
        return _cached_seed_transactions

    if not SEED_TRANSACTIONS_FILE.exists():
        return []

    with open(SEED_TRANSACTIONS_FILE, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            timestamp = row["timestamp"]
            if timestamp.endswith("Z"):
                timestamp = timestamp[:-1] + "+00:00"
            _cached_seed_transactions.append({
                "timestamp": datetime.fromisoformat(timestamp),
                "amount": float(row["amount"]),
                "merchant_name": row["merchant_name"],
                "merchant_category": row["merchant_category"],
                "spending_category": row["spending_category"],
                "transaction_type": row["transaction_type"],
                "payment_method": row["payment_method"],
                "city": row["city"],
                "country": row["country"],
                "currency": row["currency"],
                "description": None,
            })

    return _cached_seed_transactions

async def _seed_transactions_for_user(conn: asyncpg.Connection, user_id: int) -> None:
    """Assign the shared seed transactions to a user if they have none.

    This avoids duplicating seeded rows for returning users while ensuring
    that every authenticated user has a default dataset available.
    """
    existing_count = await conn.fetchval(
        "SELECT COUNT(*) FROM transactions WHERE user_id = $1",
        user_id,
    )
    if existing_count and existing_count > 0:
        return

    seed_rows = _load_seed_transactions()
    if not seed_rows:
        return

    await conn.executemany(
        """INSERT INTO transactions (
               transaction_id, user_id, timestamp, amount, merchant_name,
               merchant_category, spending_category, transaction_type,
               payment_method, city, country, currency, description
           ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)""",
        [
            (
                uuid.uuid4(),
                user_id,
                row["timestamp"],
                row["amount"],
                row["merchant_name"],
                row["merchant_category"],
                row["spending_category"],
                row["transaction_type"],
                row["payment_method"],
                row["city"],
                row["country"],
                row["currency"],
                row["description"],
            )
            for row in seed_rows
        ],
    )
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

@app.on_event("startup")
async def startup():
    """Initialize the database connection pool and ensure required schema exists.

    This runs once when the FastAPI app starts, so the app can safely assume
    that the tables exist for users, items, transactions, and budget preferences.
    """
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        ssl="require" if DATABASE_SSL_MODE == "require" else False,
        min_size=5,
        max_size=20,
        command_timeout=60,
        max_inactive_connection_lifetime=300,
    )
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                google_id TEXT UNIQUE,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name TEXT,
                picture TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)
        await conn.execute("""
            ALTER TABLE users
            ALTER COLUMN google_id DROP NOT NULL
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id UUID PRIMARY KEY,
                user_id INTEGER NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                amount NUMERIC(18, 2) NOT NULL,
                merchant_name TEXT NOT NULL,
                merchant_category TEXT NOT NULL,
                spending_category TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL,
                currency TEXT NOT NULL,
                description TEXT
            )
        """)
        await conn.execute("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS description TEXT
        """)
        await conn.execute("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)
        await conn.execute("""
            UPDATE transactions
            SET user_id = (SELECT id FROM users WHERE email = 'nikhil.m@berkeley.edu' LIMIT 1)
            WHERE user_id IS NULL
        """)
        await conn.execute(
            """INSERT INTO users (email, password_hash, name, picture)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (email) DO UPDATE SET
                 password_hash = EXCLUDED.password_hash,
                 name = EXCLUDED.name
            """,
            DEV_USER_EMAIL,
            hash_password(DEV_USER_PASSWORD),
            "Dev User",
            None,
        )
        # Budget preferences: one row per category, amount is the user's spending limit
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS "BudgetPrefs" (
                category TEXT PRIMARY KEY,
                amount   NUMERIC(18, 2) NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monthly_reports (
                user_id INTEGER NOT NULL,
                year_month TEXT NOT NULL,
                summary TEXT NOT NULL,
                highlights_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                suggestions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                totals_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                model_version TEXT,
                PRIMARY KEY (user_id, year_month)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monthly_report_history (
                report_id UUID PRIMARY KEY,
                user_id INTEGER NOT NULL,
                year_month TEXT NOT NULL,
                summary TEXT NOT NULL,
                highlights_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                suggestions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                totals_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                model_version TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id UUID PRIMARY KEY,
                user_id INTEGER NOT NULL,
                workflow_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                latency_ms INTEGER,
                error TEXT
            )
        """)
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS embedding vector(768)
        """)
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS embedding vector(768)
        """)

@app.on_event("shutdown")
async def shutdown():
    """Close the database pool cleanly when the application shuts down."""
    await pool.close()

# --- Auth ---
# Authentication is based on Google sign-in and JWT session tokens.

class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str

def create_jwt(user_id: str, email: str) -> str:
    """Build a signed JWT for the authenticated user.

    The token contains the user id and email and expires after a short period.
    This token is returned to the frontend and used for all subsequent API calls.
    """
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(authorization: str = Header(...)) -> dict:
    """Extract and verify the bearer token from the Authorization header.

    If the token is valid, return a minimal user identity dict for route dependencies.
    If invalid, raise a 401 so protected endpoints reject the request.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be in format: Bearer <token>",
        )
    token = authorization[len("Bearer "):]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"user_id": payload["sub"], "email": payload["email"]}

@app.post("/auth/signup")
async def signup(body: SignupRequest):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Valid email is required")
    validate_password(body.password)
    name = body.name.strip() if body.name else None
    password_hash = hash_password(body.password)

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, name, picture)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id, email, name, picture""",
                email, password_hash, name, None,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="User already exists")
        except Exception as exc:
            logger.exception("Signup failed")
            raise HTTPException(status_code=500, detail="Signup failed") from exc

        await _seed_transactions_for_user(conn, int(row["id"]))

    user_id = str(row["id"])
    token = create_jwt(user_id, email)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
        },
    }


@app.post("/auth/login")
async def login(body: LoginRequest):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Valid email is required")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, name, picture, password_hash
               FROM users
               WHERE email = $1""",
            email,
        )
        if not row or not row["password_hash"]:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not verify_password(body.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id = str(row["id"])
    token = create_jwt(user_id, row["email"])
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
        },
    }

@app.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return the current authenticated user's profile.

    Also trigger transaction seeding for any existing users who have not yet
    received the shared dataset. This makes first-login behavior idempotent.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, picture FROM users WHERE id = $1",
            int(user["user_id"]),
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        await _seed_transactions_for_user(conn, int(row["id"]))

        return {
            "id": str(row["id"]),
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
        }

# --- Spending Category Enum ---
# Define the allowed spending categories that can be used in transactions
# and budget preference requests.
class SpendingCategory(str, Enum):
    """Valid spending categories — shared by transactions and budget preferences."""
    groceries      = "groceries"
    dining         = "dining"
    transportation = "transportation"
    rent           = "rent"
    utilities      = "utilities"
    entertainment  = "entertainment"
    travel         = "travel"
    subscriptions  = "subscriptions"
    healthcare     = "healthcare"
    shopping       = "shopping"
    income         = "income"


# --- Item Models ---
# Request payload definitions for the generic items CRUD endpoints.

class ItemCreate(BaseModel):
    name: str
    value: Optional[str] = None

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None


# --- Budget Models ---
# Request payload definitions for budget preference operations.

class BudgetCreate(BaseModel):
    """Request body for creating or updating a budget limit."""
    category: SpendingCategory  # validated against the enum; FastAPI returns 422 on invalid value
    amount: float               # spending limit in USD; must be > 0


# --- Transaction Models ---

class TransactionCreate(BaseModel):
    amount: float
    merchant_name: str
    merchant_category: str
    spending_category: str
    transaction_type: str = Field(description="'credit' or 'debit'")
    payment_method: str
    city: str
    country: str = "US"
    currency: str = "USD"
    description: Optional[str] = None


class MonthlyReportGenerateRequest(BaseModel):
    year_month: Optional[str] = None
    force: bool = False


def _serialize_monthly_report_row(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    d["report_id"] = str(d["report_id"])
    d["generated_at"] = d["generated_at"].isoformat()
    return d


def _month_range_from_year_month(year_month: Optional[str]) -> tuple[str, datetime, datetime]:
    if year_month:
        if not re.fullmatch(r"\d{4}-\d{2}", year_month):
            raise HTTPException(status_code=422, detail="year_month must be in YYYY-MM format")
        year, month = map(int, year_month.split("-"))
        if month < 1 or month > 12:
            raise HTTPException(status_code=422, detail="Invalid month in year_month")
        start = datetime(year, month, 1, tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.strftime("%Y-%m"), start, end


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        raise ValueError("Model response did not contain a JSON object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON was not an object")
    return parsed


def _coerce_report_shape(payload: dict[str, Any], fallback_report: dict[str, Any]) -> dict[str, Any]:
    summary = str(payload.get("summary") or fallback_report["summary"]).strip()
    highlights = payload.get("highlights") or []
    suggestions = payload.get("suggestions") or []

    if not isinstance(highlights, list):
        highlights = [str(highlights)]
    highlights = [str(x).strip() for x in highlights if str(x).strip()][:6]

    normalized_suggestions: list[dict[str, Any]] = []
    if isinstance(suggestions, list):
        for s in suggestions[:6]:
            if isinstance(s, dict):
                normalized_suggestions.append(
                    {
                        "title": str(s.get("title", "Suggestion")).strip() or "Suggestion",
                        "rationale": str(s.get("rationale", "")).strip(),
                        "estimated_savings_usd": float(s.get("estimated_savings_usd", 0) or 0),
                    }
                )
            else:
                normalized_suggestions.append(
                    {"title": str(s).strip() or "Suggestion", "rationale": "", "estimated_savings_usd": 0}
                )

    if not highlights:
        highlights = fallback_report["highlights"]
    if not normalized_suggestions:
        normalized_suggestions = fallback_report["suggestions"]

    return {
        "summary": summary,
        "highlights": highlights,
        "suggestions": normalized_suggestions,
    }


async def _build_monthly_report_payload(user_id: int, year_month: Optional[str]) -> dict[str, Any]:
    ym, month_start, month_end = _month_range_from_year_month(year_month)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    async with pool.acquire() as conn:
        totals_row = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) AS total_spent,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(amount), 0) AS net_cashflow,
                COUNT(*) AS txn_count
            FROM transactions
            WHERE user_id = $1 AND timestamp >= $2 AND timestamp < $3
            """,
            user_id, month_start, month_end,
        )
        category_rows = await conn.fetch(
            """
            WITH current_month AS (
                SELECT LOWER(spending_category) AS category, SUM(ABS(amount)) AS spend
                FROM transactions
                WHERE user_id = $1
                  AND amount < 0
                  AND timestamp >= $2
                  AND timestamp < $3
                GROUP BY LOWER(spending_category)
            ),
            previous_month AS (
                SELECT LOWER(spending_category) AS category, SUM(ABS(amount)) AS spend
                FROM transactions
                WHERE user_id = $1
                  AND amount < 0
                  AND timestamp >= $4
                  AND timestamp < $2
                GROUP BY LOWER(spending_category)
            )
            SELECT
                c.category,
                c.spend AS current_spend,
                COALESCE(p.spend, 0) AS previous_spend
            FROM current_month c
            LEFT JOIN previous_month p ON p.category = c.category
            ORDER BY c.spend DESC
            LIMIT 6
            """,
            user_id, month_start, month_end, prev_start,
        )
        merchant_rows = await conn.fetch(
            """
            SELECT merchant_name, COUNT(*) AS txn_count, SUM(ABS(amount)) AS total_spend
            FROM transactions
            WHERE user_id = $1
              AND amount < 0
              AND timestamp >= $2
              AND timestamp < $3
            GROUP BY merchant_name
            ORDER BY total_spend DESC
            LIMIT 5
            """,
            user_id, month_start, month_end,
        )
        budget_rows = await conn.fetch(
            """
            SELECT
                bp.category,
                bp.amount AS budget_limit,
                COALESCE(SUM(ABS(t.amount)), 0) AS total_spent
            FROM "BudgetPrefs" bp
            LEFT JOIN transactions t
              ON t.user_id = $1
             AND LOWER(t.spending_category) = LOWER(bp.category)
             AND t.amount < 0
             AND t.timestamp >= $2
             AND t.timestamp < $3
            GROUP BY bp.category, bp.amount
            ORDER BY bp.category
            """,
            user_id, month_start, month_end,
        )

        example_rows = await conn.fetch(
            """
            SELECT transaction_id, timestamp, merchant_name, spending_category, amount, description
            FROM transactions
            WHERE user_id = $1
              AND timestamp >= $2
              AND timestamp < $3
              AND embedding IS NOT NULL
            ORDER BY embedding <=> google_ml.embedding('text-embedding-005', $4)::vector
            LIMIT 8
            """,
            user_id, month_start, month_end, "monthly spending patterns and recurring expenses",
        )

    totals = {
        "total_spent": float(totals_row["total_spent"] or 0),
        "total_income": float(totals_row["total_income"] or 0),
        "net_cashflow": float(totals_row["net_cashflow"] or 0),
        "transaction_count": int(totals_row["txn_count"] or 0),
    }
    categories = []
    for row in category_rows:
        prev = float(row["previous_spend"] or 0)
        curr = float(row["current_spend"] or 0)
        delta = ((curr - prev) / prev) if prev > 0 else None
        categories.append(
            {
                "category": row["category"],
                "current_spend": curr,
                "previous_spend": prev,
                "delta_ratio_vs_previous": delta,
            }
        )

    return {
        "year_month": ym,
        "totals": totals,
        "categories": categories,
        "top_merchants": [
            {
                "merchant_name": r["merchant_name"],
                "txn_count": int(r["txn_count"]),
                "total_spend": float(r["total_spend"] or 0),
            }
            for r in merchant_rows
        ],
        "budget_usage": [
            {
                "category": r["category"],
                "total_spent": float(r["total_spent"] or 0),
                "budget_limit": float(r["budget_limit"] or 0),
            }
            for r in budget_rows
        ],
        "examples": [
            {
                "transaction_id": str(r["transaction_id"]),
                "timestamp": r["timestamp"].isoformat(),
                "merchant_name": r["merchant_name"],
                "spending_category": r["spending_category"],
                "amount": float(r["amount"]),
                "description": r["description"] or "",
            }
            for r in example_rows
        ],
    }


def _fallback_monthly_report(payload: dict[str, Any]) -> dict[str, Any]:
    totals = payload["totals"]
    categories = payload["categories"]
    summary = (
        f"In {payload['year_month']}, you spent ${totals['total_spent']:.2f} across "
        f"{totals['transaction_count']} transactions and brought in ${totals['total_income']:.2f}."
    )
    highlights = []
    for cat in categories[:3]:
        if cat["delta_ratio_vs_previous"] is None:
            highlights.append(f"{cat['category']} spend was ${cat['current_spend']:.2f}.")
        else:
            direction = "up" if cat["delta_ratio_vs_previous"] >= 0 else "down"
            pct = abs(cat["delta_ratio_vs_previous"]) * 100
            highlights.append(f"{cat['category']} spend was {direction} {pct:.1f}% vs last month.")
    suggestions = []
    for b in payload["budget_usage"]:
        overspend = b["total_spent"] - b["budget_limit"]
        if b["budget_limit"] > 0 and overspend > 0:
            suggestions.append(
                {
                    "title": f"Reduce {b['category']} spending",
                    "rationale": f"You are ${overspend:.2f} over your monthly budget in this category.",
                    "estimated_savings_usd": round(overspend, 2),
                }
            )
    return {"summary": summary, "highlights": highlights, "suggestions": suggestions[:5]}


def _generate_report_with_gemini(payload: dict[str, Any]) -> dict[str, Any]:
    fallback = _fallback_monthly_report(payload)
    if not GEMINI_API_KEY:
        return fallback

    prompt = (
        "You are a personal finance assistant. Produce a monthly report as JSON.\n"
        "Return ONLY a JSON object with keys: summary, highlights, suggestions.\n"
        "summary: 2-3 sentences.\n"
        "highlights: array of 3-6 short strings.\n"
        "suggestions: array of objects with keys title, rationale, estimated_savings_usd.\n"
        "Do not invent numbers; use only the provided data.\n\n"
        f"DATA:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    url = GEMINI_API_URL.format(model=GEMINI_MODEL, api_key=GEMINI_API_KEY)
    req: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    try:
        response = requests.post(url, json=req, timeout=60)
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _extract_json_object(text)
        return _coerce_report_shape(parsed, fallback)
    except Exception:
        logger.exception("Falling back to deterministic monthly report generation")
        return fallback


def _serialize_transaction(row: asyncpg.Record) -> dict:
    """Convert a transaction row to JSON-safe primitives for API responses.

    This normalizes UUIDs, timestamps, and numeric values so the frontend can
    render them directly without driver-specific types.
    """
    d = dict(row)
    d["transaction_id"] = str(d["transaction_id"])
    d["timestamp"] = d["timestamp"].isoformat()
    d["amount"] = float(d["amount"])
    d.pop("embedding", None)
    return d


# --- General Routes ---
# Lightweight endpoints for health checks and example responses.

@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}


# --- Item Routes ---
# Simple CRUD endpoints for the generic items table used by the demo frontend.

@app.get("/items")
async def get_items():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM items ORDER BY created_at DESC")
        return [dict(r) for r in rows]

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        return dict(row)

@app.post("/items", status_code=201)
async def create_item(item: ItemCreate):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO items (name, value) VALUES ($1, $2) RETURNING *",
            item.name, item.value
        )
        return dict(row)

@app.put("/items/{item_id}")
async def update_item(item_id: int, item: ItemUpdate):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE items SET
               name = COALESCE($1, name),
               value = COALESCE($2, value)
               WHERE id = $3 RETURNING *""",
            item.name, item.value, item_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        return dict(row)

@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM items WHERE id = $1", item_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Item not found")


# --- Transaction Routes ---
# These endpoints are scoped to the authenticated user and operate only on
# that user's transaction rows.

@app.post("/api/transactions", status_code=201)
async def create_transaction(txn: TransactionCreate, user: dict = Depends(get_current_user)):
    txn_id = uuid.uuid4()
    ts = datetime.now(timezone.utc)
    embed_text = " ".join(filter(None, [
        txn.merchant_name, txn.merchant_category,
        txn.spending_category, txn.description,
    ]))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO transactions (
                transaction_id, user_id, timestamp, amount, merchant_name,
                merchant_category, spending_category, transaction_type,
                payment_method, city, country, currency, description
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *""",
            txn_id, int(user["user_id"]), ts, txn.amount, txn.merchant_name,
            txn.merchant_category, txn.spending_category, txn.transaction_type,
            txn.payment_method, txn.city, txn.country, txn.currency,
            txn.description,
        )
        try:
            await conn.execute(
                """UPDATE transactions
                   SET embedding = google_ml.embedding('text-embedding-005', $1)::vector
                   WHERE transaction_id = $2""",
                embed_text, txn_id,
            )
        except Exception:
            logger.exception("Failed to generate embedding for transaction %s", txn_id)
        return _serialize_transaction(row)


@app.get("/api/transactions/category/{spending_category}")
async def fetch_transactions_by_category(spending_category: str, user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE user_id = $1 AND LOWER(spending_category) = LOWER($2)
               ORDER BY timestamp DESC""",
            int(user["user_id"]), spending_category,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/current-month")
async def fetch_current_month(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE user_id = $1 AND timestamp >= $2
               ORDER BY timestamp DESC""",
            int(user["user_id"]), month_start,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/previous-month")
async def fetch_previous_month(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if current_month_start.month == 1:
        prev_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
    else:
        prev_month_start = current_month_start.replace(month=current_month_start.month - 1)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE user_id = $1 AND timestamp >= $2 AND timestamp < $3
               ORDER BY timestamp DESC""",
            int(user["user_id"]), prev_month_start, current_month_start,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/recent")
async def fetch_n_transactions(limit: int = Query(default=10, ge=1, le=500), user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE user_id = $1
               ORDER BY timestamp DESC
               LIMIT $2""",
            int(user["user_id"]), limit,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/search")
async def search_transactions(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """Semantic similarity search over the authenticated user's transactions."""
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """SELECT *,
                       1 - (embedding <=> google_ml.embedding('text-embedding-005', $1)::vector) AS similarity
                   FROM transactions
                   WHERE user_id = $2
                     AND embedding IS NOT NULL
                   ORDER BY embedding <=> google_ml.embedding('text-embedding-005', $1)::vector
                   LIMIT $3""",
                q.strip(), int(user["user_id"]), limit,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Semantic search failed: {e}")
    results = []
    for r in rows:
        d = _serialize_transaction(r)
        d["similarity"] = float(r["similarity"])
        results.append(d)
    return results
@app.get("/api/transactions/all")
async def fetch_all_transactions(user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE user_id = $1
               ORDER BY timestamp DESC""",
            int(user["user_id"]),
        )
        return [_serialize_transaction(r) for r in rows]


# --- Budget Routes ---
# Budget operations let the user create or update spending limits by category.

@app.post("/api/budgets", status_code=200)
async def create_budget(budget: BudgetCreate):
    """
    Set (or update) a monthly spending limit for a category.

    - category: one of the SpendingCategory enum values
    - amount: spending limit in USD; must be a positive number

    Returns {"status": 0} on success.
    If the same category already has a budget, the amount is overwritten (upsert).
    """
    # Reject non-positive amounts — a budget of $0 or negative makes no sense
    if budget.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be greater than 0")

    try:
        async with pool.acquire() as conn:
            # INSERT or UPDATE: category is the primary key, so duplicate calls
            # for the same category simply update the stored amount instead of erroring
            await conn.execute(
                """INSERT INTO "BudgetPrefs" (category, amount)
                   VALUES ($1, $2)
                   ON CONFLICT (category) DO UPDATE SET amount = EXCLUDED.amount""",
                budget.category.value,
                budget.amount,
            )
        return {"status": 0}
    except Exception as e:
        # Log the full error server-side; return a generic failure code to the caller
        print(f"[ERROR] create_budget: {e}")
        return JSONResponse(status_code=500, content={"status": 1, "error": str(e)})


# --- Monthly Report Routes ---

@app.get("/api/agents/monthly-report")
async def get_monthly_report(
    year_month: Optional[str] = Query(default=None),
    user: dict = Depends(get_current_user),
):
    ym, _, _ = _month_range_from_year_month(year_month)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT report_id, year_month, summary, highlights_json, suggestions_json, totals_json, generated_at, model_version
            FROM monthly_report_history
            WHERE user_id = $1 AND year_month = $2
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            int(user["user_id"]), ym,
        )
    if not row:
        raise HTTPException(status_code=404, detail="No monthly report found for the selected month")
    return _serialize_monthly_report_row(row)


@app.get("/api/agents/monthly-report/history")
async def list_monthly_reports(
    year_month: Optional[str] = Query(default=None),
    user: dict = Depends(get_current_user),
):
    user_id = int(user["user_id"])
    async with pool.acquire() as conn:
        if year_month:
            ym, _, _ = _month_range_from_year_month(year_month)
            rows = await conn.fetch(
                """
                SELECT report_id, year_month, summary, highlights_json, suggestions_json, totals_json, generated_at, model_version
                FROM monthly_report_history
                WHERE user_id = $1 AND year_month = $2
                ORDER BY generated_at DESC
                """,
                user_id, ym,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT report_id, year_month, summary, highlights_json, suggestions_json, totals_json, generated_at, model_version
                FROM monthly_report_history
                WHERE user_id = $1
                ORDER BY generated_at DESC
                LIMIT 50
                """,
                user_id,
            )
    return [_serialize_monthly_report_row(r) for r in rows]


@app.delete("/api/agents/monthly-report/{report_id}", status_code=204)
async def delete_monthly_report(report_id: str, user: dict = Depends(get_current_user)):
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid report_id")
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM monthly_report_history WHERE report_id = $1 AND user_id = $2",
            rid, int(user["user_id"]),
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Report not found")


@app.post("/api/agents/monthly-report/generate")
async def generate_monthly_report(body: MonthlyReportGenerateRequest, user: dict = Depends(get_current_user)):
    user_id = int(user["user_id"])
    ym, _, _ = _month_range_from_year_month(body.year_month)

    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_runs (run_id, user_id, workflow_type, status, started_at)
            VALUES ($1, $2, 'monthly_report', 'running', $3)
            """,
            run_id, user_id, started_at,
        )

    try:
        payload = await _build_monthly_report_payload(user_id, ym)
        report = _generate_report_with_gemini(payload)
        report_id = uuid.uuid4()
        generated_at = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO monthly_report_history (
                    report_id, user_id, year_month, summary, highlights_json, suggestions_json, totals_json, generated_at, model_version
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, $9)
                """,
                report_id,
                user_id,
                ym,
                report["summary"],
                json.dumps(report["highlights"]),
                json.dumps(report["suggestions"]),
                json.dumps(payload["totals"]),
                generated_at,
                GEMINI_MODEL if GEMINI_API_KEY else "deterministic-fallback",
            )
            await conn.execute(
                """
                INSERT INTO monthly_reports (
                    user_id, year_month, summary, highlights_json, suggestions_json, totals_json, generated_at, model_version
                ) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7, $8)
                ON CONFLICT (user_id, year_month) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    highlights_json = EXCLUDED.highlights_json,
                    suggestions_json = EXCLUDED.suggestions_json,
                    totals_json = EXCLUDED.totals_json,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
                """,
                user_id,
                ym,
                report["summary"],
                json.dumps(report["highlights"]),
                json.dumps(report["suggestions"]),
                json.dumps(payload["totals"]),
                generated_at,
                GEMINI_MODEL if GEMINI_API_KEY else "deterministic-fallback",
            )
            latency_ms = int((generated_at - started_at).total_seconds() * 1000)
            await conn.execute(
                """
                UPDATE agent_runs
                SET status = 'completed', completed_at = $2, latency_ms = $3
                WHERE run_id = $1
                """,
                run_id, generated_at, latency_ms,
            )
        return {
            "report_id": str(report_id),
            "year_month": ym,
            "summary": report["summary"],
            "highlights": report["highlights"],
            "suggestions": report["suggestions"],
            "totals": payload["totals"],
            "generated_at": generated_at.isoformat(),
            "model_version": GEMINI_MODEL if GEMINI_API_KEY else "deterministic-fallback",
            "cached": False,
        }
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_runs
                SET status = 'failed', completed_at = NOW(), error = $2
                WHERE run_id = $1
                """,
                run_id, str(exc),
            )
        raise


# --- NL2SQL Models ---

class NL2SQLGenerateRequest(BaseModel):
    question: str

class NL2SQLExecuteRequest(BaseModel):
    sql: str


# --- NL2SQL Routes ---

@app.post("/api/nl2sql/generate")
async def nl2sql_generate(req: NL2SQLGenerateRequest):
    """Translate a natural language question to SQL using AlloyDB AI NL2SQL."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT alloydb_ai_nl.get_sql($1::text, $2::text, '{}'::json) ->> 'sql' AS sql",
                "app_config",
                req.question.strip(),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"NL2SQL generation failed: {e}")
    return {"question": req.question, "sql": row["sql"]}


ROW_LIMIT = 200

@app.post("/api/nl2sql/execute")
async def nl2sql_execute(req: NL2SQLExecuteRequest):
    """Execute a SQL query (SELECT only) and return columns + rows (capped at ROW_LIMIT)."""
    sql = req.sql.strip().rstrip(";")
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=422, detail="Only SELECT statements are allowed")
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(f"SELECT * FROM ({sql}) _q LIMIT {ROW_LIMIT + 1}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Query failed: {e}")
    if not rows:
        return {"columns": [], "rows": [], "truncated": False}
    truncated = len(rows) > ROW_LIMIT
    rows = rows[:ROW_LIMIT]
    columns = list(rows[0].keys())
    result_rows = [
        [str(v) if not isinstance(v, (int, float, bool, type(None))) else v for v in row.values()]
        for row in rows
    ]
    return {"columns": columns, "rows": result_rows, "truncated": truncated}


@app.get("/api/budgets/usage")
async def fetch_budget_usage():
    """
    Return spending vs. budget limit for every category the user has configured.

    Spending is summed from the transactions table for the current calendar month.
    Only categories present in BudgetPrefs are included in the response.

    Response shape: [{"category": str, "total_spent": float, "budget_limit": float}, ...]
    Example:        [{"category": "dining", "total_spent": 120.0, "budget_limit": 100.0}]
    """
    # Compute the start of the current calendar month (UTC), same as current-month endpoint
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                bp.category,
                -- Sum all transaction amounts for this category this month.
                -- ABS() because debit amounts are stored as negatives; we want a positive spend figure.
                -- COALESCE returns 0 when there are no matching transactions yet.
                COALESCE(SUM(ABS(t.amount)), 0) AS total_spent,
                bp.amount                        AS budget_limit
            FROM "BudgetPrefs" bp
            LEFT JOIN transactions t
                -- Match on category name (case-insensitive) and restrict to current month
                ON LOWER(t.spending_category) = LOWER(bp.category)
               AND t.timestamp >= $1
            GROUP BY bp.category, bp.amount
            ORDER BY bp.category
            """,
            month_start,
        )

    # Convert NUMERIC fields to float for JSON serialisation
    return [
        {
            "category":     row["category"],
            "total_spent":  float(row["total_spent"]),
            "budget_limit": float(row["budget_limit"]),
        }
        for row in rows
    ]
