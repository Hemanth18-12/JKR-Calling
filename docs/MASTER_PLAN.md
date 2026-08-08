# JKR AI Calling — Master Plan

## 1. What this is

JKR AI Calling is a multi-tenant, India-first AI outbound/inbound calling platform. It places
and receives calls in Telugu, Hindi, English and code-switched variants, qualifies leads,
answers questions from business-approved knowledge, books appointments, hands off to humans
when needed, and proves incremental business impact (not just call volume).

Positioning: *"An India-first multilingual AI revenue agent that calls leads, understands
customers, performs business actions and proves measurable business impact."*

Every call carries a brief, natural AI disclosure. The product is designed to be trusted, not
to impersonate a human.

## 2. Repository state at project start

Empty directory, no git history, no existing stack. This is a from-scratch build. See
`docs/DECISIONS/0001-tooling-and-monorepo.md` for why pnpm+Turborepo / uv-workspace was chosen
over alternatives.

## 3. Build strategy for this pass

Full production breadth (every table, every route, every integration, at full depth) is a
multi-month effort. This build pass uses a **deep-vertical-slice** strategy, confirmed with the
project owner: the core product loop — the demo flow in `docs/IMPLEMENTATION_CHECKLIST.md` §Demo
Flow (mirrors master-spec §33) — works end to end with real logic, real persistence and real
tests. Breadth beyond that loop is delivered as full schema + working CRUD + scaffolded UI, with
gaps explicitly tracked rather than silently implied. See `docs/DECISIONS/0007-scope-for-this-pass.md`.

No real telephony call is ever placed by default. Mock providers (STT/LLM/TTS/telephony) are the
default for every workspace; a real provider requires explicit workspace configuration,
`ENABLE_LIVE_CALLS=true`, and the destination number in an authorized allow-list. See
`docs/SECURITY_AND_COMPLIANCE.md`.

## 4. Reference repositories

| Repo | What we took from it | What we deliberately did not do |
|---|---|---|
| `CALLE-AI/awesome-phone-call-agents` | Consent-first calling, dry-run-by-default, E.164 normalization, suppression checks, idempotent dispatch, structured call results, retry/human-review queues | Did not adopt CALL-E as the only telephony provider — it's one adapter behind `TelephonyProvider` |
| `bolna-ai/bolna` | STT→LLM→TTS streaming orchestration shape, barge-in/interruption state machine, turn latency measurement, provider abstraction boundaries | Did not copy its orchestration engine wholesale — `TurnManager` and provider interfaces are reimplemented for this codebase's tenancy/safety requirements |
| `Shubhamsaboo/awesome-llm-apps` | RAG ingestion → chunk → embed → retrieve shape, structured extraction / missing-field / next-best-question pattern, post-call multi-stage analysis pattern | Did not use Streamlit or any of its demo scaffolding as production architecture |
| `blackdwarftech/siphon` | LiveKit-based SIP/WebRTC voice infra shape, worker-based call processing, provider-plugin idea, self-hosted data sovereignty stance | Did not assume its latency/production claims; `MediaRuntime` is an interface with a Mock implementation as default and a LiveKit implementation as an alternate, swappable without touching call/business logic |

Full attribution: `THIRD_PARTY_NOTICES.md`.

## 5. Document map

- `docs/ARCHITECTURE.md` — system/service topology, module boundaries, request flow
- `docs/DATA_MODEL.md` — entity list, ownership/tenancy rules, RLS approach
- `docs/API_DESIGN.md` — REST/SSE surface, conventions, auth
- `docs/VOICE_ARCHITECTURE.md` — real-time pipeline, TurnManager, provider router, latency targets
- `docs/SECURITY_AND_COMPLIANCE.md` — safety gate, consent/suppression, compliance posture
- `docs/IMPLEMENTATION_CHECKLIST.md` — living status tracker, Deep/Medium/Scaffolded per module
- `docs/DECISIONS/*` — ADRs for choices not fully pinned by the spec

## 6. Phase order

Phases 0–10 as defined in `docs/IMPLEMENTATION_CHECKLIST.md`, executed in order, each closed out
with lint/typecheck/test before moving to the next.
