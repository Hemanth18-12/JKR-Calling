"""Wires this service's DATABASE_URL into the environment jkr_db.session
reads from (same pattern as services/api/app/db.py). Session-per-request
handling itself lives directly in main.py's route handlers via
`jkr_db.session.workspace_scoped_session` — voice-worker's routes take
workspace_id from the POST body, not a path param, so the
Depends()-generator pattern services/api uses for path-param-based routes
doesn't apply cleanly here (see the comment in main.py::create_session)."""

from __future__ import annotations

import os

from app.config import get_settings

os.environ["DATABASE_URL"] = get_settings().database_url
