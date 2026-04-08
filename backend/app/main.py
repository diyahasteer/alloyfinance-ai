import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from dotenv import load_dotenv
import asyncpg
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="AlloyFinance API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

pool: asyncpg.Pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
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

@app.on_event("shutdown")
async def shutdown():
    await pool.close()

# --- Auth ---

class GoogleLoginRequest(BaseModel):
    credential: str

def create_jwt(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
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
    try:
        idinfo = id_token.verify_oauth2_token(
            body.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")

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
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, picture FROM users WHERE id = $1",
            int(user["user_id"]),
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": str(row["id"]),
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
        }


# --- Item Models ---

class ItemCreate(BaseModel):
    name: str
    value: Optional[str] = None

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None


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
    """Convert a transaction row to a JSON-friendly dict."""
    d = dict(row)
    d["transaction_id"] = str(d["transaction_id"])
    d["timestamp"] = d["timestamp"].isoformat()
    d["amount"] = float(d["amount"])
    return d


# --- General Routes ---

@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}


# --- Item Routes ---

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
