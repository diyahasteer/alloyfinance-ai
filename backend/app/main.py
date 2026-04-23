import csv
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import jwt
from dotenv import load_dotenv
import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel, Field

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

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_ID:
    raise ValueError("GOOGLE_CLIENT_ID is not set")

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET is not set")

# JWT configuration for user session tokens.
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

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

@app.on_event("startup")
async def startup():
    """Initialize the database connection pool and ensure required schema exists.

    This runs once when the FastAPI app starts, so the app can safely assume
    that the tables exist for users, items, transactions, and budget preferences.
    """
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        ssl=False,
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
                google_id TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                picture TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
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
        # Budget preferences: one row per category, amount is the user's spending limit
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS "BudgetPrefs" (
                category TEXT PRIMARY KEY,
                amount   NUMERIC(18, 2) NOT NULL
            )
        """)

@app.on_event("shutdown")
async def shutdown():
    """Close the database pool cleanly when the application shuts down."""
    await pool.close()

# --- Auth ---
# Authentication is based on Google sign-in and JWT session tokens.

class GoogleLoginRequest(BaseModel):
    credential: str

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

@app.post("/auth/google")
async def google_login(body: GoogleLoginRequest):
    """Handle Google sign-in from the frontend and create/update the user record.

    This endpoint verifies the Google credential, upserts the user row, seeds
    default transactions for first-time users, and returns a JWT for the client.
    """
    try:
        idinfo = id_token.verify_oauth2_token(
            body.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Google authentication failed: Invalid or expired credential token",
        )
    except Exception as exc:
        logger.exception("Google token verification failed")
        raise HTTPException(
            status_code=502,
            detail="Google token verification failed. Please try again.",
        ) from exc

    google_id = idinfo["sub"]
    email = idinfo["email"]
    name = idinfo.get("name")
    picture = idinfo.get("picture")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO users (google_id, email, name, picture)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (email) DO UPDATE SET name = $3, picture = $4
               RETURNING id, email, name, picture""",
            google_id, email, name, picture,
        )

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


def _serialize_transaction(row: asyncpg.Record) -> dict:
    """Convert a transaction row to JSON-safe primitives for API responses.

    This normalizes UUIDs, timestamps, and numeric values so the frontend can
    render them directly without driver-specific types.
    """
    d = dict(row)
    d["transaction_id"] = str(d["transaction_id"])
    d["timestamp"] = d["timestamp"].isoformat()
    d["amount"] = float(d["amount"])
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
