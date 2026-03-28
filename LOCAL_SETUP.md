# Local Development Setup

## Prerequisites

Make sure the following are installed on your machine:

- **Node.js** v18+ — [nodejs.org](https://nodejs.org)
- **Python** 3.11+ — [python.org](https://python.org)
- **PostgreSQL** 14+ — [postgresql.org](https://www.postgresql.org/download)
- **Git**

---

## 1. Clone the Repositories

```bash
git clone https://github.com/Digizone-lk/AstrynoxERP-frontend.git frontend
git clone https://github.com/Digizone-lk/AstrynoxERP-backend.git backend
```

---

## 2. Set Up PostgreSQL Database

Open `psql` or your preferred PostgreSQL client and run:

```sql
CREATE DATABASE saas_billing;
```

Note the connection details you'll need:
- Host: `localhost`
- Port: `5432`
- Database: `saas_billing`
- Username: your postgres username (default: `postgres`)
- Password: your postgres password

---

## 3. Set Up the Backend

### 3.1 Navigate to the backend directory

```bash
cd backend
```

### 3.2 Create and activate a virtual environment

```bash
python -m venv venv
```

**Windows (Git Bash / PowerShell):**
```bash
source venv/Scripts/activate
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### 3.3 Install dependencies

```bash
pip install -r requirements.txt
```

### 3.4 Create the environment file

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and update:

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/saas_billing
SECRET_KEY=any-random-string-at-least-32-characters-long
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
FRONTEND_URL=http://localhost:3000
ENVIRONMENT=development
```

> Replace `YOUR_PASSWORD` with your actual PostgreSQL password.

### 3.5 Run database migrations

```bash
alembic upgrade head
```

### 3.6 Start the backend server

```bash
uvicorn app.main:app --reload --port 8000
```

Backend will be running at: `http://localhost:8000`
API docs available at: `http://localhost:8000/docs`

---

## 4. Set Up the Frontend

Open a **new terminal** and navigate to the frontend directory:

```bash
cd frontend
```

### 4.1 Install dependencies

```bash
npm install
```

### 4.2 Create the environment file

```bash
cp .env.local.example .env.local
```

> If `.env.local.example` doesn't exist, create `.env.local` manually:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 4.3 Start the frontend dev server

```bash
npm run dev
```

Frontend will be running at: `http://localhost:3000`

---

## 5. Verify Everything Works

1. Open `http://localhost:3000` — you should be redirected to `/login`
2. Open `http://localhost:8000/docs` — you should see the FastAPI Swagger UI
3. Register an account via the UI or the API docs
4. Log in and confirm you land on `/dashboard`

---

## Quick Reference

| Service  | URL                          | Command                                  |
|----------|------------------------------|------------------------------------------|
| Frontend | http://localhost:3000        | `npm run dev` (inside `frontend/`)       |
| Backend  | http://localhost:8000        | `uvicorn app.main:app --reload` (inside `backend/`) |
| API Docs | http://localhost:8000/docs   | —                                        |

---

## Troubleshooting

**`psycopg2` install fails on Windows**
The `requirements.txt` uses `psycopg2-binary` which should work without a compiler. If it fails, try:
```bash
pip install psycopg2-binary --force-reinstall
```

**Alembic migration errors**
Make sure your `DATABASE_URL` in `.env` is correct and PostgreSQL is running before running migrations.

**CORS errors in the browser**
Ensure `FRONTEND_URL=http://localhost:3000` is set correctly in the backend `.env`.

**`venv` not activating on Windows**
If `source venv/Scripts/activate` doesn't work in PowerShell, run:
```powershell
venv\Scripts\Activate.ps1
```
