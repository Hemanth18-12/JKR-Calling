"""Demo data seeder — spec §32/§33. Creates three fictional workspaces so the
demo flow is walkable immediately after `make seed` without first clicking
through Agent Studio/Knowledge/Campaigns by hand: each workspace gets a
published agent, approved knowledge, and a couple of consented contacts.
Idempotent — re-running skips any workspace whose slug already exists,
rather than erroring on a unique-constraint violation or duplicating rows.

Run via `make seed` (`uv run --package jkr-db python -m jkr_db.seed`).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, time

from argon2 import PasswordHasher
from sqlalchemy import select

from jkr_db.embeddings import embed_text
from jkr_db.models.agents import (
    Agent,
    AgentTool,
    AgentVersion,
    ConversationPolicy,
    DomainTerm,
    DomainVocabulary,
    ToolDefinition,
    VoicePersona,
)
from jkr_db.models.campaigns import Campaign, CampaignContact, CampaignSchedule
from jkr_db.models.contacts import ConsentEvent, Contact
from jkr_db.models.identity import PasswordCredential, User
from jkr_db.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
from jkr_db.models.providers import ProviderAccount, ProviderHealth
from jkr_db.models.tenancy import Organization, Role, Workspace, WorkspaceMember
from jkr_db.phone import normalize_e164
from jkr_db.session import get_session, workspace_scoped_session

DEMO_PASSWORD = "DemoPassword123!"
_hasher = PasswordHasher()

PROVIDER_KIND_DISPLAY = {
    "telephony": "Mock Telephony (default)", "stt": "Mock STT (default)",
    "llm": "Mock LLM (default)", "tts": "Mock TTS (default)",
}

# Mirrors services/api/app/modules/tools/service.py::TOOL_CATALOG — can't
# import it (services/api depends on packages/db, not the other way around),
# so this is a deliberate, small, documented duplication of reference data.
TOOL_CATALOG: list[tuple[str, str, str, int, bool]] = [
    ("check_calendar_slots", "Look up available appointment slots", "tools:view", 5, False),
    ("book_appointment", "Book a new appointment for the contact", "contacts:edit", 10, True),
    ("reschedule_appointment", "Move an existing appointment to a new time", "contacts:edit", 10, True),
    ("cancel_appointment", "Cancel an existing appointment", "contacts:edit", 10, True),
    ("create_crm_lead", "Create a lead record in the connected CRM", "contacts:edit", 10, False),
    ("update_crm_stage", "Move a CRM lead to a new pipeline stage", "contacts:edit", 10, False),
    ("create_human_callback", "Hand off to a human team member", "calls:transfer", 10, False),
    ("send_whatsapp", "Send a WhatsApp message to the contact", "contacts:edit", 10, False),
    ("send_sms", "Send an SMS to the contact", "contacts:edit", 10, False),
    ("send_email", "Send an email to the contact", "contacts:edit", 10, False),
]


WORKSPACES = [
    {
        "org_name": "Aaha Dental Care",
        "workspace_name": "Aaha Dental Care",
        "slug": "aaha-dental-care",
        "timezone": "Asia/Kolkata",
        "default_language": "te-en-IN",
        "owner_email": "owner@aahadentalcare.demo",
        "owner_name": "Sunitha Rao",
        "agent": {
            "name": "Front Desk Assistant", "business_identity": "Aaha Dental Care",
            "primary_language": "te-en-IN", "primary_objective": "book_appointment",
            "ai_disclosure_text": "నేను Aaha Dental Care తరఫున మాట్లాడుతున్న AI assistant ని.",
            "greeting_text": "నమస్కారం {name} గారు, నేను Aaha Dental Care తరఫున మాట్లాడుతున్న AI assistant ని. మీ అపాయింట్‌మెంట్ గురించి ఒక నిమిషం మాట్లాడొచ్చా?",
            "closing_text": "మీ అపాయింట్‌మెంట్ వివరాలు నోట్ చేసుకున్నాను అండి, మా టీమ్ confirm చేసి మీకు తెలియజేస్తుంది. ధన్యవాదాలు!",
        },
        "knowledge": {
            "title": "Aaha Dental Care — Pricing & Hours FAQ",
            "text": (
                "Root canal treatment costs between 3000 and 8000 rupees depending on the tooth affected. "
                "Teeth cleaning and scaling costs 800 rupees. "
                "We are open Monday to Saturday, 9 AM to 8 PM, and closed on Sundays. "
                "For dental emergencies outside working hours, call our emergency line at 9876543210. "
                "We accept walk-ins but appointments are recommended to avoid waiting."
            ),
        },
        "domain_vocabulary": {
            "name": "Dental Procedures",
            "description": "Common dental procedure/treatment terms, including known STT mis-transcriptions from real calls.",
            "attach": True,
            "terms": [
                {
                    "canonical": "root canal treatment", "category": "procedure", "criticality": "critical",
                    "languages": ["te", "en"],
                    # "ఫ్రూట్ కెనాల్స్"/"fruit canals" is the literal
                    # mis-transcription from real call
                    # 1482f303-3dc9-4fa2-b32c-83f43f24d7c0 — seeded as a
                    # known alias, the direct fix for that bug.
                    "aliases": ["ఫ్రూట్ కెనాల్స్", "ఫ్రూట్ కెనాల్", "fruit canal", "fruit canals", "RCT", "root kenal"],
                },
                {
                    "canonical": "teeth cleaning and scaling", "category": "procedure", "criticality": "standard",
                    "languages": ["te", "en"], "aliases": ["scaling", "cleaning", "టీత్ క్లీనింగ్"],
                },
                {
                    "canonical": "filling", "category": "procedure", "criticality": "standard",
                    "languages": ["te", "en"], "aliases": ["dental filling", "ఫిల్లింగ్"],
                },
                {
                    "canonical": "extraction", "category": "procedure", "criticality": "critical",
                    "languages": ["te", "en"], "aliases": ["tooth extraction", "పన్ను తీయడం", "extract"],
                },
            ],
        },
        "contacts": [
            {"name": "Ravi Kumar", "phone": "9876500101"},
            {"name": "Lakshmi Devi", "phone": "9876500102"},
        ],
        "campaign_objective": "book_appointment",
    },
    {
        "org_name": "Adarsh Educational Institutions",
        "workspace_name": "Adarsh Educational Institutions",
        "slug": "adarsh-educational-institutions",
        "timezone": "Asia/Kolkata",
        "default_language": "hi-en-IN",
        "owner_email": "owner@adarshedu.demo",
        "owner_name": "Vikram Adarsh",
        "agent": {
            "name": "Admissions Counsellor", "business_identity": "Adarsh Educational Institutions",
            "primary_language": "hi-en-IN", "primary_objective": "qualify_lead",
            "ai_disclosure_text": "मैं Adarsh Educational Institutions की तरफ से बात कर रहा AI assistant हूँ।",
            "greeting_text": "नमस्ते {name} जी, मैं Adarsh Educational Institutions की तरफ से बात कर रहा AI assistant हूँ। आपकी admission enquiry के बारे में एक मिनट बात कर सकता हूँ?",
            "closing_text": "धन्यवाद, मैंने आपकी जानकारी नोट कर ली है। हमारी counselling team जल्द ही आपसे संपर्क करेगी।",
        },
        "knowledge": {
            "title": "Adarsh Educational Institutions — Admissions FAQ",
            "text": (
                "Annual fees for the undergraduate program range from 60000 to 120000 rupees depending on the course. "
                "Admission applications for the new academic year open in April and close in June. "
                "The campus is located in Hyderabad with hostel facilities available for outstation students. "
                "Merit scholarships covering up to 50 percent of fees are available for students scoring above 90 percent in qualifying exams. "
                "Admission office hours are Monday to Saturday, 9 AM to 5 PM."
            ),
        },
        "domain_vocabulary": {
            "name": "Admissions & Programs",
            "description": "Admissions and academic program terminology for enquiry qualification.",
            "attach": True,
            "terms": [
                {
                    "canonical": "merit scholarship", "category": "admissions", "criticality": "critical",
                    "languages": ["hi", "en"], "aliases": ["scholarship", "मेरिट स्कॉलरशिप", "merit scholorship"],
                },
                {
                    "canonical": "undergraduate program", "category": "academics", "criticality": "standard",
                    "languages": ["hi", "en"], "aliases": ["UG program", "undergraduate course", "अंडरग्रेजुएट"],
                },
                {
                    "canonical": "hostel facility", "category": "campus", "criticality": "standard",
                    "languages": ["hi", "en"], "aliases": ["hostel", "छात्रावास", "hostel facilities"],
                },
                {
                    "canonical": "entrance exam", "category": "admissions", "criticality": "critical",
                    "languages": ["hi", "en"], "aliases": ["entrance test", "प्रवेश परीक्षा", "qualifying exam"],
                },
            ],
        },
        "contacts": [
            {"name": "Suresh Reddy", "phone": "9876500201"},
            {"name": "Priya Sharma", "phone": "9876500202"},
        ],
        "campaign_objective": "qualify_lead",
    },
    {
        "org_name": "JKR Creatives",
        "workspace_name": "JKR Creatives",
        "slug": "jkr-creatives",
        "timezone": "Asia/Kolkata",
        "default_language": "en-IN",
        "owner_email": "owner@jkrcreatives.demo",
        "owner_name": "Jyothi Rao",
        "agent": {
            "name": "Client Success Coordinator", "business_identity": "JKR Creatives",
            "primary_language": "en-IN", "primary_objective": "collect_feedback",
            "ai_disclosure_text": "I'm an AI assistant calling on behalf of JKR Creatives.",
            "greeting_text": "Hi {name}, this is an AI assistant calling on behalf of JKR Creatives. Do you have a minute to share feedback on your recent project with us?",
            "closing_text": "Thank you so much for your feedback — I've noted it down and our team will follow up if needed.",
        },
        "knowledge": {
            "title": "JKR Creatives — Services & Pricing FAQ",
            "text": (
                "JKR Creatives offers branding, social media management, and video production packages. "
                "Branding packages start at 25000 rupees, social media management starts at 15000 rupees per month. "
                "Typical project turnaround is 2 to 4 weeks depending on scope. "
                "New client enquiries can book a discovery call through our website or by calling the studio directly. "
                "Studio hours are Monday to Friday, 10 AM to 7 PM."
            ),
        },
        # Real estate is not JKR Creatives' business — this vocabulary is
        # seeded under its workspace_id (every DomainVocabulary is
        # workspace-scoped) but deliberately left unattached to any seeded
        # agent (`"attach": False`), to prove the schema generalizes to a
        # third, unrelated domain without forcing an artificial fit onto one
        # of the two already-attached use cases.
        "domain_vocabulary": {
            "name": "Real Estate Listings",
            "description": "Real estate terminology — proves domain vocabularies generalize beyond dental/education; not assigned to any seeded agent.",
            "attach": False,
            "terms": [
                {
                    "canonical": "RERA registration", "category": "compliance", "criticality": "critical",
                    "languages": ["en"], "aliases": ["RERA number", "RERA reg", "rera registeration"],
                },
                {
                    "canonical": "carpet area", "category": "specification", "criticality": "standard",
                    "languages": ["en"], "aliases": ["carpet area sqft", "usable area"],
                },
                {
                    "canonical": "possession date", "category": "timeline", "criticality": "critical",
                    "languages": ["en"], "aliases": ["handover date", "possession", "possesion date"],
                },
                {
                    "canonical": "sale deed", "category": "legal", "criticality": "critical",
                    "languages": ["en"], "aliases": ["sale agreement", "saledeed"],
                },
            ],
        },
        "contacts": [
            {"name": "Arjun Mehta", "phone": "9876500301"},
            {"name": "Kavya Iyer", "phone": "9876500302"},
        ],
        "campaign_objective": "collect_feedback",
    },
]


async def _seed_workspace(spec: dict) -> None:
    async with get_session() as db:
        existing = await db.execute(select(Workspace).where(Workspace.slug == spec["slug"]))
        if existing.scalar_one_or_none() is not None:
            print(f"  [skip] {spec['workspace_name']} already seeded")
            return

        org = Organization(name=spec["org_name"])
        db.add(org)
        await db.flush()

        workspace = Workspace(
            organization_id=org.id, name=spec["workspace_name"], slug=spec["slug"],
            timezone=spec["timezone"], default_language=spec["default_language"],
            calling_window_start=time(9, 0), calling_window_end=time(20, 0), is_demo=True,
        )
        db.add(workspace)
        await db.flush()

        user_result = await db.execute(select(User).where(User.email == spec["owner_email"]))
        owner = user_result.scalar_one_or_none()
        if owner is None:
            owner = User(email=spec["owner_email"], full_name=spec["owner_name"])
            db.add(owner)
            await db.flush()
            db.add(PasswordCredential(user_id=owner.id, password_hash=_hasher.hash(DEMO_PASSWORD)))

        owner_role_result = await db.execute(select(Role).where(Role.key == "workspace_owner"))
        owner_role = owner_role_result.scalar_one()

        workspace_id = workspace.id
        owner_id = owner.id

    # Everything below is workspace-owned — needs app.current_workspace_id
    # set for RLS (docs/DECISIONS/0004-tenant-isolation.md). workspace_members
    # also needs this session's workspace_id to satisfy its dual-condition
    # policy's `workspace_id = current_workspace_id` branch.
    async with workspace_scoped_session(workspace_id) as db:
        db.add(
            WorkspaceMember(
                workspace_id=workspace_id, user_id=owner_id, role_id=owner_role.id,
                status="active", joined_at=datetime.now(UTC),
            )
        )

        for kind, display_name in PROVIDER_KIND_DISPLAY.items():
            account = ProviderAccount(
                workspace_id=workspace_id, kind=kind, name="mock", display_name=display_name,
                is_default=True, priority=0, status="healthy",
            )
            db.add(account)
            await db.flush()
            db.add(
                ProviderHealth(
                    workspace_id=workspace_id, provider_account_id=account.id, status="healthy",
                    latency_p50_ms=0, latency_p95_ms=0, error_rate=0.0, checked_at=datetime.now(UTC),
                    details={"note": "mock provider — always healthy"},
                )
            )

        tool_definitions: dict[str, uuid.UUID] = {}
        for name, description, required_permission, timeout_seconds, confirmation_required in TOOL_CATALOG:
            definition = ToolDefinition(
                workspace_id=workspace_id, name=name, description=description,
                required_permission=required_permission, timeout_seconds=timeout_seconds,
                confirmation_required=confirmation_required, is_enabled=True,
            )
            db.add(definition)
            await db.flush()
            tool_definitions[name] = definition.id

        agent_spec = spec["agent"]
        agent = Agent(
            workspace_id=workspace_id, name=agent_spec["name"], business_identity=agent_spec["business_identity"],
            primary_language=agent_spec["primary_language"], persona_template="seed_demo", status="draft",
        )
        db.add(agent)
        await db.flush()

        version = AgentVersion(
            workspace_id=workspace_id, agent_id=agent.id, version_number=1, status="draft",
            primary_objective=agent_spec["primary_objective"], ai_disclosure_text=agent_spec["ai_disclosure_text"],
            greeting_text=agent_spec["greeting_text"], closing_text=agent_spec["closing_text"],
            personality="warm_receptionist", formality="warm", energy="medium", response_length="short",
            supported_languages=[agent_spec["primary_language"]], created_by=owner_id,
        )
        db.add(version)
        await db.flush()

        db.add(VoicePersona(workspace_id=workspace_id, agent_version_id=version.id, language=agent_spec["primary_language"]))
        db.add(ConversationPolicy(workspace_id=workspace_id, agent_version_id=version.id))
        for tool_id in tool_definitions.values():
            db.add(AgentTool(workspace_id=workspace_id, agent_version_id=version.id, tool_definition_id=tool_id, enabled=True))

        # Publish immediately — spec §33's demo flow assumes a ready-to-call agent.
        version.status = "published"
        version.published_at = datetime.now(UTC)
        agent.status = "active"
        agent.published_version_id = version.id
        await db.flush()

        domain_vocab_spec = spec.get("domain_vocabulary")
        if domain_vocab_spec is not None:
            vocabulary = DomainVocabulary(
                workspace_id=workspace_id, name=domain_vocab_spec["name"], description=domain_vocab_spec["description"],
            )
            db.add(vocabulary)
            await db.flush()
            for term_spec in domain_vocab_spec["terms"]:
                db.add(
                    DomainTerm(
                        workspace_id=workspace_id, vocabulary_id=vocabulary.id, canonical=term_spec["canonical"],
                        aliases=term_spec["aliases"], category=term_spec["category"],
                        criticality=term_spec["criticality"], languages=term_spec["languages"],
                    )
                )
            if domain_vocab_spec["attach"]:
                agent.domain_vocabulary_id = vocabulary.id
            await db.flush()

        knowledge_spec = spec["knowledge"]
        document = KnowledgeDocument(
            workspace_id=workspace_id, source_type="manual_faq", title=knowledge_spec["title"],
            approval_state="approved", language=spec["default_language"],
        )
        db.add(document)
        await db.flush()

        doc_version = KnowledgeDocumentVersion(
            workspace_id=workspace_id, document_id=document.id, version_number=1,
            raw_text=knowledge_spec["text"], processed_at=datetime.now(UTC), created_by=owner_id,
        )
        db.add(doc_version)
        await db.flush()
        document.current_version_id = doc_version.id

        # Paragraph-per-chunk, same granularity knowledge/service.py's real
        # ingestion produces — each sentence-cluster becomes one chunk.
        chunks = [c.strip() for c in knowledge_spec["text"].split(". ") if c.strip()]
        for index, chunk_text in enumerate(chunks):
            text_with_period = chunk_text if chunk_text.endswith(".") else chunk_text + "."
            embedding = await embed_text(text_with_period)
            db.add(
                KnowledgeChunk(
                    workspace_id=workspace_id, document_id=document.id, document_version_id=doc_version.id,
                    chunk_index=index, text=text_with_period, embedding=embedding, approval_state="approved",
                    language=spec["default_language"],
                )
            )

        contact_ids = []
        for contact_spec in spec["contacts"]:
            contact = Contact(
                workspace_id=workspace_id, full_name=contact_spec["name"],
                phone_e164=normalize_e164(contact_spec["phone"]), lead_source="seed_demo", consent_status="granted",
            )
            db.add(contact)
            await db.flush()
            db.add(
                ConsentEvent(
                    workspace_id=workspace_id, contact_id=contact.id, purpose="marketing", source="verbal_recorded",
                    granted_at=datetime.now(UTC),
                )
            )
            contact_ids.append(contact.id)

        campaign = Campaign(
            workspace_id=workspace_id, name=f"{spec['workspace_name']} — Demo Campaign",
            objective=spec["campaign_objective"], agent_id=agent.id, agent_version_id=version.id,
            status="draft", mode="dry_run", max_attempts=3, retry_policy={"backoff_minutes": [30, 120, 480]},
            created_by=owner_id,
        )
        db.add(campaign)
        await db.flush()
        db.add(
            CampaignSchedule(
                workspace_id=workspace_id, campaign_id=campaign.id, calling_window_start=time(9, 0),
                calling_window_end=time(20, 0), days_of_week=[0, 1, 2, 3, 4, 5], timezone=spec["timezone"],
            )
        )
        for contact_id in contact_ids:
            db.add(CampaignContact(workspace_id=workspace_id, campaign_id=campaign.id, contact_id=contact_id, status="pending"))

    print(f"  [ok]   {spec['workspace_name']} ({spec['slug']}) — login as {spec['owner_email']} / {DEMO_PASSWORD}")


async def main() -> None:
    print(f"Seeding {len(WORKSPACES)} demo workspaces...")
    for spec in WORKSPACES:
        await _seed_workspace(spec)
    print("Done. All demo users share the password:", DEMO_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
