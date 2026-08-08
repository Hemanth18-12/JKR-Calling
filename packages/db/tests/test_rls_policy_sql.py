"""Static guard against the empty-string-GUC regression documented in
docs/DECISIONS/0004-tenant-isolation.md: every RLS policy this codebase
creates must wrap `current_setting(...)` in `NULLIF(..., '')` before casting
to uuid, or a reused pooled connection can crash a query outright (cast
error) instead of harmlessly excluding rows. A bare
`current_setting(...)::uuid` with no NULLIF is a real, live bug, not a style
nit — see the ADR for the reproduction."""

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"

# Matches current_setting('app.xxx', true)::uuid that is NOT preceded by NULLIF(
UNGUARDED_CAST = re.compile(r"(?<!NULLIF\()current_setting\('app\.[a-z_]+',\s*true\)::uuid", re.IGNORECASE)


def test_no_unguarded_current_setting_uuid_casts_in_migrations():
    offenders = []
    for path in MIGRATIONS_DIR.glob("*.py"):
        text = path.read_text()
        for match in UNGUARDED_CAST.finditer(text):
            offenders.append(f"{path.name}: {match.group(0)}")
    assert not offenders, (
        "Found current_setting(...)::uuid cast(s) not wrapped in NULLIF(..., '') — "
        f"see docs/DECISIONS/0004-tenant-isolation.md: {offenders}"
    )


def test_rls_migration_uses_nullif_guard():
    rls_migration = MIGRATIONS_DIR / "cc55370bda3d_app_role_and_row_level_security.py"
    content = rls_migration.read_text()
    assert "NULLIF(current_setting('app.current_workspace_id', true), '')" in content
    assert "NULLIF(current_setting('app.current_user_id', true), '')" in content
