# FastAPI + Supabase Setup

## 1) Create and activate a virtual environment (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 2) Install dependencies

```powershell
pip install -r requirements.txt
```

## 3) Configure Supabase

Create `backend/.env`. The backend loads this file automatically on startup and when running `seed.py`.

```powershell
$env:SUPABASE_URL="https://your-project.supabase.co"
$env:SUPABASE_KEY="your-anon-or-service-role-key"
$env:SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
$env:ALLOW_TENANT_SWITCH="true"
```

`SUPABASE_SERVICE_ROLE_KEY` is recommended for the backend and seed script. If it is missing, the app falls back to `SUPABASE_KEY`, then `SUPABASE_ANON_KEY`.
`ALLOW_TENANT_SWITCH=true` enables the Electron tenant switch menu for development only.

## 4) Create the database schema

Open the Supabase SQL Editor and run:

```sql
\i supabase/schema.sql
```

If your SQL editor does not support `\i`, copy the contents of `supabase/schema.sql` directly into the editor and execute it.

## 5) Run the API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 6) Seed data

```powershell
python seed.py --bootstrap-tenant demo-tenant
python seed.py --demo
```

`--bootstrap-tenant` creates tenant apps and policy only.
`--demo` creates the demo users, memberships, inventory, timeclock, chat, and POS records.

## 7) Run backend tests

```powershell
python -m unittest discover -s tests
```

## 8) Test it

- Health: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`
