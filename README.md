# alloyfinance-ai

Bootstrapped React frontend + FastAPI backend with a basic API handshake.

## Running with Docker (recommended)

The easiest way to run everything. Only requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Postgres: localhost:5433

To stop everything: `docker compose down`
To stop and wipe the database: `docker compose down -v`

---

## Running locally (manual setup)

### Backend (FastAPI)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

Open the app at `http://localhost:5173` and it will call the backend at `http://localhost:8000/api/hello`.

> **Note:** Manual setup requires a running PostgreSQL instance matching the credentials in `.env`.
