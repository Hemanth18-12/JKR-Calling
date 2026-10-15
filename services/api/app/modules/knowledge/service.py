from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from jkr_conversation.llm_client import get_default_client
from jkr_conversation.rag import search_knowledge_with_timing
from jkr_db.embeddings import embed_text
from jkr_db.models.knowledge import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeDocumentAgent,
    KnowledgeDocumentVersion,
    KnowledgeReview,
    RetrievalEvent,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.extraction import (
    chunk_text,
    extract_text_from_csv,
    extract_text_from_docx,
    extract_text_from_pdf,
    fetch_website_text,
)


async def create_collection(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str, description: str | None
) -> KnowledgeCollection:
    collection = KnowledgeCollection(workspace_id=workspace_id, name=name, description=description)
    db.add(collection)
    await db.flush()
    return collection


async def list_collections(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    result = await db.execute(select(KnowledgeCollection).where(KnowledgeCollection.workspace_id == workspace_id))
    collections = list(result.scalars().all())
    out = []
    for c in collections:
        count_result = await db.execute(
            select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.collection_id == c.id)
        )
        out.append({"collection": c, "document_count": count_result.scalar_one()})
    return out


async def create_document(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    source_type: str,
    title: str,
    collection_id: uuid.UUID | None = None,
    language: str | None = None,
    scope: str = "workspace",
    agent_ids: list[uuid.UUID] | None = None,
    raw_text: str | None = None,
    source_url: str | None = None,
    file_base64: str | None = None,
) -> KnowledgeDocument:
    extracted_text: str
    resolved_title = title

    if source_type in ("manual_faq", "text"):
        if not raw_text or not raw_text.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "raw_text is required for this source type")
        extracted_text = raw_text
    elif source_type == "website":
        if not source_url:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "source_url is required for website sources")
        fetched_title, extracted_text = await fetch_website_text(source_url)
        resolved_title = title or fetched_title
    elif source_type in ("pdf", "docx", "csv"):
        if not file_base64:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file_base64 is required for this source type")
        try:
            data = base64.b64decode(file_base64)
        except Exception as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file_base64 is not valid base64") from exc
        if source_type == "pdf":
            extracted_text = extract_text_from_pdf(data)
        elif source_type == "docx":
            extracted_text = extract_text_from_docx(data)
        else:
            extracted_text = extract_text_from_csv(data)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported source_type: {source_type}")

    if not extracted_text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No text could be extracted from this source")

    document = KnowledgeDocument(
        workspace_id=workspace_id,
        collection_id=collection_id,
        source_type=source_type,
        title=resolved_title,
        source_url=source_url,
        approval_state="draft",
        scope=scope,
        language=language,
    )
    db.add(document)
    await db.flush()

    if scope == "agent" and agent_ids:
        for aid in agent_ids:
            db.add(KnowledgeDocumentAgent(workspace_id=workspace_id, document_id=document.id, agent_id=aid))
        await db.flush()

    version = KnowledgeDocumentVersion(
        workspace_id=workspace_id,
        document_id=document.id,
        version_number=1,
        raw_text=extracted_text,
    )
    db.add(version)
    await db.flush()
    document.current_version_id = version.id
    await db.flush()
    return document


async def process_document(db: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID) -> KnowledgeDocument:
    """Chunk + embed the current version's text — spec §16's
    semantic chunking -> embedding -> vector storage."""
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if document.current_version_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document has no content version")

    version_result = await db.execute(
        select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == document.current_version_id)
    )
    version = version_result.scalar_one_or_none()
    if version is None or not version.raw_text:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document version has no text to process")

    document.approval_state = "processing"
    await db.flush()

    # Clear any prior chunks for this version (re-processing is idempotent).
    existing_chunks = await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_version_id == version.id))
    for chunk in existing_chunks.scalars().all():
        await db.delete(chunk)
    await db.flush()

    pieces = chunk_text(version.raw_text)
    for index, piece in enumerate(pieces):
        embedding = await embed_text(piece)
        db.add(
            KnowledgeChunk(
                workspace_id=workspace_id,
                document_id=document.id,
                document_version_id=version.id,
                chunk_index=index,
                text=piece,
                embedding=embedding,
                approval_state="draft",
                language=document.language,
            )
        )

    version.processed_at = datetime.now(UTC)
    document.approval_state = "needs_review"
    await db.flush()
    return document


