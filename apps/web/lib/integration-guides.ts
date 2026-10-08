export interface TroubleshootingItem {
  issue: string;
  solution: string;
}

export interface IntegrationGuide {
  id: string;
  title: string;
  i18nKey: string;
  whatItDoes: string;
  whyUseIt: string;
  prerequisites: string[];
  steps: string[];
  successIndicator: string;
  howToTest: string;
  troubleshooting: TroubleshootingItem[];
  extraNotice?: string;
}

export const INTEGRATION_GUIDES: Record<string, IntegrationGuide> = {
  webhook: {
    id: "webhook",
    title: "Outgoing Webhooks",
    i18nKey: "integrations.guide.webhook",
    whatItDoes:
      "Sends real-time JSON notifications from JKR Calling directly to your own server, CRM, or backend API as soon as a phone call or chat ends.",
    whyUseIt:
      "Get call transcripts, call audio recordings, caller intent summaries, qualification scores, and appointment details delivered to your system instantly with zero manual data entry.",
    prerequisites: [
      "A public HTTPS endpoint URL that can receive POST requests (e.g. https://yourdomain.com/api/webhooks).",
      "For quick testing: a free URL from webhook.site (no account required).",
      "A secret passphrase of your choice (minimum 8 characters) to verify that incoming payloads are authentic.",
    ],
    steps: [
      "Click 'Add Webhook Endpoint' below.",
      "In the 'Endpoint URL' field, paste your destination URL (e.g. https://webhook.site/your-unique-uuid).",
      "In the 'Signing Secret' field, choose a secure passphrase (e.g. MySecretWebHook2026).",
      "Check the events you want to receive ('call.completed', 'crm.lead.created').",
      "Click 'Register Webhook'. The status badge will update to Active.",
    ],
    successIndicator:
      "When a phone call concludes, your server receives an HTTP POST request with headers 'X-JKR-Signature' (HMAC-SHA256) and a JSON payload containing caller phone, call duration, billable seconds, and AI summary.",
    howToTest:
      "Click the 'Send Test Webhook' button on this card. Enter your webhook.site URL and click Send. Open your webhook.site tab to see the live signed JSON payload arrive within milliseconds.",
    troubleshooting: [
      {
        issue: "HTTP 404 or 405 on receiving server",
        solution: "Verify your server route accepts HTTP POST requests (not just GET).",
      },
      {
        issue: "Signature mismatch error",
        solution: "Ensure your backend verifies HMAC-SHA256 using the exact same Signing Secret you entered in JKR Calling.",
      },
      {
        issue: "Webhook timeouts",
        solution: "Your endpoint must return HTTP 200 within 8 seconds. For heavy database jobs, respond with 200 immediately and process the call payload asynchronously.",
      },
    ],
  },

  crm: {
    id: "crm",
    title: "CRM Lead Pipeline (HubSpot & Webhook)",
    i18nKey: "integrations.guide.crm",
    whatItDoes:
      "Syncs high-intent callers, qualified leads, and appointment bookings automatically into your HubSpot account or custom CRM (Salesforce, Zoho, or College ERP).",
    whyUseIt:
      "Ensures sales agents never miss a qualified prospect. Leads gathered by the AI voice assistant appear in your CRM with full contact information, conversation notes, and pipeline stage.",
    prerequisites: [
      "A free or paid HubSpot account (app.hubspot.com).",
      "A HubSpot Private App Access Token (starts with 'pat-na1-' or 'pat-eu1-').",
      "OR for custom CRMs: a webhook receiver URL from your CRM or automation tool (Zapier/Make).",
    ],
    steps: [
      "In HubSpot, go to Settings (gear icon in top right) -> Integrations -> Private Apps.",
      "Click 'Create a private app'. Name it 'JKR Calling Voice Sync'.",
      "Click the 'Scopes' tab and grant: 'crm.objects.contacts.write' and 'crm.objects.contacts.read'.",
      "Click 'Create app' -> 'Continue creating' -> 'Show token' -> 'Copy'.",
      "Return to JKR Calling, click 'Connect CRM' on this card, paste your Private App Token, and click 'Verify & Connect'.",
    ],
    successIndicator:
      "Card badge changes to 'Connected' with 'HubSpot CRM'. A test contact ('JKR Verification Lead') will appear in your HubSpot Contacts list with company 'JKR Calling Lead Sync'.",
    howToTest:
      "Click 'Verify Connection'. JKR Calling will communicate with HubSpot's CRM API and create or update a verified test contact, confirming full two-way communication.",
    troubleshooting: [
      {
        issue: "HubSpot HTTP 401 Unauthorized",
        solution: "The Private App Token is invalid or expired. Re-generate the token in HubSpot Settings -> Private Apps and paste the fresh token.",
      },
      {
        issue: "HubSpot HTTP 403 Forbidden (Missing Scopes)",
        solution: "Edit your Private App in HubSpot and ensure 'crm.objects.contacts.write' and 'crm.objects.contacts.read' scopes are enabled.",
      },
      {
        issue: "Custom CRM Webhook not receiving leads",
        solution: "Check that your webhook URL is public (HTTPS) and reachable from the internet.",
      },
    ],
    extraNotice: "Clicking 'Open Portal' on a connected HubSpot card opens your live HubSpot CRM dashboard at app.hubspot.com.",
  },

  google_calendar: {
    id: "google_calendar",
    title: "Calendar Export (.ics)",
    i18nKey: "integrations.guide.calendar",
    whatItDoes:
      "Automatically creates universal .ics calendar invites for every appointment booked by your AI assistant, complete with 1-tap Google Calendar, Apple Calendar, and Outlook Web links.",
    whyUseIt:
      "100% free, built-in, and requires ZERO Google Cloud billing, Microsoft Azure setup, or OAuth permissions. Works across all calendar applications and mobile devices seamlessly.",
    prerequisites: [
      "Nothing! This feature is built-in and always active for all workspaces.",
    ],
    steps: [
      "When your AI voice assistant books an appointment during a phone call or website chat, an RFC 5545 calendar invite is automatically generated.",
      "The confirmation WhatsApp message sent to the caller includes a 1-tap link to add the event to their Google Calendar or download the .ics file.",
      "You can also download .ics files anytime directly from the Appointments tab.",
    ],
    successIndicator:
      "Every booked appointment has a calendar download button and 1-tap add link in the Appointments dashboard.",
    howToTest:
      "Click 'Test .ics Generation' below. JKR Calling will generate a valid calendar invite and provide direct links to test 1-tap Google Calendar and Outlook import.",
    troubleshooting: [
      {
        issue: "Calendar shows wrong timezone",
        solution: "JKR Calling automatically formats timestamps in IST (India Standard Time, UTC+05:30). When imported into Google or Apple Calendar, it adjusts to your device's local timezone automatically.",
      },
    ],
  },

  google_sheets: {
    id: "google_sheets",
    title: "Data Export (CSV)",
    i18nKey: "integrations.guide.sheets",
    whatItDoes:
      "Provides instant 1-click CSV file downloads of all your booked appointments, qualified caller leads, conversation tags, and follow-up tasks.",
    whyUseIt:
      "Import your data into Microsoft Excel, Google Sheets, or Apple Numbers anytime for accounting, team reviews, or offline reports without complex OAuth setups.",
    prerequisites: [
      "Nothing! This feature is built-in and always active for all workspaces.",
    ],
    steps: [
      "Navigate to the Appointments or Contacts tab in the left sidebar.",
      "Click the 'Export CSV' button in the top right.",
      "Open the downloaded file in Microsoft Excel, Google Sheets, or any spreadsheet software.",
    ],
    successIndicator:
      "A clean CSV file downloads with headers: Appointment ID, Customer Name, Phone, Scheduled Date (IST), Scheduled Time (IST), Status, and Conversation Notes.",
    howToTest:
      "Click 'Verify CSV Export' below. JKR Calling will verify that your workspace appointment database is correctly structured and format a test export.",
    troubleshooting: [
      {
        issue: "Exported CSV is empty",
        solution: "Your workspace has no booked appointments yet. Run a test call in the Test Lab to book an appointment first.",
      },
    ],
  },

  meta_lead_ads: {
    id: "meta_lead_ads",
    title: "Meta Lead Ads (Facebook & Instagram)",
    i18nKey: "integrations.guide.meta",
    whatItDoes:
      "Captures leads the exact second a prospective customer submits a Lead Ad form on Facebook or Instagram, and triggers an instant AI phone call within 30 seconds.",
    whyUseIt:
      "Contacting a lead within 5 minutes increases conversion rates by up to 21x. Your AI agent calls while the user is still looking at their phone.",
    prerequisites: [
      "A Meta Business Manager account with an active Facebook Page.",
      "A Meta Lead Ad campaign running with a Lead Generation Instant Form.",
      "A Page Access Token with 'leads_retrieval' and 'pages_manage_ads' permissions from developers.facebook.com.",
    ],
    steps: [
      "Open Meta for Developers (developers.facebook.com) and create or select your Business App.",
      "Add the 'Webhooks' product and subscribe to the 'leadgen' field for your Page.",
      "In Graph API Explorer, select your Facebook Page and generate a Page Access Token with 'leads_retrieval', 'pages_show_list', and 'pages_manage_ads' scopes.",
      "Copy your Facebook Page ID (found in Page About / Settings) and the Page Access Token.",
      "Click 'Connect Meta' on this card, paste the Page ID and Token, and click 'Connect Meta Ads'.",
    ],
    successIndicator:
      "Card badge turns to 'Connected' displaying your Facebook Page name. When a lead submits an ad form on Instagram or Facebook, JKR Calling receives the webhook and initiates an outreach call.",
    howToTest:
      "Use the official Meta Lead Ads Testing Tool at developers.facebook.com/tools/lead-ads-testing. Select your Page and Form, click 'Create lead', and watch the inbound lead appear in JKR Calling.",
    troubleshooting: [
      {
        issue: "Meta Graph API token expired",
        solution: "Standard user tokens expire after 60 days. In Meta Business Manager, create a 'System User' and generate a permanent System User Token.",
      },
      {
        issue: "No lead callback occurs",
        solution: "Ensure the campaign is enabled and ENABLE_LIVE_CALLS setting in JKR Calling allows outbound calls.",
      },
    ],
    extraNotice: "If you do not run Facebook/Instagram Ads, leave this integration as 'Not Connected'.",
  },

  whatsapp: {
    id: "whatsapp",
    title: "WhatsApp Business Integration",
    i18nKey: "integrations.guide.whatsapp",
    whatItDoes:
      "Enables automated post-call appointment confirmations, brochures, and follow-up messages sent directly to your callers over WhatsApp.",
    whyUseIt:
      "98% open rate compared to 20% for email. Callers receive their booking details and meeting location on their phone instantly.",
    prerequisites: [
      "FOR BASIC NOTIFICATIONS: None! JKR Calling already has built-in Twilio WhatsApp / SMS notification dispatch enabled in the pipeline.",
      "FOR OFFICIAL META CLOUD API (Optional): A Meta WhatsApp Business Account (WABA) ID, a phone number registered with WhatsApp Cloud API, and a System User Access Token.",
    ],
    steps: [
      "Understanding the 2 modes:",
      "1. Built-in Transactional Sending (Default): JKR Calling automatically dispatches appointment confirmations via Twilio WhatsApp sender with SMS fallback. No setup required.",
      "2. Meta WhatsApp Cloud API Direct: If you want official green-badge WhatsApp templates without Twilio, go to developers.facebook.com -> WhatsApp -> Getting Started.",
      "Copy your WhatsApp Business Account ID (WABA ID) and System User Token.",
      "Click 'Connect WA' on this card, enter your phone number, WABA ID, and Token, then click 'Connect WhatsApp'.",
    ],
    successIndicator:
      "Callers automatically receive WhatsApp messages confirming appointment date, time, and address as soon as an appointment is booked.",
    howToTest:
      "Click 'Verify Connection' on this card to check the status of your WhatsApp notification pipeline.",
    troubleshooting: [
      {
        issue: "Twilio WhatsApp Sandbox recipient not joined (Error 63015)",
        solution: "When testing with a Twilio Sandbox number, the recipient's phone must send the join keyword (e.g. 'join <keyword>') to Twilio once. If not joined, JKR Calling automatically falls back to SMS so the notification is never lost.",
      },
      {
        issue: "Template not approved on Meta Cloud API",
        solution: "On Meta WhatsApp Manager, ensure your notification template has 'Utility' category and 'Approved' status.",
      },
    ],
    extraNotice:
      "IMPORTANT: Your workspace is already equipped with transactional WhatsApp & SMS appointment notifications. Meta Cloud API is only required if you manage your own Meta WABA directly.",
  },

  n8n: {
    id: "n8n",
    title: "n8n Workflow Automation",
    i18nKey: "integrations.guide.n8n",
    whatItDoes:
      "Connects your self-hosted or cloud n8n instance to trigger complex multi-step automations whenever calls start, end, or book appointments.",
    whyUseIt:
      "Build custom workflows to send Slack alerts, update Google Sheets, sync with custom PostgreSQL/MySQL databases, or notify regional sales teams.",
    prerequisites: [
      "A running n8n instance (self-hosted on Docker/VPS or n8n.cloud).",
      "Your n8n instance URL (e.g. https://n8n.yourcompany.com).",
      "An optional n8n API Key (found in n8n Settings -> API).",
    ],
    steps: [
      "In n8n, create a new workflow and add a 'Webhook' trigger node. Set the HTTP method to 'POST'.",
      "Copy the Webhook URL generated by n8n.",
      "In JKR Calling, click 'Connect n8n' on this card.",
      "Enter your n8n instance URL (e.g. https://n8n.yourcompany.com) and API Key or Webhook URL.",
      "Click 'Connect n8n'. JKR Calling will verify that your n8n instance responds.",
    ],
    successIndicator:
      "Card badge turns to 'Connected' with your instance URL. When a call completes, n8n trigger nodes fire and execute downstream workflows.",
    howToTest:
      "Click 'Verify Connection' below. JKR Calling will ping your n8n instance's health endpoint and report latency.",
    troubleshooting: [
      {
        issue: "Connection refused / timeout",
        solution: "Check that your self-hosted n8n instance is publicly accessible on HTTPS with a valid SSL certificate.",
      },
      {
        issue: "HTTP 401 Unauthorized",
        solution: "Ensure the n8n API Key provided has permissions to access your instance.",
      },
    ],
    extraNotice: "n8n is open-source and self-hostable. If you do not use n8n, leave this card as 'Not Connected'.",
  },
};
