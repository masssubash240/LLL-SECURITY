# AI Security Shield

Real-time **AI protection layer** for chatbots: scan every message for injection, jailbreaks, harmful content, and leakage; score and optionally block; filter assistant output. Built with **FastAPI** + **React (Vite)**, optional **Firebase Firestore**, and a **cyberpunk SOC-style dashboard**.

---

## Table of contents

- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Frontend](#frontend)
- [Security engine](#security-engine)
- [Firestore collections](#firestore-collections)
- [Troubleshooting](#troubleshooting)
- [Production notes](#production-notes)
- [License](#license)

---

## Architecture

```text
User message → Input scanner → Chat / LLM hook → Output filter → Safe response
```

| Stage | What it does |
|--------|----------------|
| **Input scanner** | Regex/heuristics + optional semantic similarity (`sentence-transformers`) vs. attack phrase bank → **threat score 0–100**; **block** if score ≥ threshold (~72). |
| **Chat** | Template “assistant” replies in demo; replace with your LLM behind the same gate. |
| **Output filter** | Redacts/refuses echoes of risky patterns in model output. |

---

## Repository layout

```text
EXPO\LLM\
├── backend\              # FastAPI application
│   ├── main.py           # Routes, lifespan, chat sandbox
│   ├── security_engine.py
│   ├── firestore_db.py
│   ├── auth.py           # JWT + password hashing (pbkdf2_sha256)
│   ├── config.py
│   ├── models.py
│   ├── requirements.txt
│   └── .env.example
├── frontend\             # React + Vite SPA
│   ├── src\
│   │   ├── api\          # Axios client, /api proxy
│   │   ├── pages\        # Dashboard, Chat, Monitor, Simulator, etc.
│   │   ├── components\   # Glass cards, neon frame, particles, terminal UI
│   │   └── data\         # attackPrompts.js (testing packs)
│   └── vite.config.js    # dev proxy → :8000
└── README.md
```

---

## Prerequisites

| Tool | Notes |
|------|--------|
| **Node.js** | 18+ |
| **Python** | 3.10+ (3.14+ OK; bcrypt not required — auth uses PBKDF2) |
| **Firebase** | Optional: service account JSON for persistent DB |

---

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env    # Windows: copy ; adjust secrets
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API base: **`http://127.0.0.1:8000`**

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (often **`http://localhost:5173`**).

Dev server **`/api`** is proxied to **`http://127.0.0.1:8000`** (`frontend/vite.config.js`).

**PowerShell:** If `npm` fails (“running scripts is disabled”), use **`npm.cmd run dev`**, or set execution policy for your user:  
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Login (development defaults)

Set in `backend/.env` (see `.env.example`):

| Field | Default |
|--------|---------|
| Email | `admin@shield.local` |
| Password | `SecureAdmin123!` |

**Change these before any real deployment.**

- **Admin** — full sidebar: Live Monitor, Attack Logs, Analytics, Attack Simulator.
- **User** (Firestore `users` or future flows) — Dashboard, Chatbot, Settings.

---

## Configuration

Copy **`backend/.env.example`** → **`backend/.env`**.

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | Sign JWTs (use a long random string in production) |
| `JWT_ALGORITHM` | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session length |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Bootstrap admin login |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Firebase service account JSON |
| `SECURITY_DISABLE_SEMANTIC` | `true` = skip embeddings, regex-only (faster, less RAM) |
| `CORS_ORIGINS` | Comma-separated origins, e.g. `http://localhost:5173` |

Optional frontend override:

```env
# frontend/.env
VITE_API_URL=http://127.0.0.1:8000
```

### ML stack

If **`torch`** / **`sentence-transformers`** fail to install, install a CPU wheel from [pytorch.org](https://pytorch.org) for your OS/Python, then:

```bash
pip install -r requirements.txt
```

Set **`SECURITY_DISABLE_SEMANTIC=true`** for a lightweight demo without downloading `all-MiniLM-L6-v2`.

---

## API reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | — | Liveness |
| `POST` | `/auth/login` | — | `{ "email", "password" }` → JWT + role |
| `GET` | `/me` | User | Current user from JWT |
| `POST` | `/scan` | User | Scan text, log threat |
| `POST` | `/chat` | User | Scan message; if blocked → 400 + scan; else reply + output filter |
| `GET` | `/logs` | Admin | Recent operational logs |
| `GET` | `/threats` | Admin | Threat ledger |
| `GET` | `/analytics` | Admin | Summary + timeline hints |
| `POST` | `/simulate` | Admin | Batch-run default or custom attack strings |

---

## Frontend

| Route | Role | Description |
|-------|------|-------------|
| `/login` | Public | JWT login |
| `/` | All | Security dashboard (charts, terminal feed, alerts) |
| `/monitor` | Admin | Polling live threats + logs |
| `/chat` | All | Protected chat + last scan panel |
| `/logs` | Admin | Full attack log table |
| `/analytics` | Admin | Analytics charts |
| `/simulator` | Admin | Red-team batch tests |
| `/settings` | All | Session / integration notes |

**Stack:** React 19, Vite 8, Tailwind v4, Framer Motion, Recharts, React Router, Lucide icons.

**`src/data/attackPrompts.js`** — Example adversarial prompts for **testing your own sandbox only**. Do not use against third-party services without authorization.

---

## Security engine

- **Files:** `backend/security_engine.py`
- **Signals:** prompt injection, jailbreak/DAN-style phrases, harmful roleplay hooks, PII/secret-like patterns, spam (length, URLs, repetition), optional **cosine similarity** to a fixed attack phrase list.
- **Tuning:** Adjust regex weights, reference phrases, block threshold, and output patterns in code to match your policy.

---

## Firestore collections

Used when **`GOOGLE_APPLICATION_CREDENTIALS`** points to a valid JSON key:

| Collection | Purpose |
|------------|---------|
| `users` | Optional non-admin accounts (email, `password_hash`, `role`) |
| `threats` | Scored events + preview + blocked flag |
| `logs` | Structured log lines |
| `analytics` | Document `summary` (counters / by category) |
| `blocked_prompts` | Hashes / counts for blocked content |

Without Firebase, data is kept **in-memory** (resets on restart).

---

## Troubleshooting

| Issue | What to try |
|--------|-------------|
| `ECONNREFUSED` on `/api` | Start backend on port **8000** before or with the UI. |
| `npm` script errors in PowerShell | Use **`npm.cmd`**, or fix execution policy (see Quick start). |
| Wrong `cd` | Run `npm` from **`frontend/`**, `uvicorn` from **`backend/`**. |
| Port 5173 busy | Vite may pick **5174+**; use the URL shown in the terminal. |
| Slow first request / large download | First semantic model load downloads **MiniLM**; or set **`SECURITY_DISABLE_SEMANTIC=true`**. |
| Passlib / bcrypt errors | This repo uses **PBKDF2** in `auth.py`; reinstall deps if you changed it back to bcrypt. |

---

## Production notes

- Rotate **`JWT_SECRET`**, use **HTTPS**, and apply **rate limiting** on `/scan` and `/chat`.
- Replace **`generate_reply`** in `main.py` with your **real LLM**; keep input scan + output filter in front of production traffic.
- Lock down **Firestore rules** and **IAM** for the service account.
- Review and extend detection lists for your domain; consider async queues for logging at scale.

---

## License

MIT — adjust for your organization if needed.