async def list_documents(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID | None = None
) -> list[dict]:
    query = select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id)
    if agent_id is not None:
        agent_subq = (
            select(KnowledgeDocumentAgent.document_id)
            .where(
                KnowledgeDocumentAgent.workspace_id == workspace_id,
                KnowledgeDocumentAgent.agent_id == agent_id,
            )
        )
        query = query.where(
            or_(
                KnowledgeDocument.scope == "workspace",
                KnowledgeDocument.id.in_(agent_subq),
            )
        )

    result = await db.execute(query.order_by(KnowledgeDocument.title))
    documents = list(result.scalars().all())
    out = []
    for d in documents:
        count_result = await db.execute(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.document_id == d.id))
        agent_rows = await db.execute(
            select(KnowledgeDocumentAgent.agent_id).where(
                KnowledgeDocumentAgent.document_id == d.id,
                KnowledgeDocumentAgent.workspace_id == workspace_id,
            )
        )
        assigned_agents = list(agent_rows.scalars().all())
        out.append({
            "document": d,
            "chunk_count": count_result.scalar_one(),
            "agent_ids": assigned_agents,
        })
    return out


async def get_document(db: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID) -> dict:
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    preview = None
    if document.current_version_id:
        version_result = await db.execute(
            select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == document.current_version_id)
        )
        version = version_result.scalar_one_or_none()
        if version and version.raw_text:
            preview = version.raw_text[:1000]

    chunks_result = await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id).order_by(KnowledgeChunk.chunk_index)
    )
    agent_rows = await db.execute(
        select(KnowledgeDocumentAgent.agent_id).where(
            KnowledgeDocumentAgent.document_id == document.id,
            KnowledgeDocumentAgent.workspace_id == workspace_id,
        )
    )
    assigned_agents = list(agent_rows.scalars().all())
    return {
        "document": document,
        "raw_text_preview": preview,
        "chunks": list(chunks_result.scalars().all()),
        "agent_ids": assigned_agents,
    }


async def update_document_agents(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    scope: str,
    agent_ids: list[uuid.UUID],
) -> dict:
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    document.scope = scope
    existing = await db.execute(
        select(KnowledgeDocumentAgent).where(
            KnowledgeDocumentAgent.document_id == document_id,
            KnowledgeDocumentAgent.workspace_id == workspace_id,
        )
    )
    for row in existing.scalars().all():
        await db.delete(row)
    await db.flush()

    if scope == "agent":
        for aid in agent_ids:
            db.add(KnowledgeDocumentAgent(workspace_id=workspace_id, document_id=document.id, agent_id=aid))
        await db.flush()

    return await get_document(db, workspace_id=workspace_id, document_id=document_id)


