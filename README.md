# Yale SOM Course Explorer

Browse the Yale SOM course catalog and ask an agent about it. React + FastAPI +
pydantic-ai, with the catalog in a SQL database, accounts behind bcrypt, and each
person's chat history saved to their account.

Built for MGT 409, Lecture 8 — the Lecture 7 app with the JSON file swapped for a
real database, a login screen added, and the whole thing deployable.

## What's here

```
backend/     FastAPI app — auth, courses API, chat, the pydantic-ai agent
  db.py               SQLAlchemy engine + courses/users/chats tables
  auth.py             bcrypt hashing and JWT sign-in tokens
  tools.py            search_courses, querying the courses table
  agent.py            the pydantic-ai agent (catalog tool + native web search)
  main.py             the HTTP routes
  migrate_to_postgres.py   one-shot SQLite -> Supabase copy
frontend/    React + Vite — catalog grid, course modal, chat panel, login gate
data/        yale_som.db (not committed — see below)
render.yaml  Render Blueprint for both services
```

## Database

Three tables in one database:

| table | what it holds |
| --- | --- |
| `courses` | the 234-row SOM catalog, shipped in the course zip |
| `users` | one row per account: username + bcrypt hash |
| `chats` | one row per message, linked to a user |

`courses` comes with the zip. `users` and `chats` are created automatically on
first startup, locally and in production.

The same code runs on both backends: with `DATABASE_URL` unset it uses
`data/yale_som.db`; set it to a Postgres URL and SQLAlchemy talks to Supabase
instead. Nothing else changes.

## Running it locally

**1. Get the database.** Download `data.zip` from the Lecture 8 page and unzip it
so the file lands at `data/yale_som.db`. It is gitignored, so every clone needs
this step.

**2. Set your key.**

```bash
cp .env.example .env
```

Then put your real `PORTKEY_API_KEY` in `.env`.

**3. Backend.**

```bash
cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

```bash
cd backend && ./.venv/bin/uvicorn main:app --reload --port 8000
```

**4. Frontend,** in a second terminal:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173, create an account, and the catalog and chat are
yours. API docs are at http://127.0.0.1:8000/docs.

If the frontend runs on a port other than 5173, that is fine — the backend allows
any localhost port. If your backend is not on 8000, set `VITE_API_BASE` in
`frontend/.env.local`.

## Deploying

Backend first, so its URL exists for the frontend.

**1. Supabase.** Create a project, then copy the **Session pooler** connection
string from *Project Settings → Database*. Load the catalog into it:

```bash
cd backend && DATABASE_URL='postgresql://...' ./.venv/bin/python migrate_to_postgres.py
```

That creates all three tables and copies the 234 courses. Local accounts are not
copied — sign up again on the deployed site.

**2. Render — backend.** New Web Service from this repo, root directory
`backend`, build `pip install -r requirements.txt`, start
`uvicorn main:app --host 0.0.0.0 --port $PORT`. Environment variables:

| key | value |
| --- | --- |
| `DATABASE_URL` | the Supabase connection string |
| `PORTKEY_API_KEY` | your Portkey key |
| `JWT_SECRET` | any long random string (`openssl rand -base64 32`) |

**3. Render — frontend.** New Static Site, root directory `frontend`, build
`npm ci && npm run build`, publish `dist`. Set `VITE_API_BASE` to the backend URL
from step 2. Add a rewrite from `/*` to `/index.html` so refreshing a route works.

**4. Back to the backend.** Set `FRONTEND_ORIGIN` to the static site's URL and
redeploy — until you do, the browser blocks every API call as cross-origin.

`render.yaml` encodes all of this if you would rather use a Blueprint.

### Notes on the free tier

The backend sleeps after 15 minutes idle, so the first request after a quiet
spell takes ~30 seconds. Sign-in survives it: tokens are JWTs, so a restart does
not log anyone out — as long as `JWT_SECRET` is set and stays the same.
