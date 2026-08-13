# JKR AI Calling

[![Live Web Application](https://img.shields.io/badge/Vercel-Deployed-black?style=for-the-badge&logo=vercel)](https://jkr-calling.vercel.app/)
[![Stack](https.img.shields.io/badge/Stack-Next.js_14_%7C_FastAPI_%7C_Postgres-blue?style=for-the-badge)](https://jkr-calling.vercel.app/)

India-first, multilingual (Telugu / Hindi / English, code-switched) multi-tenant AI calling
platform. Makes and receives calls, qualifies leads, answers from business-approved knowledge,
books appointments, hands off to humans, and reports business outcomes — not just call volume.

**Live Application**: [https://jkr-calling.vercel.app/](https://jkr-calling.vercel.app/)

No real telephony call is ever placed by default. Every provider defaults to a mock adapter; see
`.env.example` and `docs/SECURITY_AND_COMPLIANCE.md` §1.

## Start here

- **Deployed Frontend**: [https://jkr-calling.vercel.app/](https://jkr-calling.vercel.app/)
- `docs/MASTER_PLAN.md` — what this is, how it's scoped, where everything lives
- `docs/ARCHITECTURE.md` — service topology and module boundaries
- `docs/IMPLEMENTATION_CHECKLIST.md` — current build status, kept up to date


## Running locally — step by step

`make dev` (the Docker Compose path) is not yet usable: the Dockerfiles it references under
`infra/docker/` haven't been written this pass (see `docs/IMPLEMENTATION_CHECKLIST.md`'s "Known
gaps"). Every service in this build has been run, tested, and demoed **natively** instead —
Docker Compose is only used for the stateful infra (Postgres/Redis/MinIO). Follow the steps below.

### 0. Prerequisites

- **Docker** (Desktop or equivalent), running — for Postgres, Redis, MinIO
- **Node.js >= 20** and **pnpm >= 9** (`corepack enable` will pick up the version pinned in
  `package.json`)
- **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**
- A bash-compatible shell (the Makefile assumes one)

### 1. Clone and configure

```bash
git clone https://github.com/APPARAOsiddapureddy/jkrcalling.git
cd jkrcalling
cp .env.example .env
```

Nothing in `.env` needs to be edited to run the local demo — every provider (telephony, STT, TTS,
LLM) defaults to a mock adapter, and no real call is ever placed unless `ENABLE_LIVE_CALLS=true`
is set explicitly (see `.env.example` and `docs/SECURITY_AND_COMPLIANCE.md` §1).

### 2. Install dependencies and start infra

```bash
make setup
```

This runs `pnpm install`, `uv sync --all-packages`, starts `postgres`/`redis`/`minio` via Docker
Compose, waits for Postgres to become healthy, and applies Alembic migrations.

### 3. Seed demo data

```bash
make seed
```

Loads the three demo workspaces (Aaha Dental, Adarsh Educational, JKR Creatives) and prints each
workspace's owner login to the terminal — save these, you'll need them to log in.

### 4. Start every service, each in its own terminal

Open five terminals at the repo root and run one command in each:

```bash
# Terminal 1 — API (the only backend surface the browser talks to)
cd services/api && uv run --package jkr-api uvicorn app.main:app --reload --port 8000

# Terminal 2 — voice worker (real-time call/conversation loop)
cd services/voice-worker && uv run --package jkr-voice-worker uvicorn app.main:app --reload --port 8100

# Terminal 3 — campaign worker (background jobs)
cd services/campaign-worker && uv run --package jkr-campaign-worker dramatiq app.tasks -p 1 -t 1

# Terminal 4 — intelligence worker (background jobs)
cd services/intelligence-worker && uv run --package jkr-intelligence-worker dramatiq app.tasks -p 1 -t 1

# Terminal 5 — web frontend
pnpm --filter web dev
```

(`services/integration-worker` has no code yet — skip it.)

### 5. Open the app

http://localhost:3000 — log in with one of the owner accounts printed by `make seed`.

### 6. Optional: scripted demo / e2e test

With the full stack up:

```bash
make demo   # scripted walkthrough of the full demo flow (safety gate → dial → book → analytics)
make e2e    # Playwright browser test of the UI-navigable portion of the same flow
```

### Stopping and cleaning up

```bash
make down    # stop the postgres/redis/minio containers (Ctrl+C stops the native services above)
make clean   # stop containers, remove volumes, node_modules, .venv, and build artifacts
```

## Repository layout

See `docs/ARCHITECTURE.md` §1–2 for the full picture. Short version: `apps/web` is the only
frontend, `services/api` is the only backend surface the browser talks to, `services/voice-worker`
runs the real-time call/conversation loop in its own process, `services/campaign-worker` /
`intelligence-worker` / `integration-worker` are background job processors, `packages/db` is the
single source of truth for the database schema.
