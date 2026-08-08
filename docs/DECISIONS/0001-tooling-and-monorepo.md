# ADR-0001: Monorepo tooling

## Status
Accepted

## Context
Spec §4 recommends pnpm + Turborepo for TypeScript and `uv` for Python, in one monorepo. No
existing repo constrains this — greenfield choice.

## Decision
- TypeScript: pnpm workspaces + Turborepo (`pnpm-workspace.yaml`, `turbo.json`).
- Python: a single `uv` workspace rooted at the repo root (`pyproject.toml` `[tool.uv.workspace]`)
  with members `packages/db` and each `services/*` Python service, all pinned to Python 3.12
  (installed via `uv python install 3.12` — the host machine's default `python3` was 3.14, which
  risks missing wheels for some scientific/db packages; 3.12 is the spec's stated minimum and has
  the widest current wheel coverage).
- API client generation: a hand-written typed fetch client in `packages/sdk` against Zod schemas
  in `packages/contracts`, rather than a full OpenAPI-codegen pipeline. A generator step (e.g.
  `openapi-typescript`) can be added later without changing the consuming code's shape; deferred
  to keep the build free of an extra network-dependent codegen step in this pass.

## Consequences
`packages/contracts` must be kept in sync with `services/api` schemas by hand during this build —
tracked as a checklist item, not automated yet.
