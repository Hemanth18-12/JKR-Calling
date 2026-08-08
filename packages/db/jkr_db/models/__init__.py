"""Import every model module so Base.metadata is fully populated before Alembic
autogenerate or create_all runs. Import order does not need to respect FK
dependencies — SQLAlchemy resolves ForeignKey('table.column') strings lazily at
mapper-configuration time, and Alembic/create_all topologically sort CREATE
TABLE statements from the resulting metadata."""

from jkr_db.models import (  # noqa: F401
    agents,
    audit,
    billing,
    calls,
    campaigns,
    contacts,
    experiments,
    identity,
    integrations,
    knowledge,
    providers,
    tenancy,
    tools,
)

__all__ = [
    "agents",
    "audit",
    "billing",
    "calls",
    "campaigns",
    "contacts",
    "experiments",
    "identity",
    "integrations",
    "knowledge",
    "providers",
    "tenancy",
    "tools",
]
