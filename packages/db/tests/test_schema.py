from jkr_db.base import Base
from jkr_db.models import *  # noqa: F401,F403 populate metadata


def test_metadata_has_every_master_spec_table():
    expected = {
        "users", "sessions", "password_credentials", "oauth_identities",
        "organizations", "workspaces", "workspace_members", "roles", "permissions", "role_permissions",
        "agents", "agent_versions", "voice_personas", "pronunciation_entries",
        "conversation_policies", "tool_definitions", "agent_tools",
        "phone_numbers", "provider_accounts", "provider_credentials", "provider_health",
        "contacts", "contact_fields", "contact_tags", "segments", "segment_members",
        "consent_events", "suppression_entries",
        "campaigns", "campaign_versions", "campaign_contacts", "campaign_schedules",
        "campaign_attempts", "retry_jobs",
        "call_sessions", "call_participants", "call_turns", "call_events", "call_recordings",
        "call_transcripts", "call_latency_metrics", "interruption_events", "call_outcomes",
        "extracted_fields", "call_summaries", "quality_evaluations",
        "knowledge_collections", "knowledge_documents", "knowledge_document_versions",
        "knowledge_chunks", "knowledge_reviews", "retrieval_events",
        "tool_executions", "appointments", "human_handoffs", "follow_up_tasks", "messages",
        "integrations", "integration_credentials", "webhook_endpoints", "webhook_deliveries",
        "experiments", "experiment_variants", "experiment_assignments", "conversion_events",
        "revenue_events",
        "usage_events", "provider_costs", "invoices", "subscription_plans",
        "audit_logs", "security_events", "feature_flags",
    }
    actual = set(Base.metadata.tables.keys())
    missing = expected - actual
    assert not missing, f"Missing tables from master spec §24: {sorted(missing)}"


def test_every_table_with_workspace_id_has_an_index():
    for table in Base.metadata.tables.values():
        if "workspace_id" not in table.columns:
            continue
        indexed_columns = {col.name for idx in table.indexes for col in idx.columns}
        assert "workspace_id" in indexed_columns, (
            f"{table.name}.workspace_id has no index — RLS lookups on it will be slow"
        )
