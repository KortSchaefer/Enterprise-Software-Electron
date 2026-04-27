# Enterprise Software Electron

Electron desktop shell with a FastAPI backend, Supabase persistence, and tenant-installable apps for Inventory, Timeclock, Chat, and POS.

## Prerequisites

- Windows PowerShell
- Node.js with npm
- Python 3.11+ recommended
- A Supabase project

## Quick Start

Run these commands from the project root:

```powershell
npm install
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
npm run dev:full
```

If you are already inside `backend`, do not run `cd backend` again. The venv activation command from `backend` is:

```powershell
.\.venv\Scripts\Activate.ps1
```

From the project root, activate it with:

```powershell
.\backend\.venv\Scripts\Activate.ps1
```

## Environment

Create `backend/.env`. The backend and seed script load this file automatically.

Required Supabase values:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
ALLOW_TENANT_SWITCH=true
```

Use `SUPABASE_SERVICE_ROLE_KEY` for local development and seeding. Do not commit real secrets.

## Supabase Schema

The database schema is maintained in:

```text
backend/supabase/schema.sql
```

After schema changes, open the Supabase SQL Editor, paste the full contents of `backend/supabase/schema.sql`, and run it. If the app or seed script reports a missing table such as `public.pos_menu_categories`, the SQL in Supabase is not up to date.

## Seed Data

From the `backend` directory with the venv active:

```powershell
python seed.py --bootstrap-tenant demo-tenant
python seed.py --demo
```

`--bootstrap-tenant demo-tenant` installs the baseline tenant apps and defaults.

`--demo` creates demo users, memberships, inventory, timeclock, chat, and POS data.

Demo login:

```text
Tenant: demo-tenant
Email: alice@demo-tenant.local
Password: Password123!
```

Other seeded users:

```text
admin@demo-tenant.local
bob@demo-tenant.local
```

They use the same password.

## Running The App

Start backend, renderer, and Electron together:

```powershell
npm run dev:full
```

Manual backend only:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Manual renderer and Electron:

```powershell
npm run dev
```

Useful URLs:

```text
Backend health: http://127.0.0.1:8000/health
Backend docs:   http://127.0.0.1:8000/docs
Renderer dev:   http://localhost:5173
```

## POS App

`pos` is a popout-only app. It should appear in the installed apps list after seeding or installing it for the tenant. Clicking POS from the dashboard opens or focuses a dedicated POS window instead of rendering inside the dashboard.

The POS flow is:

```text
Dashboard -> POS popout -> Table selector -> Order entry screen
```

If the dashboard says `No renderer module mapped for: pos`, the dashboard launcher code has regressed and is trying to render POS inline.

## Tenant Switching

Tenant switching is a development workflow. It is controlled by:

```env
ALLOW_TENANT_SWITCH=true
```

Set it in `backend/.env`, then restart the app. If disabled, the switch-tenant menu/page should not be available during normal use.

## Build

```powershell
npm run build
```

This builds the renderer with Vite.

## Tests

Backend test command, if tests are present:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```

The root `npm test` script is currently a placeholder.

## Local State

Electron bootstrap state is stored under the user app-data directory, for example:

```text
C:\Users\<you>\AppData\Roaming\enterprise-software-electron\bootstrap-state.json
```

If tenant activation or login state looks stale during development, close the app and inspect that file.