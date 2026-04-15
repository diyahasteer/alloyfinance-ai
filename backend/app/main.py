import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="AlloyFinance API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8001", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

pool: asyncpg.Pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, ssl=False)
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
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id UUID PRIMARY KEY,
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
        # Budget preferences: one row per category, amount is the user's spending limit
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS "BudgetPrefs" (
                category TEXT PRIMARY KEY,
                amount   NUMERIC(18, 2) NOT NULL
            )
        """)

@app.on_event("shutdown")
async def shutdown():
    await pool.close()

# --- Spending Category Enum ---

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

class ItemCreate(BaseModel):
    name: str
    value: Optional[str] = None

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None


# --- Budget Models ---

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
async def create_transaction(txn: TransactionCreate):
    txn_id = uuid.uuid4()
    ts = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO transactions (
                transaction_id, timestamp, amount, merchant_name,
                merchant_category, spending_category, transaction_type,
                payment_method, city, country, currency, description
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *""",
            txn_id, ts, txn.amount, txn.merchant_name,
            txn.merchant_category, txn.spending_category, txn.transaction_type,
            txn.payment_method, txn.city, txn.country, txn.currency,
            txn.description,
        )
        return _serialize_transaction(row)


@app.get("/api/transactions/category/{spending_category}")
async def fetch_transactions_by_category(spending_category: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE LOWER(spending_category) = LOWER($1)
               ORDER BY timestamp DESC""",
            spending_category,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/current-month")
async def fetch_current_month():
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE timestamp >= $1
               ORDER BY timestamp DESC""",
            month_start,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/previous-month")
async def fetch_previous_month():
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if current_month_start.month == 1:
        prev_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
    else:
        prev_month_start = current_month_start.replace(month=current_month_start.month - 1)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               WHERE timestamp >= $1 AND timestamp < $2
               ORDER BY timestamp DESC""",
            prev_month_start, current_month_start,
        )
        return [_serialize_transaction(r) for r in rows]


@app.get("/api/transactions/recent")
async def fetch_n_transactions(limit: int = Query(default=10, ge=1, le=500)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM transactions
               ORDER BY timestamp DESC
               LIMIT $1""",
            limit,
        )
        return [_serialize_transaction(r) for r in rows]


# --- Budget Routes ---

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


@app.post("/api/nl2sql/execute")
async def nl2sql_execute(req: NL2SQLExecuteRequest):
    """Execute a SQL query (SELECT only) and return columns + rows."""
    sql = req.sql.strip().rstrip(";")
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=422, detail="Only SELECT statements are allowed")
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Query failed: {e}")
    if not rows:
        return {"columns": [], "rows": []}
    columns = list(rows[0].keys())
    result_rows = []
    for row in rows:
        result_rows.append([
            str(v) if not isinstance(v, (int, float, bool, type(None))) else v
            for v in row.values()
        ])
    return {"columns": columns, "rows": result_rows}


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