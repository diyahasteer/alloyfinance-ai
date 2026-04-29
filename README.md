# alloyfinance-ai

Bootstrapped React frontend + FastAPI backend with a basic API handshake.

## Setup

Requires the `.env` file (get this from the team).

**Step 1 — Start the AlloyDB port-forward** (keep this running in a separate terminal):
```bash
gcloud alloydb instances port-forward INSTANCE_NAME \
  --port=5433 \
  --project=PROJECT_ID \
  --region=REGION
```

**Step 2 — Start the app:**

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

## Authentication

- The app now uses email/password authentication with JWT bearer tokens.
- A dev user is automatically seeded on backend startup:
  - email: `foo@bar.com`
  - password: `password`