async def set_review_decision(
    db: AsyncSession, *, workspace_id: uuid.UUID, document_id: uuid.UUID, reviewer_id: uuid.UUID, approve: bool, notes: str | None
) -> KnowledgeDocument:
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.workspace_id == workspace_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if document.approval_state not in ("needs_review", "approved", "rejected", "draft"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Document must be processed before it can be reviewed")

    new_state = "approved" if approve else "rejected"
    document.approval_state = new_state

    chunks_result = await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    for chunk in chunks_result.scalars().all():
        chunk.approval_state = new_state

    db.add(
        KnowledgeReview(
            workspace_id=workspace_id, document_id=document_id, reviewer_id=reviewer_id,
            decision=new_state, notes=notes, reviewed_at=datetime.now(UTC),
        )
    )
    await db.flush()
    return document


def calculate_health_score(answers: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    """Calculates completion health score (0-100), missing fields, and actionable suggestions."""
    score = 0
    missing: list[str] = []
    suggestions: list[str] = []

    # 1. Identity & Business overview (15 pts)
    if answers.get("business_name") and (answers.get("what_we_offer") or answers.get("business_overview")):
        score += 15
    else:
        missing.append("Business name & overview")
        suggestions.append("Add your business name and overview so customers understand what you offer")

    # 2. Location & Maps (15 pts)
    has_city = bool(answers.get("city") or answers.get("location_city"))
    has_addr = bool(answers.get("full_address") or answers.get("location_address"))
    has_landmark = bool(answers.get("landmark"))
    if has_city and has_addr:
        score += 12
        if has_landmark or answers.get("google_maps_url"):
            score += 3
        else:
            suggestions.append("Add a landmark or Google Maps link for easy customer directions")
    else:
        missing.append("Complete address & location")
        suggestions.append("Add your physical address and city so callers can locate you")

    # 3. Hours & working days (10 pts)
    if answers.get("working_days_and_hours") or answers.get("hours"):
        score += 10
    else:
        missing.append("Working days & operating hours")
        suggestions.append("Specify working hours so the agent knows when you are open")

    # 4. Products / Services & Pricing (20 pts)
    prods = answers.get("top_products_or_services") or answers.get("products") or []
    if isinstance(prods, list) and len(prods) >= 1:
        score += 20 if len(prods) >= 3 else 12
    elif isinstance(prods, str) and len(prods.strip()) > 10:
        score += 15
    else:
        missing.append("Products or services with pricing")
        suggestions.append("List at least 3-5 core products/services with prices or price ranges")

    # 5. Offers, Discounts & Payment Methods (10 pts)
    has_pay = bool(answers.get("payment_methods"))
    has_offers = bool(answers.get("offers_and_discounts") or answers.get("offers"))
    if has_pay:
        score += 6
        if has_offers:
            score += 4
    else:
        missing.append("Payment methods (UPI, Cards, COD)")
        suggestions.append("Specify payment methods like UPI, Cash, or Cards")

    # 6. Delivery, Returns & Policies (15 pts)
    has_deliv = bool(answers.get("delivery_and_shipping") or answers.get("service_area"))
    has_returns = bool(answers.get("returns_refunds_cancellation") or answers.get("return_policy"))
    if has_deliv and has_returns:
        score += 15
    elif has_deliv or has_returns:
        score += 8
        if not has_returns:
            missing.append("Returns, refunds & cancellation policy")
            suggestions.append("Add your return/refund policy to handle dispute inquiries")
    else:
        missing.append("Delivery & Return/Refund policies")
        suggestions.append("Add your delivery coverage and return/cancellation policy")

    # 7. FAQs (10 pts)
    faqs = answers.get("customer_faqs") or answers.get("faqs") or []
    if isinstance(faqs, list) and len(faqs) >= 2:
        score += 10
    elif isinstance(faqs, str) and len(faqs.strip()) > 15:
        score += 8
    else:
        missing.append("Top customer questions & answers")
        suggestions.append("Add at least 3 common customer questions to increase first-call resolution")

    # 8. Guardrails & Escalation (10 pts)
    has_guard = bool(answers.get("guardrails") or answers.get("never_promise"))
    has_esc = bool(answers.get("human_escalation") or answers.get("handoff_person"))
    if has_guard and has_esc:
        score += 10
    elif has_guard or has_esc:
        score += 5
    else:
        missing.append("Guardrails (what AI must never say)")
        suggestions.append("Set guardrails on what the AI must never promise or advise")

    return min(100, score), missing, suggestions


def _build_deterministic_markdown(
    business_name: str,
    business_type: str,
    agent_category: str,
    language: str,
    answers: dict[str, Any],
) -> str:
    """Deterministic fallback to compile structured knowledge text without hallucinations."""
    b_name = business_name or answers.get("business_name") or "Business"
    overview = answers.get("what_we_offer") or answers.get("business_overview") or "**Not provided**"
    city = answers.get("city") or answers.get("location_city") or "**Not provided**"
    state = answers.get("state") or answers.get("location_state") or "**Not provided**"
    address = answers.get("full_address") or answers.get("location_address") or "**Not provided**"
    landmark = answers.get("landmark") or "**Not provided**"
    maps_url = answers.get("google_maps_url") or "**Not provided**"
    service_area = answers.get("service_area") or "**Not provided**"
    hours = answers.get("working_days_and_hours") or answers.get("hours") or "**Not provided**"
    phone = answers.get("phone") or answers.get("phone_number") or "**Not provided**"
    whatsapp = answers.get("whatsapp") or "**Not provided**"
    email = answers.get("email") or "**Not provided**"
    team_languages = answers.get("team_languages") or "English, Telugu, Hindi"

    prods = answers.get("top_products_or_services") or answers.get("products")
    offers = answers.get("offers_and_discounts") or answers.get("offers") or "**Not provided**"
    payments = answers.get("payment_methods") or "**Not provided**"
    delivery = answers.get("delivery_and_shipping") or "**Not provided**"
    returns = answers.get("returns_refunds_cancellation") or answers.get("return_policy") or "**Not provided**"
    diff = answers.get("why_choose_us") or answers.get("differentiators") or "**Not provided**"
    faqs = answers.get("customer_faqs") or answers.get("faqs")
    guardrails = answers.get("guardrails") or answers.get("never_promise") or "Do not provide unauthorized medical/financial advice. Never invent prices or offer unapproved discounts."
    escalation = answers.get("human_escalation") or answers.get("handoff_person") or "Transfer to store manager if customer has unresolved complaints or asks for a human."

    prod_lines = []
    if isinstance(prods, list):
        for p in prods:
            if isinstance(p, dict):
                prod_lines.append(f"- **{p.get('name', 'Product')}**: {p.get('price', 'Price on request')} — {p.get('description', '')}")
            else:
                prod_lines.append(f"- {p}")
    elif prods:
        prod_lines.append(str(prods))
    else:
        prod_lines.append("- **Not provided** (Owner to specify top products and prices)")

    faq_lines = []
    if isinstance(faqs, list):
        for f in faqs:
            if isinstance(f, dict):
                faq_lines.append(f"**Q: {f.get('question', '')}**\nA: {f.get('answer', '')}\n")
            else:
                faq_lines.append(f"- {f}")
    elif faqs:
        faq_lines.append(str(faqs))
    else:
        faq_lines.append("- **Not provided**")

    # Category specifics
    category_section = ""
    if agent_category == "appointment_booking":
        slots = answers.get("available_slots") or "**Not provided**"
        booking_rules = answers.get("booking_rules") or "**Not provided**"
        reschedule = answers.get("rescheduling_no_show_policy") or "**Not provided**"
        staff = answers.get("doctor_or_staff_names") or "**Not provided**"
        category_section = f"""## 6. Appointment Booking Details
- **Available Slots & Timings**: {slots}
- **Booking Rules & Advance Notice**: {booking_rules}
- **Rescheduling & Cancellation**: {reschedule}
- **Doctors / Specialists / Staff**: {staff}
"""
    elif agent_category == "lead_qualification":
        ideal = answers.get("ideal_customer") or "**Not provided**"
        budget = answers.get("budget_range") or "**Not provided**"
        hot = answers.get("hot_lead_criteria") or "**Not provided**"
        category_section = f"""## 6. Lead Qualification Criteria
- **Ideal Customer Profile**: {ideal}
- **Target Budget Range**: {budget}
- **Hot Lead Threshold**: {hot}
"""
    elif agent_category == "customer_support":
        issues = answers.get("common_issues_and_fixes") or "**Not provided**"
        warranty = answers.get("warranty_terms") or "**Not provided**"
        category_section = f"""## 6. Support & Warranty Protocols
- **Common Issues & Resolutions**: {issues}
- **Warranty Terms**: {warranty}
"""
    elif agent_category == "collections":
        due_rules = answers.get("due_date_rules") or "**Not provided**"
        late_fee = answers.get("late_fee_policy") or "**Not provided**"
        category_section = f"""## 6. Payment & Collections Policies
- **Due Date Rules**: {due_rules}
- **Late Fee / Settlement Policy**: {late_fee}
"""
    elif agent_category == "feedback":
        rating_scale = answers.get("rating_scale") or "1 to 5 stars"
        neg = answers.get("negative_feedback_protocol") or "Apologize politely and offer immediate manager callback"
        category_section = f"""## 6. Customer Feedback Protocol
- **Rating Scale**: {rating_scale}
- **Negative Feedback Action**: {neg}
"""

    return f"""# {b_name} — Business Knowledge Base

## 1. Business Overview & Identity
- **Business Name**: {b_name}
- **Category / Industry**: {business_type.replace('_', ' ').title()}
- **What We Offer**: {overview}
- **Languages Spoken by Team**: {team_languages}
- **Why Customers Choose Us**: {diff}

## 2. Location & Operating Hours
- **Full Address**: {address}
- **City & State**: {city}, {state}
- **Landmark**: {landmark}
- **Google Maps Link**: {maps_url}
- **Service Coverage Area**: {service_area}
- **Working Days & Hours**: {hours}

## 3. Products / Services & Pricing
{chr(10).join(prod_lines)}

## 4. Offers, Discounts & Payment Methods
- **Special Offers & Festival Deals**: {offers}
- **Accepted Payment Methods**: {payments}

## 5. Delivery, Shipping & Return Policies
- **Delivery & Shipping Policy**: {delivery}
- **Returns, Refunds & Cancellation**: {returns}

{category_section}
## 7. Frequently Asked Questions
{chr(10).join(faq_lines)}

## 8. Guardrails & Restrictions (What AI Must NEVER Say)
- {guardrails}

## 9. Human Escalation Protocol
- **When to Transfer**: {escalation}
- **Primary Contact**: {phone} | {whatsapp} | {email}
"""


async def generate_knowledge_from_answers(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    business_type: str,
    agent_category: str,
    language: str,
    answers: dict[str, Any],
) -> dict:
    """Builds clean, grounded knowledge text from owner's answers using LLM with deterministic fallback."""
    b_name = answers.get("business_name") or "Business"
    score, missing_fields, suggestions = calculate_health_score(answers)

    deterministic_md = _build_deterministic_markdown(
        business_name=b_name,
        business_type=business_type,
        agent_category=agent_category,
        language=language,
        answers=answers,
    )

    llm = get_default_client()
    generated_text = deterministic_md

    if llm is not None:
        lang_instruction = "English"
        if language in ("te", "telugu"):
            lang_instruction = "Telugu (spoken phone-friendly Telugu script and clear vocabulary)"
        elif language in ("hi", "hindi"):
            lang_instruction = "Hindi (spoken phone-friendly Hindi/Hinglish script and natural vocabulary)"

        system_prompt = (
            f"You are an expert AI knowledge architect for JKR AI Calling. "
            f"Format and polish this business knowledge base in fluent, spoken-friendly {lang_instruction} "
            f"for an AI voice agent on real phone calls.\n"
            f"CRITICAL RULES:\n"
            f"1. Use ONLY the owner's answers provided in the raw draft. NEVER invent or hallucinate prices, addresses, phone numbers, discounts, doctor names, or return policies.\n"
            f"2. Any section or detail missing or marked '**Not provided**' MUST remain explicitly marked as '**Not provided**'.\n"
            f"3. Keep the Markdown section headings intact: 1. Business Overview, 2. Location & Operating Hours, 3. Products/Services & Pricing, 4. Offers & Payment Methods, 5. Delivery & Returns, 6. Category Specifics, 7. FAQs, 8. Guardrails, 9. Escalation.\n"
            f"4. The FAQs must be concise, spoken-style questions and direct 1-2 sentence answers."
        )

        user_prompt = f"Here is the owner's verified input data:\n\n{deterministic_md}\n\nPlease generate the polished {lang_instruction} knowledge document now."

        try:
            llm_result = await llm.complete_text(system=system_prompt, user=user_prompt, max_tokens=2500)
            if llm_result and len(llm_result.strip()) > 100:
                generated_text = llm_result.strip()
        except Exception:
            generated_text = deterministic_md

    title = f"{b_name} Knowledge Base ({language.upper()})"
    return {
        "title": title,
        "generated_text": generated_text,
        "health_score": score,
        "missing_fields": missing_fields,
        "suggestions": suggestions,
    }


async def test_agent_knowledge(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    query: str,
    language: str = "en",
) -> dict:
    """Answers a question directly using scoped approved knowledge chunks."""
    chunks, above_threshold, timing = await search_knowledge_with_timing(
        db, workspace_id=workspace_id, query=query, agent_id=agent_id, top_k=4
    )

    used_scope = "workspace-wide"
    if chunks:
        # Check if top chunk doc has scope == "agent"
        doc_res = await db.execute(
            select(KnowledgeDocument.scope).where(KnowledgeDocument.id == chunks[0].document_id)
        )
        s = doc_res.scalar_one_or_none()
        if s == "agent":
            used_scope = "agent-specific"

    if not above_threshold or not chunks:
        fallback_msg = "I'm sorry, I don't have that information in my approved knowledge base yet."
        if language in ("te", "telugu"):
            fallback_msg = "క్షమించండి, నా దగ్గర ప్రస్తుతం ఆ సమాచారం లేదు. మా టీమ్‌తో మాట్లాడేలా చేస్తాను."
        elif language in ("hi", "hindi"):
            fallback_msg = "माफ़ कीजिए, मेरे पास अभी यह जानकारी उपलब्ध नहीं है। मैं आपको हमारी टीम से कनेक्ट करवा देता हूँ।"

        return {
            "answer": fallback_msg,
            "grounded": False,
            "matched_chunks": [],
            "used_scope": used_scope,
            "latency_ms": {
                "embedding_ms": timing.embedding_ms,
                "vector_search_ms": timing.vector_search_ms,
                "total_ms": timing.total_ms,
            },
        }

    # Answer using matched chunks
    llm = get_default_client()
    context_text = "\n\n".join([f"[{c.document_title}]: {c.text}" for c in chunks[:3]])
    lang_name = "English" if language == "en" else ("Telugu" if language in ("te", "telugu") else "Hindi")

    if llm is not None:
        system_prompt = (
            f"You are a friendly, helpful phone call assistant. Answer the customer's question naturally and concisely "
            f"in 1 to 2 spoken sentences in {lang_name}, strictly using ONLY the approved knowledge excerpts provided below. "
            f"Do not guess, assume, or add anything not mentioned in the context."
        )
        user_prompt = f"Knowledge Context:\n{context_text}\n\nCustomer Question: {query}"
        try:
            spoken_ans = await llm.complete_text(system=system_prompt, user=user_prompt, max_tokens=150)
            if not spoken_ans:
                spoken_ans = chunks[0].text[:200]
        except Exception:
            spoken_ans = chunks[0].text[:200]
    else:
        spoken_ans = chunks[0].text[:200]

    return {
        "answer": spoken_ans,
        "grounded": True,
        "matched_chunks": [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "document_title": c.document_title,
                "text": c.text,
                "score": c.score,
            }
            for c in chunks
        ],
        "used_scope": used_scope,
        "latency_ms": {
            "embedding_ms": timing.embedding_ms,
            "vector_search_ms": timing.vector_search_ms,
            "total_ms": timing.total_ms,
        },
    }


async def list_knowledge_gaps(
    db: AsyncSession, *, workspace_id: uuid.UUID, agent_id: uuid.UUID | None = None
) -> list[dict]:
    """Finds customer queries that could not be answered from approved knowledge."""
    query = (
        select(
            RetrievalEvent.query,
            func.count(RetrievalEvent.id).label("count"),
            func.max(RetrievalEvent.created_at).label("last_asked_at"),
            func.max(RetrievalEvent.id).label("id"),
        )
        .where(
            RetrievalEvent.workspace_id == workspace_id,
            RetrievalEvent.used_in_response == False,  # noqa: E712
        )
        .group_by(RetrievalEvent.query)
        .order_by(func.count(RetrievalEvent.id).desc())
        .limit(20)
    )
    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "id": r.id,
            "query": r.query,
            "count": r.count,
            "last_asked_at": r.last_asked_at,
        }
        for r in rows
    ]
