"""Every domain enum used across the schema, as Python StrEnum (mirrored as
Postgres native ENUM types in the Alembic migration)."""

from __future__ import annotations

from enum import StrEnum


class WorkspaceRole(StrEnum):
    PLATFORM_SUPER_ADMIN = "platform_super_admin"
    JKR_ADMIN = "jkr_admin"
    WORKSPACE_OWNER = "workspace_owner"
    WORKSPACE_ADMIN = "workspace_admin"
    CAMPAIGN_MANAGER = "campaign_manager"
    SALES_MANAGER = "sales_manager"
    AGENT_OPERATOR = "agent_operator"
    ANALYST = "analyst"
    VIEWER = "viewer"


class MemberStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class LanguageCode(StrEnum):
    TELUGU = "te-IN"
    HINDI = "hi-IN"
    ENGLISH_IN = "en-IN"
    TELUGU_ENGLISH = "te-en-IN"
    HINDI_ENGLISH = "hi-en-IN"


class AgentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentVersionStatus(StrEnum):
    DRAFT = "draft"
    TESTING = "testing"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ProviderKind(StrEnum):
    TELEPHONY = "telephony"
    STT = "stt"
    LLM = "llm"
    TTS = "tts"


class ProviderName(StrEnum):
    MOCK = "mock"
    TWILIO = "twilio"
    SIP_TRUNK = "sip_trunk"
    EXOTEL = "exotel"
    PLIVO = "plivo"
    TELNYX = "telnyx"
    DEEPGRAM = "deepgram"
    SARVAM_STT = "sarvam_stt"
    GOOGLE_STT = "google_stt"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_LLM = "google_llm"
    LOCAL_LLM = "local_llm"
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"
    SARVAM_TTS = "sarvam_tts"
    OPENAI_TTS = "openai_tts"


class ProviderHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class ConsentSource(StrEnum):
    SIGNED_FORM = "signed_form"
    VERBAL_RECORDED = "verbal_recorded"
    CHECKBOX = "checkbox"
    WHATSAPP_OPT_IN = "whatsapp_opt_in"
    API = "api"


class ConsentPurpose(StrEnum):
    MARKETING = "marketing"
    TRANSACTIONAL = "transactional"
    SERVICE = "service"
    APPOINTMENT_REMINDER = "appointment_reminder"


class SuppressionReason(StrEnum):
    CUSTOMER_OPT_OUT = "customer_opt_out"
    WRONG_NUMBER = "wrong_number"
    LEGAL_SUPPRESSION = "legal_suppression"
    WORKSPACE_BLOCK = "workspace_block"
    COMPLAINT = "complaint"
    REPEATED_FAILURE = "repeated_failure"
    MANUAL_BLOCK = "manual_block"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CampaignMode(StrEnum):
    DRY_RUN = "dry_run"
    LIVE = "live"


class CampaignObjective(StrEnum):
    BOOK_APPOINTMENT = "book_appointment"
    QUALIFY_LEAD = "qualify_lead"
    COLLECT_FEEDBACK = "collect_feedback"
    RENEWAL_REMINDER = "renewal_reminder"
    CUSTOM = "custom"


class CampaignContactStatus(StrEnum):
    PENDING = "pending"
    RESERVED = "reserved"
    DIALING = "dialing"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    HUMAN_REVIEW = "human_review"
    SUPPRESSED = "suppressed"
    CONVERTED = "converted"


class CallDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallStatus(StrEnum):
    QUEUED = "queued"
    DIALING = "dialing"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    TRANSFERRED = "transferred"
    ABANDONED = "abandoned"


class CallEndReason(StrEnum):
    COMPLETED = "completed"
    CUSTOMER_HANGUP = "customer_hangup"
    AGENT_ENDED = "agent_ended"
    TRANSFERRED = "transferred"
    ERROR = "error"
    TIMEOUT = "timeout"
    DO_NOT_CALL = "do_not_call"
    WRONG_NUMBER = "wrong_number"


class SpeakerRole(StrEnum):
    AGENT = "agent"
    CUSTOMER = "customer"
    SYSTEM = "system"
    TOOL = "tool"


class InterruptionClass(StrEnum):
    MEANINGFUL = "meaningful"
    FALSE_POSITIVE = "false_positive"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"


