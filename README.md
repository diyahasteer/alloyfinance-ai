# alloyfinance-ai

Bootstrapped React frontend + FastAPI backend with a basic API handshake.

## Backend (FastAPI)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

Open the app at `http://localhost:5173` and it will call the backend at `http://localhost:8000/api/hello`.

## GKE + AlloyDB Omni (deploy)

One-time project setup and per-member setup for GKE cluster `alloydb-demo` and AlloyDB Omni are in **[deploy/GKE-ALLOYDB-SETUP.md](deploy/GKE-ALLOYDB-SETUP.md)**. Optional scripts: `deploy/setup-project.sh`, `deploy/setup-member.sh`.
