from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncpg
import os

from pathlib import Path
from dotenv import load_dotenv
# Load .env from cwd or from project root (when running from backend/)
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

app = FastAPI(title="AlloyFinance API", version="0.1.0")

# Allow local dev frontend by default. Tighten for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NEED TO UPDATE THIS FOR PRODUCTION
def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"

DATABASE_URL = _get_database_url()

pool: asyncpg.Pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    # Create table if it doesn't exist
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

@app.on_event("shutdown")
async def shutdown():
    await pool.close()


# --- MODELS ---

class ItemCreate(BaseModel):
    name: str
    value: Optional[str] = None

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None

# --- ROUTES ---


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}
