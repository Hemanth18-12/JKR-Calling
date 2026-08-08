"""Automatic audit logging for every successful mutating request — a single
ASGI middleware, not per-route calls (docs/SECURITY_AND_COMPLIANCE.md §9:
"via a shared decorator/dependency, not ad hoc per-route calls").

**Known, deliberate scope boundary**: only workspace-scoped actions (every
mutating route in this codebase takes `?workspace_id=`) are logged. Platform-
level actions (signup, login, workspace creation itself) are not, because
`audit_logs.workspace_id` is RLS-protected by the same `tenant_isolation`
policy as every other tenant table (see the `cc55370bda3d` migration) —
without an explicit `WITH CHECK`, Postgres uses the policy's `USING` clause
for inserts too, so a row with `workspace_id IS NULL` can never satisfy
`workspace_id = current_setting(...)::uuid` (NULL never equals anything,
including itself) under the non-superuser `jkr_app` role every service
connects as. Writing platform-level audit rows would require the superuser
connection reserved for migrations — deliberately not given to ordinary
request handling. Also does not capture per-field before/after diffs (would
require deep coupling to every module's ORM state); captures who did what to
which resource, which is what most audit consumption actually needs.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request, Response
from jkr_db.models.audit import AuditLog
from jkr_db.models.identity import Session as SessionModel
from jkr_db.session import get_session, workspace_scoped_session
from sqlalchemy import select

from app.config import get_settings
from app.security import hash_session_token

logger = logging.getLogger("jkr.audit")

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _resource_type_and_id(path: str) -> tuple[str, str | None]:
    segments = [s for s in path.split("/") if s]
    # segments[0:2] are always "api", "v1".
    resource_type = segments[2] if len(segments) > 2 else "unknown"
    resource_id = None
    for segment in segments[3:]:
        try:
            uuid.UUID(segment)
        except ValueError:
            continue
        resource_id = segment
        break
    return resource_type, resource_id


async def _resolve_actor_user_id(request: Request) -> uuid.UUID | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    token_hash = hash_session_token(token)
    async with get_session() as db:
        result = await db.execute(select(SessionModel.user_id).where(SessionModel.token_hash == token_hash))
        return result.scalar_one_or_none()


async def audit_log_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)

    if request.method not in _MUTATING_METHODS or not (200 <= response.status_code < 300):
        return response

    workspace_id_raw = request.query_params.get("workspace_id")
    if not workspace_id_raw:
        return response
    try:
        workspace_id = uuid.UUID(workspace_id_raw)
    except ValueError:
        return response

    try:
        actor_user_id = await _resolve_actor_user_id(request)
        resource_type, resource_id = _resource_type_and_id(request.url.path)
        client_ip = request.client.host if request.client else None
        request_id = response.headers.get("X-Request-Id")

        async with workspace_scoped_session(workspace_id) as db:
            db.add(
                AuditLog(
                    workspace_id=workspace_id, actor_user_id=actor_user_id,
                    action=f"{request.method} {request.url.path}", resource_type=resource_type,
                    resource_id=resource_id, ip_address=client_ip, request_id=request_id,
                )
            )
    except Exception:
        # Audit logging must never break the primary action it's observing.
        logger.exception("Failed to write audit log for %s %s", request.method, request.url.path)

    return response
