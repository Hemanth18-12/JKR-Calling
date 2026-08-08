"""Objective definitions — what a call is trying to accomplish, and which
facts it needs along the way. Ported verbatim (same field keys, same
multilingual question wording) from services/voice-worker/app/providers/mock.py's
MOCK_SCRIPTS/CLOSING_BY_OBJECTIVE, which is the pre-existing, authored source
of truth for this content — not rewritten. The `objective` id values here
match AgentVersion.primary_objective exactly (a bare string on that model
today, used as this dict's key both before and after this refactor).

The key behavioral change from the old MOCK_SCRIPTS: previously
`MockLLM.next_question(asked_count)` walked `fields` strictly in list order
via a script cursor. Here, `fields` is a set of candidates for planner.py to
choose from based on what's still missing — order in the list below is only
a *priority tiebreak* (ask earlier-listed fields first when multiple are
equally missing), not a mandatory sequence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    question: dict[str, str]  # {"te": ..., "hi": ..., "en": ...}
    extraction_hint: str  # short English description for the extractor LLM prompt
    required: bool = True


@dataclass(frozen=True)
class ObjectiveDefinition:
    id: str
    fields: list[FieldDefinition]
    closing_text: dict[str, str]  # canned, per-language — safety-net fallback if generation fails
    tool_on_completion: str | None = None


DEFAULT_CLOSING = {
    "te": "ధన్యవాదాలు అండి, మీ వివరాలు నోట్ చేసుకున్నాను. మా టీమ్ మిమ్మల్ని త్వరలో సంప్రదిస్తుంది.",
    "hi": "धन्यवाद, मैंने आपकी जानकारी नोट कर ली है। हमारी टीम जल्द ही आपसे संपर्क करेगी।",
    "en": "Thank you, I've noted that down. Our team will follow up with you shortly.",
}

OBJECTIVES: dict[str, ObjectiveDefinition] = {
    "qualify_and_route": ObjectiveDefinition(
        id="qualify_and_route",
        fields=[
            FieldDefinition(
                key="topic",
                question={
                    "te": "ప్రస్తుతం ఏ విషయంలో సహాయం కావాలి అండి?",
                    "hi": "आपको किस बारे में मदद चाहिए?",
                    "en": "What can I help you with today?",
                },
                extraction_hint="what the customer needs help with, in their own words",
            ),
            FieldDefinition(
                key="preferred_callback_time",
                question={
                    "te": "మీకు ఎప్పుడు కాల్ చేస్తే వీలుగా ఉంటుంది అండి?",
                    "hi": "आपको कब कॉल करना सही रहेगा?",
                    "en": "When would be a good time to call you back?",
                },
                extraction_hint="when it's convenient to call the customer back",
            ),
        ],
        closing_text=DEFAULT_CLOSING,
    ),
    "qualify_lead": ObjectiveDefinition(
        id="qualify_lead",
        fields=[
            FieldDefinition(
                key="interest_detail",
                question={
                    "te": "మీరు దేని గురించి enquiry ఇచ్చారు, కొంచెం చెప్పగలరా అండి?",
                    "hi": "आपने किस बारे में पूछताछ की थी?",
                    "en": "Could you tell me a bit more about what you're looking for?",
                },
                extraction_hint="more detail about what the customer originally enquired about or is interested in",
            ),
            FieldDefinition(
                key="timeline",
                question={
                    "te": "మీరు ఎప్పటికల్లా decision తీసుకోవాలని అనుకుంటున్నారు?",
                    "hi": "आप कब तक निर्णय लेना चाहते हैं?",
                    "en": "What's your timeline for making a decision?",
                },
                extraction_hint="when the customer wants to make a decision or move forward",
            ),
        ],
        closing_text=DEFAULT_CLOSING,
    ),
    "book_appointment": ObjectiveDefinition(
        id="book_appointment",
        fields=[
            FieldDefinition(
                key="reason_for_visit",
                question={
                    "te": "మీకు ఏ సమస్య కోసం అపాయింట్‌మెంట్ కావాలి అండి?",
                    "hi": "आपको अपॉइंटमेंट किस लिए चाहिए?",
                    "en": "What's this appointment for?",
                },
                extraction_hint="what the appointment/visit is for — the treatment, service, or reason",
            ),
            FieldDefinition(
                key="preferred_date",
                question={
                    "te": "మీకు ఏ రోజు వీలుగా ఉంటుంది అండి?",
                    "hi": "आपको कौन सा दिन सही रहेगा?",
                    "en": "Which day works best for you?",
                },
                extraction_hint="which day the customer wants the appointment on",
            ),
            FieldDefinition(
                key="preferred_time",
                question={
                    "te": "ఏ సమయం మీకు వీలుగా ఉంటుంది?",
                    "hi": "कौन सा समय ठीक रहेगा?",
                    "en": "What time works for you?",
                },
                extraction_hint="what time of day the customer wants the appointment",
            ),
        ],
        closing_text={
            "te": "సరే అండి, మీ అపాయింట్‌మెంట్ వివరాలు నోట్ చేసుకున్నాను. మా టీమ్ confirm చేసి మీకు తెలియజేస్తుంది.",
            "hi": "ठीक है, मैंने आपकी अपॉइंटमेंट की जानकारी नोट कर ली है। हमारी टीम कन्फर्म करके आपको बताएगी।",
            "en": "Great, I've noted your appointment details. Our team will confirm and follow up with you.",
        },
        tool_on_completion="book_appointment",
    ),
    "renewal_reminder": ObjectiveDefinition(
        id="renewal_reminder",
        fields=[
            FieldDefinition(
                key="renewal_interest",
                question={
                    "te": "మీరు renewal గురించి ఆలోచించారా అండి?",
                    "hi": "क्या आपने रिन्यूअल के बारे में सोचा है?",
                    "en": "Have you had a chance to think about renewing?",
                },
                extraction_hint="whether the customer wants to renew, or is still deciding",
            ),
            FieldDefinition(
                key="preferred_callback_time",
                question={
                    "te": "మీకు ఎప్పుడు కాల్ చేస్తే వీలుగా ఉంటుంది?",
                    "hi": "आपको कब कॉल करना ठीक रहेगा?",
                    "en": "When's a good time to follow up with you?",
                },
                extraction_hint="when it's convenient to follow up with the customer",
            ),
        ],
        closing_text=DEFAULT_CLOSING,
    ),
    "collect_feedback": ObjectiveDefinition(
        id="collect_feedback",
        fields=[
            FieldDefinition(
                key="satisfaction",
                question={
                    "te": "మీ అనుభవం ఎలా ఉంది అండి?",
                    "hi": "आपका अनुभव कैसा रहा?",
                    "en": "How was your experience with us?",
                },
                extraction_hint="how satisfied the customer was with their experience",
            ),
            FieldDefinition(
                key="improvement_area",
                question={
                    "te": "మేము ఇంకా ఏమి మెరుగుపరచాలి అంటారు?",
                    "hi": "हमें और क्या सुधारना चाहिए?",
                    "en": "Is there anything we could improve?",
                },
                extraction_hint="anything the customer thinks could be improved",
                required=False,
            ),
        ],
        closing_text=DEFAULT_CLOSING,
    ),
}

DEFAULT_OBJECTIVE_ID = "qualify_and_route"


def get_objective(objective_id: str) -> ObjectiveDefinition:
    return OBJECTIVES.get(objective_id, OBJECTIVES[DEFAULT_OBJECTIVE_ID])


def required_field_keys(objective_id: str) -> list[str]:
    return [f.key for f in get_objective(objective_id).fields if f.required]


def all_field_keys(objective_id: str) -> list[str]:
    return [f.key for f in get_objective(objective_id).fields]
