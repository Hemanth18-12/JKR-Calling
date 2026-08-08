# ADR-0007: Deep-vertical-slice scope for this build pass

## Status
Accepted

## Context
The master spec describes a multi-month, multi-engineer platform (80+ tables, 5 services, ~100
frontend routes). A single build pass cannot deliver all of it at full production depth. Two
strategies were presented to the project owner: (a) deep vertical slice — real, tested,
end-to-end logic for the core product loop, full schema everywhere, scaffolds for the long tail;
(b) broad-shallow — minimal CRUD everywhere, no advanced logic anywhere. Owner chose (a).

## Decision
Full real logic this pass: identity/auth/RBAC, tenancy, agent studio, provider abstraction +
mock adapters + router, contacts/consent/suppression, campaign engine incl. safety gate +
dry-run + dialer loop + retries, knowledge ingestion + pgvector RAG + approval workflow, tool
framework, call sessions + TurnManager + live console + call detail, post-call intelligence
pipeline, core analytics, compliance pages.

Real CRUD + basic logic, less UI depth: experiments, billing/usage, integrations (generic
webhook + mock CRM fully working; OAuth-requiring integrations stubbed behind TODO env vars).

Schema + route + minimal UI only, explicitly marked as such in
`docs/IMPLEMENTATION_CHECKLIST.md`: platform admin section, voice benchmark lab, some long-tail
settings pages.

The full §24 table list is implemented as real schema (not partial) regardless of which tier its
business logic lands in, since every later phase depends on the schema being complete and
correct.

## Consequences
`docs/IMPLEMENTATION_CHECKLIST.md` must never claim a Scaffolded item as Done — it carries an
explicit tier marker (Deep/Medium/Scaffolded) per area so a future pass (or a reader) can trust
the checklist rather than needing to re-audit the code to find out what's real.
