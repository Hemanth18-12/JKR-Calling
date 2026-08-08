# JKR AI Calling

India-first, multilingual (Telugu / Hindi / English, code-switched) multi-tenant AI calling
platform. Makes and receives calls, qualifies leads, answers from business-approved knowledge,
books appointments, hands off to humans, and reports business outcomes — not just call volume.

No real telephony call is ever placed by default. Every provider defaults to a mock adapter; see
`.env.example` and `docs/SECURITY_AND_COMPLIANCE.md` §1.

## Start here

- `docs/MASTER_PLAN.md` — what this is, how it's scoped, where everything lives
- `docs/ARCHITECTURE.md` — service topology and module boundaries
- `docs/IMPLEMENTATION_CHECKLIST.md` — current build status, kept up to date

## Quickstart

```bash
cp .env.example .env
make setup       # installs deps, starts postgres/redis/minio, runs migrations
make seed        # loads the three demo workspaces (owner login printed per workspace)
```

Then start every service natively — see the per-service commands in the Makefile's
`dev-native` target (`services/api`, `services/voice-worker`, `services/campaign-worker`,
`services/intelligence-worker`, and `pnpm --filter web dev`, each in its own terminal) — and open
http://localhost:3000. `make dev` (the Docker Compose path) is not yet usable: the Dockerfiles it
references under `infra/docker/` haven't been written this pass (see
`docs/IMPLEMENTATION_CHECKLIST.md`'s "Known gaps"); every service in this build has been run,
tested, and demoed natively instead.

Once the stack is up:

```bash
make demo   # scripted walkthrough of the full demo flow (safety gate → dial → book → analytics)
make e2e    # Playwright browser test of the UI-navigable portion of the same flow
```

## Repository layout

See `docs/ARCHITECTURE.md` §1–2 for the full picture. Short version: `apps/web` is the only
frontend, `services/api` is the only backend surface the browser talks to, `services/voice-worker`
runs the real-time call/conversation loop in its own process, `services/campaign-worker` /
`intelligence-worker` / `integration-worker` are background job processors, `packages/db` is the
single source of truth for the database schema.
