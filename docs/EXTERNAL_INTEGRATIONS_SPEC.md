# External Integrations Architecture & Specification

This document details the requirements, authentication flows, data schemas, and implementation contracts for the non-core external integrations: **CRM / College ERP**, **Meta Lead Ads**, and **n8n**.

---

## 1. Google Calendar Integration (Completed & Active)

- **Status:** **Fully Implemented & Active**
- **Auth Flow:** OAuth 2.0 (`accounts.google.com/o/oauth2/v2/auth`) with offline refresh token grant.
- **Scopes:** `https://www.googleapis.com/auth/calendar.events`, `https://www.googleapis.com/auth/userinfo.email`.
- **Runtime Hook:** `_run_book_appointment` in `packages/db/jkr_db/tools_engine.py` automatically checks for active workspace Google Calendar token, decrypts credentials, and inserts calendar event via Google Calendar REST API (`POST /v3/calendars/{calendar_id}/events`).
- **Endpoints:**
  - `GET /api/v1/integrations/google-calendar/auth-url`
  - `POST /api/v1/integrations/google-calendar/connect`
  - `POST /api/v1/integrations/google-calendar/disconnect`
  - `GET /api/v1/integrations/google-calendar/status`

---

## 2. CRM / College ERP Integration (Documented Specification)

### Purpose
Synchronize high-intent student admission inquiries, patient consult requests, and lead qualification stages bidirectionally between JKR Calling and the client's existing CRM or ERP (e.g., Salesforce, HubSpot, Zoho CRM, or custom College ERPs like CollPoll / Camu / MasterSoft).

### Authentication & Connection Options
1. **API Key / Secret Token (Most Common for College ERPs):**
   - Workspace config stores: `base_url`, `api_key_encrypted`, `institution_id`.
   - Outbound HTTP header: `Authorization: Bearer <decrypted_key>` or `X-API-Key: <key>`.
2. **OAuth 2.0 (Salesforce / HubSpot / Zoho):**
   - Standard authorization code grant with refresh token.

### Data Contract & Payload Schema
When an AI voice call reaches outcome `appointment_booked`, `qualified`, or `interested`, the post-call intelligence pipeline dispatches a structured lead update:

```json
{
  "event": "lead.qualified",
  "workspace_id": "91b2abf1-9a7b-48d3-ac51-5a1cad458bc7",
  "lead": {
    "external_id": "ERP-2026-90412",
    "first_name": "Ramesh",
    "last_name": "Kumar",
    "phone": "+918019101606",
    "email": "ramesh@example.com",
    "qualification_score": "hot",
    "program_of_interest": "B.Tech Computer Science / Dental Consultation",
    "conversation_summary": "Inquired about root canal treatment timing and booked Sunday 11 AM consultation with Dr. Lalitha.",
    "call_recording_url": "https://api.jkr.ai/api/v1/calls/18173b92-567b-43ea-9d10-3ee1f08bb5d9/recording",
    "call_duration_seconds": 28,
    "last_call_at": "2026-09-24T08:42:39Z"
  }
}
```

### What Is Needed to Move to Production:
1. Destination ERP endpoint URL and client API key provisioned in Workspace Integrations settings.
2. Field-mapping table in DB (`crm_field_mappings`: e.g. mapping `known_fields.service` -> ERP column `course_code`).
3. Dramatiq worker actor `sync_crm_lead_task` executing idempotent POST/PUT to client ERP with 3-attempt exponential backoff.

---

## 3. Meta Lead Ads Integration (Documented Specification)

### Purpose
Capture inbound student/patient leads from Facebook and Instagram lead gen ads in real-time, instantly enroll them into an outbound JKR AI Calling campaign, and trigger an automated qualification call within 60 seconds of submission.

### Architecture & Webhook Verification
1. **Webhook Ingestion:**
   - Meta requires a webhook verification challenge handshake (`GET /api/v1/integrations/meta/webhook`):
     ```python
     if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
         return PlainTextResponse(request.query_params.get("hub.challenge"))
     ```
   - Event receiver (`POST /api/v1/integrations/meta/webhook`):
     - Validates `X-Hub-Signature-256` HMAC using client App Secret.
2. **Lead Retrieval:**
   - Meta webhook only delivers `leadgen_id`, not PII:
     ```json
     {
       "entry": [{
         "changes": [{
           "value": {
             "leadgen_id": "1234567890",
             "page_id": "987654321",
             "form_id": "456789123"
           }
         }]
       }]
     }
     ```
   - Worker queries Graph API: `GET https://graph.facebook.com/v19.0/{leadgen_id}?access_token={page_access_token}`.
   - Extracts `full_name`, `phone_number`, `course_preference`.
3. **Automated Campaign Enrollment:**
   - Automatically inserts row into `contacts` and `campaign_contacts`.
   - Triggers voice-worker to originate outbound AI call.

### What Is Needed to Move to Production:
1. Verified Meta Business App with `leads_retrieval` and `pages_manage_ads` permissions.
2. Long-lived Page Access Token stored in `integration_credentials`.
3. Public HTTPS endpoint (or reverse-proxy tunnel) configured in Meta App Dashboard Webhooks.

---

## 4. n8n Workflow Automation (Documented Specification)

### Purpose
Enable low-code orchestration where users can design custom logic in self-hosted or cloud n8n workflows triggered by JKR Calling events (e.g. sending personalized PDF brochures, Slack notifications to counselors, or notifying field teams).

### Integration Topology
1. **Outbound from JKR Calling to n8n (Active Today via Outgoing Webhooks):**
   - JKR Calling already has a hardened, HMAC-signed webhook delivery engine in `jkr_db.webhook_engine`.
   - Users create an n8n Webhook Node, paste the webhook URL into JKR Calling `/app/integrations`, and set Secret Key.
   - JKR Calling signs every payload with `X-JKR-Signature: sha256=...` protecting against tampering.
2. **Inbound from n8n to JKR Calling (REST API):**
   - n8n triggers outbound call or campaign batch via JKR Calling API:
     - `POST /api/v1/campaigns/{campaign_id}/contacts` (Bulk lead upload)
     - `POST /api/v1/calls/test` or `POST /api/v1/campaigns/{campaign_id}/start`
   - Authenticated using workspace API Key (`Authorization: Bearer jkr_live_...`).

### What Is Needed for Dedicated Community Node:
1. Packaged `n8n-nodes-jkr-calling` npm package containing:
   - Node trigger: `onCallCompleted`, `onAppointmentBooked`, `onLeadHot`.
   - Node action: `startAiCall`, `checkCallStatus`, `bookAppointmentSlot`.