class KnowledgeSourceType(StrEnum):
    WEBSITE = "website"
    SITEMAP = "sitemap"
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"
    CSV = "csv"
    MANUAL_FAQ = "manual_faq"
    PRODUCT_CATALOGUE = "product_catalogue"
    PRICING_SHEET = "pricing_sheet"
    POLICY_DOCUMENT = "policy_document"
    API = "api"


class ApprovalState(StrEnum):
    DRAFT = "draft"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ToolName(StrEnum):
    CHECK_CALENDAR_SLOTS = "check_calendar_slots"
    BOOK_APPOINTMENT = "book_appointment"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"
    CREATE_CRM_LEAD = "create_crm_lead"
    UPDATE_CRM_STAGE = "update_crm_stage"
    CREATE_HUMAN_CALLBACK = "create_human_callback"
    SEND_WHATSAPP = "send_whatsapp"
    SEND_SMS = "send_sms"
    SEND_EMAIL = "send_email"
    SEND_PAYMENT_LINK = "send_payment_link"
    CHECK_ORDER_STATUS = "check_order_status"
    CHECK_APPLICATION_STATUS = "check_application_status"
    CREATE_SUPPORT_TICKET = "create_support_ticket"
    TRANSFER_CALL = "transfer_call"
    ADD_SUPPRESSION_ENTRY = "add_suppression_entry"
    SAVE_CUSTOMER_PREFERENCE = "save_customer_preference"


class ToolExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HandoffReason(StrEnum):
    CUSTOMER_REQUESTED = "customer_requested"
    LOW_CONFIDENCE = "low_confidence"
    HIGH_RISK_TOPIC = "high_risk_topic"
    ANGRY_CUSTOMER = "angry_customer"
    TOOL_FAILURE = "tool_failure"
    INSUFFICIENT_KNOWLEDGE = "insufficient_knowledge"
    BUSINESS_RULE = "business_rule"
    HIGH_VALUE_NEGOTIATION = "high_value_negotiation"


class HandoffStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class FollowUpChannel(StrEnum):
    WHATSAPP = "whatsapp"
    HUMAN_CALLBACK = "human_callback"
    AI_CALLBACK = "ai_callback"
    REMINDER = "reminder"
    CRM_UPDATE = "crm_update"
    CLOSE = "close"
    SUPPRESS = "suppress"


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    SENT = "sent"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class IntegrationType(StrEnum):
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_SHEETS = "google_sheets"
    META_LEAD_ADS = "meta_lead_ads"
    WHATSAPP = "whatsapp"
    CRM = "crm"
    WEBHOOK = "webhook"
    N8N = "n8n"


class IntegrationStatus(StrEnum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"


class WebhookDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class ExperimentVariantType(StrEnum):
    AI_CALLING = "ai_calling"
    HUMAN_CALLING = "human_calling"
    CONTROL_NO_CALL = "control_no_call"
    AGENT_VARIANT = "agent_variant"
    VOICE_VARIANT = "voice_variant"
    OPENING_VARIANT = "opening_variant"
    TIMING_VARIANT = "timing_variant"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LeadScoreBucket(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    NOT_QUALIFIED = "not_qualified"


class CallOutcomeCategory(StrEnum):
    INTERESTED = "interested"
    QUALIFIED = "qualified"
    APPOINTMENT_BOOKED = "appointment_booked"
    CALLBACK_REQUESTED = "callback_requested"
    NOT_INTERESTED = "not_interested"
    WRONG_NUMBER = "wrong_number"
    DO_NOT_CALL = "do_not_call"
    UNREACHABLE = "unreachable"
    NEEDS_HUMAN = "needs_human"


class UsageEventType(StrEnum):
    TELEPHONY_SECONDS = "telephony_seconds"
    STT_SECONDS = "stt_seconds"
    LLM_TOKENS = "llm_tokens"
    TTS_CHARACTERS = "tts_characters"
    LIVEKIT_MINUTES = "livekit_minutes"
    RECORDING_STORAGE_MB = "recording_storage_mb"
    VECTOR_STORAGE_MB = "vector_storage_mb"
    MESSAGES = "messages"
    TOOL_EXECUTIONS = "tool_executions"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class SecurityEventSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RetryReason(StrEnum):
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    CUSTOMER_REQUESTED = "customer_requested"
    PROVIDER_ERROR = "provider_error"
