"use client";

import {
  WebhookEndpointCreate,
  type IntegrationCatalogItem,
  type WebhookEndpointOut,
} from "@jkr/contracts";
import { ApiClientError, integrationsApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FieldError,
  Input,
  Label,
  useToast,
} from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Database,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Globe,
  HelpCircle,
  Loader2,
  MessageSquare,
  Network,
  Play,
  Send,
  Share2,
  Unplug,
  Webhook,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { INTEGRATION_GUIDES } from "@/lib/integration-guides";

const INTEGRATION_ICONS: Record<string, React.ElementType> = {
  webhook: Webhook,
  crm: Database,
  google_calendar: Calendar,
  google_sheets: FileSpreadsheet,
  meta_lead_ads: Share2,
  whatsapp: MessageSquare,
  n8n: Network,
};

function NewWebhookForm({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<WebhookEndpointCreate>({
    resolver: zodResolver(WebhookEndpointCreate),
    defaultValues: { event_types: ["call.completed", "crm.lead.created"] },
  });

  const onSubmit = async (data: WebhookEndpointCreate) => {
    setFormError(null);
    try {
      await integrationsApi.createWebhook(workspaceId, data);
      toast({ title: "Webhook Registered", description: `Endpoint ${data.url} is now active.`, variant: "success" });
      reset({ event_types: ["call.completed", "crm.lead.created"] });
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not register webhook.");
    }
  };

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader>
        <CardTitle className="text-base font-semibold">Add Webhook Endpoint</CardTitle>
        <CardDescription className="text-xs">
          Fires on call completion. Payload is HMAC-signed with SHA256 (X-JKR-Signature header).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3.5">
          <div>
            <Label htmlFor="webhook-url" className="text-xs font-medium">Endpoint URL</Label>
            <Input id="webhook-url" placeholder="https://example.com/webhooks/jkr" className="mt-1" {...register("url")} />
            <FieldError>{errors.url?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="webhook-secret" className="text-xs font-medium">Signing Secret</Label>
            <Input id="webhook-secret" type="password" placeholder="At least 8 characters" className="mt-1" {...register("secret")} />
            <FieldError>{errors.secret?.message}</FieldError>
          </div>
          {formError ? <p className="text-xs text-danger">{formError}</p> : null}
          <Button type="submit" size="sm" className="w-full" loading={isSubmitting}>
            Register Webhook
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function WebhookRow({ workspaceId, endpoint }: { workspaceId: string; endpoint: WebhookEndpointOut }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busy, setBusy] = React.useState(false);

  const deactivate = async () => {
    setBusy(true);
    try {
      await integrationsApi.deactivateWebhook(workspaceId, endpoint.id);
      toast({ title: "Webhook Deactivated", description: "Endpoint has been marked inactive.", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: "Could not deactivate", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center justify-between px-5 py-3 text-sm">
      <div className="min-w-0 pr-4">
        <p className="truncate font-mono text-xs text-foreground">{endpoint.url}</p>
        <p className="text-xs text-muted-foreground">{endpoint.event_types.join(", ")}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={endpoint.is_active ? "success" : "secondary"}>
          {endpoint.is_active ? "active" : "inactive"}
        </Badge>
        {endpoint.is_active ? (
          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={deactivate} loading={busy}>
            Deactivate
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function IntegrationsPage({
  workspaceId,
  catalog,
  webhooks,
}: {
  workspaceId: string;
  catalog: IntegrationCatalogItem[];
  webhooks: WebhookEndpointOut[];
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [activeModal, setActiveModal] = React.useState<string | null>(null);
  const [disconnectingType, setDisconnectingType] = React.useState<string | null>(null);
  const [modalLoading, setModalLoading] = React.useState(false);
  const [modalError, setModalError] = React.useState<string | null>(null);

  // Testing states
  const [testingType, setTestingType] = React.useState<string | null>(null);
  const [testResults, setTestResults] = React.useState<
    Record<string, { status: "success" | "error" | "not_configured"; message: string; details?: Record<string, any>; tested_at: string }>
  >({});
  const [expandedGuides, setExpandedGuides] = React.useState<Record<string, boolean>>({});
  const [testWebhookUrl, setTestWebhookUrl] = React.useState("");

  // Form states for modals
  const [googleEmail, setGoogleEmail] = React.useState("gowthamkrishna19123@gmail.com");
  const [calendarId, setCalendarId] = React.useState("primary");
  const [sheetsSpreadsheetId, setSheetsSpreadsheetId] = React.useState("");
  const [sheetsName, setSheetsName] = React.useState("Appointments & Leads");

  const [n8nUrl, setN8nUrl] = React.useState("https://n8n.io");
  const [n8nKey, setN8nKey] = React.useState("");
  const [crmType, setCrmType] = React.useState<"hubspot" | "webhook">("hubspot");
  const [hubspotToken, setHubspotToken] = React.useState("");
  const [crmUrl, setCrmUrl] = React.useState("");
  const [crmName, setCrmName] = React.useState("HubSpot");
  const [metaPageId, setMetaPageId] = React.useState("");
  const [metaPageName, setMetaPageName] = React.useState("My Facebook Page");
  const [metaToken, setMetaToken] = React.useState("");
  const [waPhone, setWaPhone] = React.useState("+919876543210");
  const [waWabaId, setWaWabaId] = React.useState("");
  const [waToken, setWaToken] = React.useState("");

  const toggleGuide = (type: string) => {
    setExpandedGuides((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  const handleTestIntegration = async (type: string, customPayload?: Record<string, any>) => {
    setTestingType(type);
    try {
      const res = await integrationsApi.testIntegration(workspaceId, type, customPayload);
      setTestResults((prev) => ({
        ...prev,
        [type]: {
          status: res.status as "success" | "error" | "not_configured",
          message: res.message,
          details: res.details,
          tested_at: res.tested_at,
        },
      }));
      toast({
        title:
          res.status === "success"
            ? "Verification Successful"
            : res.status === "not_configured"
            ? "Configuration Required"
            : "Verification Failed",
        description: res.message,
        variant: res.status === "success" ? "success" : res.status === "not_configured" ? "default" : "danger",
      });
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : "Verification test failed.";
      setTestResults((prev) => ({
        ...prev,
        [type]: {
          status: "error",
          message: msg,
          tested_at: new Date().toISOString(),
        },
      }));
      toast({
        title: "Test Error",
        description: msg,
        variant: "danger",
      });
    } finally {
      setTestingType(null);
    }
  };

  const handleOAuthGoogle = async (type: string) => {
    try {
      const resp = await integrationsApi.getGoogleAuthUrl(workspaceId, type);
      if (resp.configured && resp.auth_url) {
        window.location.href = resp.auth_url;
      } else {
        toast({
          title: "Google OAuth Setup Required",
          description: resp.message || "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET for OAuth redirect, or use Direct Connect below.",
          variant: "default",
        });
      }
    } catch (err) {
      toast({
        title: "Connection Error",
        description: err instanceof ApiClientError ? err.message : "Failed to initiate Google OAuth flow.",
        variant: "danger",
      });
    }
  };

  const handleConnectGoogleCalendar = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalLoading(true);
    setModalError(null);
    try {
      await integrationsApi.connectGoogleCalendar(workspaceId, {
        email: googleEmail,
        calendar_id: calendarId,
      });
      toast({
        title: "Google Calendar Connected",
        description: `Connected to ${googleEmail} (${calendarId}). Appointments will sync automatically.`,
        variant: "success",
      });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to connect Google Calendar.");
    } finally {
      setModalLoading(false);
    }
  };

  const handleConnectGoogleSheets = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalLoading(true);
    setModalError(null);
    try {
      await integrationsApi.connectGoogleSheets(workspaceId, {
        email: googleEmail,
        spreadsheet_id: sheetsSpreadsheetId || "jkr-appointments-leads-sheet",
        sheet_name: sheetsName || "Appointments & Leads",
      });
      toast({
        title: "Google Sheets Connected",
        description: `Connected to ${googleEmail}. Appointments and leads will append automatically.`,
        variant: "success",
      });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to connect Google Sheets.");
    } finally {
      setModalLoading(false);
    }
  };

  const handleConnectMeta = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalLoading(true);
    setModalError(null);
    try {
      const res = await integrationsApi.connectMeta(workspaceId, {
        page_id: metaPageId,
        page_name: metaPageName,
        access_token: metaToken || undefined,
      });
      toast({
        title: "Meta Lead Ads Connected",
        description: `Facebook Page ${res.page_id} is now verified and active.`,
        variant: "success",
      });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to connect Meta Lead Ads.");
    } finally {
      setModalLoading(false);
    }
  };

  const handleConnectWhatsapp = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalLoading(true);
    setModalError(null);
    try {
      await integrationsApi.connectWhatsapp(workspaceId, {
        phone_number: waPhone,
        waba_id: waWabaId || undefined,
        access_token: waToken || undefined,
      });
      toast({
        title: "WhatsApp Business Connected",
        description: `WhatsApp line ${waPhone} is now verified and active.`,
        variant: "success",
      });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to connect WhatsApp Business.");
    } finally {
      setModalLoading(false);
    }
  };

  const handleVerifyN8n = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalLoading(true);
    setModalError(null);
    try {
      await integrationsApi.verifyN8n(workspaceId, { instance_url: n8nUrl, api_key: n8nKey || undefined });
      toast({ title: "n8n Connected", description: `Successfully verified instance at ${n8nUrl}`, variant: "success" });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to connect to n8n instance.");
    } finally {
      setModalLoading(false);
    }
  };

  const handleVerifyCrm = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalLoading(true);
    setModalError(null);
    try {
      const res = await integrationsApi.verifyCrm(workspaceId, {
        crm_type: crmType,
        hubspot_token: crmType === "hubspot" ? hubspotToken : undefined,
        webhook_url: crmType === "webhook" ? crmUrl : undefined,
        crm_name: crmType === "hubspot" ? "HubSpot" : crmName,
      });
      toast({
        title: "CRM Connected",
        description: res.hubspot_id
          ? `Verified HubSpot connection! Real test contact ID: ${res.hubspot_id}`
          : `Connected ${res.crm_name} at ${res.webhook_url}`,
        variant: "success",
      });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to verify CRM.");
    } finally {
      setModalLoading(false);
    }
  };

  const handleDisconnect = async (type: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDisconnectingType(type);
    try {
      await integrationsApi.disconnect(workspaceId, type);
      toast({ title: "Disconnected", description: "Integration has been disconnected.", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({
        title: "Disconnect Failed",
        description: err instanceof ApiClientError ? err.message : "Could not disconnect integration.",
        variant: "danger",
      });
    } finally {
      setDisconnectingType(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Integrations Grid */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.map((item) => {
          const Icon = INTEGRATION_ICONS[item.type] || Globe;
          const isConnected = item.status === "connected";
          const isConnecting = item.status === "connecting";
          const isError = item.status === "error";
          const isBuiltIn = item.type === "google_calendar" || item.type === "google_sheets";
          const isExpanded = !!expandedGuides[item.type];
          const testResult = testResults[item.type];
          const guide = INTEGRATION_GUIDES[item.type];

          return (
            <Card
              key={item.type}
              className={`relative overflow-hidden transition-all duration-200 border-border/60 flex flex-col justify-between ${
                isConnected
                  ? "border-emerald-500/40 shadow-sm shadow-emerald-500/5"
                  : isError
                  ? "border-danger/40"
                  : "hover:border-border"
              }`}
            >
              <CardContent className="p-5 flex flex-col justify-between h-full space-y-4">
                <div>
                  <div className="flex items-start justify-between gap-3 mb-2.5">
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex h-10 w-10 items-center justify-center rounded-xl border ${
                          isConnected
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                            : isError
                            ? "bg-danger/10 border-danger/30 text-danger"
                            : "bg-surface-raised border-border text-muted-foreground"
                        }`}
                      >
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-medium text-sm text-foreground flex items-center gap-1.5">
                          {item.type === "google_calendar"
                            ? "Calendar Export (.ics)"
                            : item.type === "google_sheets"
                            ? "Data Export (CSV)"
                            : item.label}
                        </h3>
                        {item.type === "google_calendar" ? (
                          <p className="text-xs text-emerald-400 font-medium flex items-center gap-1 mt-0.5">
                            <CheckCircle2 className="h-3 w-3" />
                            Free · Universal (.ics)
                          </p>
                        ) : item.type === "google_sheets" ? (
                          <p className="text-xs text-emerald-400 font-medium flex items-center gap-1 mt-0.5">
                            <CheckCircle2 className="h-3 w-3" />
                            Free · On-demand CSV
                          </p>
                        ) : isConnected ? (
                          <p className="text-xs text-emerald-400 font-medium flex items-center gap-1 mt-0.5">
                            <CheckCircle2 className="h-3 w-3" />
                            {item.connected_account || "Connected"}
                          </p>
                        ) : isError ? (
                          <p className="text-xs text-danger font-medium flex items-center gap-1 mt-0.5">
                            <AlertCircle className="h-3 w-3" />
                            Connection Error
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {item.requires_oauth ? "OAuth / Direct Token" : "Not connected"}
                          </p>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant={
                        isConnected ? "success" : isError ? "danger" : isConnecting ? "secondary" : "secondary"
                      }
                      className="capitalize"
                    >
                      {isBuiltIn
                        ? "Active (Built-in)"
                        : isConnected
                        ? "Connected"
                        : isError
                        ? "Error"
                        : isConnecting
                        ? "Connecting"
                        : "Not Connected"}
                    </Badge>
                  </div>

                  {item.last_error && isError && (
                    <div className="mb-2.5 p-2 rounded-lg bg-danger/10 border border-danger/20 text-xs text-danger flex items-start gap-1.5">
                      <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                      <span className="line-clamp-2">{item.last_error}</span>
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {item.type === "google_calendar"
                      ? "Every confirmed appointment includes a downloadable .ics calendar invite and 1-tap Google/Apple/Outlook links — zero OAuth, zero billing required."
                      : item.type === "google_sheets"
                      ? "Export confirmed appointments, qualified leads, and caller data as CSV anytime — zero OAuth or Google Cloud billing required."
                      : item.description || (isConnected ? "Active external connection." : "Not connected yet.")}
                  </p>
                </div>

                {/* Inline Test Result Box */}
                {testResult && (
                  <div
                    className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                      testResult.status === "success"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-foreground"
                        : testResult.status === "not_configured"
                        ? "bg-amber-500/10 border-amber-500/30 text-foreground"
                        : "bg-danger/10 border-danger/30 text-danger"
                    }`}
                  >
                    <div className="flex items-center justify-between font-semibold">
                      <span className="flex items-center gap-1">
                        {testResult.status === "success" ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                        ) : testResult.status === "not_configured" ? (
                          <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
                        ) : (
                          <AlertCircle className="h-3.5 w-3.5 text-danger" />
                        )}
                        {testResult.status === "success"
                          ? "Test Passed"
                          : testResult.status === "not_configured"
                          ? "Setup Required"
                          : "Verification Failed"}
                      </span>
                      <span className="text-[10px] text-muted-foreground font-normal">
                        {new Date(testResult.tested_at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST
                      </span>
                    </div>
                    <p className="text-[11px] leading-relaxed text-muted-foreground">{testResult.message}</p>
                    {testResult.details && testResult.details.download_url && (
                      <div className="pt-1 flex items-center gap-2">
                        <a
                          href={testResult.details.download_url}
                          download
                          className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline font-medium"
                        >
                          <Download className="h-3 w-3" /> Download Sample
                        </a>
                        {testResult.details.google_calendar_url && (
                          <a
                            href={testResult.details.google_calendar_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline font-medium"
                          >
                            <ExternalLink className="h-3 w-3" /> Add to Google Calendar
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Expandable How To Connect Guide */}
                {guide && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => toggleGuide(item.type)}
                      className="w-full flex items-center justify-between text-xs text-muted-foreground hover:text-foreground font-medium py-1 transition-colors"
                    >
                      <span className="flex items-center gap-1">
                        <HelpCircle className="h-3.5 w-3.5 text-primary/80" />
                        How to connect & use
                      </span>
                      {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </button>

                    {isExpanded && (
                      <div className="mt-2.5 p-3 rounded-lg bg-surface-raised border border-border text-xs space-y-2.5 max-h-72 overflow-y-auto">
                        <div>
                          <p className="font-semibold text-foreground">What it does</p>
                          <p className="text-muted-foreground mt-0.5 leading-relaxed">{guide.whatItDoes}</p>
                        </div>
                        <div>
                          <p className="font-semibold text-foreground">Why use it</p>
                          <p className="text-muted-foreground mt-0.5 leading-relaxed">{guide.whyUseIt}</p>
                        </div>
                        <div>
                          <p className="font-semibold text-foreground">Before starting</p>
                          <ul className="list-disc list-inside text-muted-foreground mt-0.5 space-y-0.5">
                            {guide.prerequisites.map((p, idx) => (
                              <li key={idx}>{p}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="font-semibold text-foreground">Step-by-step setup</p>
                          <ol className="list-decimal list-inside text-muted-foreground mt-0.5 space-y-1">
                            {guide.steps.map((s, idx) => (
                              <li key={idx} className="leading-relaxed">
                                {s}
                              </li>
                            ))}
                          </ol>
                        </div>
                        <div>
                          <p className="font-semibold text-foreground">What success looks like</p>
                          <p className="text-muted-foreground mt-0.5 leading-relaxed">{guide.successIndicator}</p>
                        </div>
                        {guide.troubleshooting.length > 0 && (
                          <div>
                            <p className="font-semibold text-foreground">Troubleshooting</p>
                            <div className="space-y-1 mt-0.5">
                              {guide.troubleshooting.map((t, idx) => (
                                <div key={idx} className="text-[11px]">
                                  <span className="font-medium text-foreground">&bull; {t.issue}: </span>
                                  <span className="text-muted-foreground">{t.solution}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {guide.extraNotice && (
                          <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-300">
                            {guide.extraNotice}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Footer Action Buttons */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-border/40">
                  <div className="flex items-center gap-1.5">
                    {/* Live Test / Verify Button */}
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-7 px-2.5 text-xs font-medium"
                      loading={testingType === item.type}
                      onClick={() => {
                        if (item.type === "webhook") {
                          setActiveModal("test_webhook");
                        } else {
                          handleTestIntegration(item.type);
                        }
                      }}
                    >
                      <Play className="h-3 w-3 mr-1" />
                      {item.type === "webhook" ? "Send Test" : "Verify Connection"}
                    </Button>

                    {/* Portal link for connected services */}
                    {isConnected && item.external_url && item.external_url.startsWith("http") && (
                      <a
                        href={item.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium px-1.5 py-1"
                      >
                        Open Portal <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                    {isBuiltIn && (
                      <a
                        href="/app/appointments"
                        className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium px-1.5 py-1"
                      >
                        {item.type === "google_calendar" ? "Appointments →" : "Export CSV →"}
                      </a>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {isConnected && !isBuiltIn ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-danger/80 hover:text-danger hover:bg-danger/10 px-2"
                        loading={disconnectingType === item.type}
                        onClick={(e) => handleDisconnect(item.type, e)}
                      >
                        <Unplug className="h-3 w-3 mr-1" /> Disconnect
                      </Button>
                    ) : !isBuiltIn ? (
                      <Button
                        size="sm"
                        variant="default"
                        className="h-7 text-xs px-2.5"
                        onClick={() => {
                          setModalError(null);
                          if (item.type === "crm") setActiveModal("crm");
                          else if (item.type === "n8n") setActiveModal("n8n");
                          else if (item.type === "meta_lead_ads") setActiveModal("meta");
                          else if (item.type === "whatsapp") setActiveModal("whatsapp");
                        }}
                      >
                        Connect
                      </Button>
                    ) : null}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Webhook Endpoints Management */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2 border-border/60">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base font-semibold">Registered Webhook Endpoints</CardTitle>
                <CardDescription className="text-xs">
                  {webhooks.length} destination{webhooks.length === 1 ? "" : "s"} actively listening to JKR Calling events.
                </CardDescription>
              </div>
              <Badge variant={webhooks.length > 0 ? "success" : "secondary"}>
                {webhooks.length > 0 ? `${webhooks.length} Active` : "None"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {webhooks.length === 0 ? (
              <div className="p-8 text-center">
                <Webhook className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                <p className="text-sm font-medium text-foreground">No webhooks registered</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Add an endpoint to receive signed call.completed & CRM events.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {webhooks.map((w) => (
                  <WebhookRow key={w.id} workspaceId={workspaceId} endpoint={w} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <NewWebhookForm workspaceId={workspaceId} />
      </div>

      {/* Modal: Test Webhook Payload */}
      {activeModal === "test_webhook" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Send className="h-4 w-4 text-primary" /> Send Test Webhook
                </CardTitle>
                <CardDescription className="text-xs">
                  Dispatches a real call.completed event with HMAC-SHA256 signature.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  setModalLoading(true);
                  try {
                    await handleTestIntegration("webhook", testWebhookUrl ? { target_url: testWebhookUrl } : undefined);
                    setActiveModal(null);
                  } finally {
                    setModalLoading(false);
                  }
                }}
                className="space-y-4"
              >
                <div>
                  <Label htmlFor="test-webhook-url" className="text-xs font-medium">Destination URL (Optional)</Label>
                  <Input
                    id="test-webhook-url"
                    placeholder="https://webhook.site/your-unique-id or leave empty for active endpoint"
                    value={testWebhookUrl}
                    onChange={(e) => setTestWebhookUrl(e.target.value)}
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Tip: Visit <a href="https://webhook.site" target="_blank" rel="noreferrer" className="text-primary underline">webhook.site</a> to get a free test URL and inspect incoming JSON headers live.
                  </p>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={modalLoading}>
                    Dispatch Test Payload
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal: CRM (HubSpot & Webhook) Configuration */}
      {activeModal === "crm" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Database className="h-4 w-4 text-primary" /> Connect CRM Lead Pipeline
                </CardTitle>
                <CardDescription className="text-xs">
                  Sync qualified callers directly into your CRM.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              {/* Type Switcher */}
              <div className="flex rounded-lg bg-surface-raised p-1 mb-4 border border-border">
                <button
                  type="button"
                  onClick={() => setCrmType("hubspot")}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${
                    crmType === "hubspot" ? "bg-surface text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  HubSpot (Direct API)
                </button>
                <button
                  type="button"
                  onClick={() => setCrmType("webhook")}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${
                    crmType === "webhook" ? "bg-surface text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Custom CRM Webhook
                </button>
              </div>

              <form onSubmit={handleVerifyCrm} className="space-y-4">
                {crmType === "hubspot" ? (
                  <>
                    <div>
                      <Label htmlFor="hubspot-token" className="text-xs font-medium">HubSpot Private App Access Token</Label>
                      <Input
                        id="hubspot-token"
                        type="password"
                        placeholder="pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                        value={hubspotToken}
                        onChange={(e) => setHubspotToken(e.target.value)}
                        required
                        className="mt-1 font-mono text-xs"
                      />
                      <div className="mt-2 p-2.5 rounded bg-surface-raised border border-border text-[11px] text-muted-foreground space-y-1">
                        <p className="font-semibold text-foreground">How to get your Private App Token:</p>
                        <p>1. Open HubSpot &rarr; Settings (gear icon) &rarr; Integrations &rarr; Private Apps.</p>
                        <p>2. Click &quot;Create a private app&quot; and grant scopes: <code className="text-primary font-mono">crm.objects.contacts.write</code> and <code className="text-primary font-mono">crm.objects.contacts.read</code>.</p>
                        <p>3. Click &quot;Create app&quot;, copy the token, and paste it here.</p>
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <Label htmlFor="crm-name" className="text-xs font-medium">CRM Name</Label>
                      <Input
                        id="crm-name"
                        placeholder="Salesforce / Zoho CRM / College ERP"
                        value={crmName}
                        onChange={(e) => setCrmName(e.target.value)}
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="crm-url" className="text-xs font-medium">Webhook Receiver URL</Label>
                      <Input
                        id="crm-url"
                        placeholder="https://your-crm-server.com/api/v1/leads"
                        value={crmUrl}
                        onChange={(e) => setCrmUrl(e.target.value)}
                        required
                        className="mt-1"
                      />
                    </div>
                  </>
                )}

                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={modalLoading}>
                    {crmType === "hubspot" ? "Verify & Connect HubSpot" : "Verify & Connect Webhook"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal: Meta Lead Ads Configuration */}
      {activeModal === "meta" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Share2 className="h-4 w-4 text-blue-400" /> Connect Meta Lead Ads
                </CardTitle>
                <CardDescription className="text-xs">
                  Connect Facebook & Instagram Lead Ads for instant AI callback.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleConnectMeta} className="space-y-4">
                <div>
                  <Label htmlFor="meta-page-id" className="text-xs font-medium">Facebook Page ID</Label>
                  <Input
                    id="meta-page-id"
                    placeholder="108294719284102"
                    value={metaPageId}
                    onChange={(e) => setMetaPageId(e.target.value)}
                    required
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">Found in Facebook Page Settings &rarr; About.</p>
                </div>
                <div>
                  <Label htmlFor="meta-page-name" className="text-xs font-medium">Page Display Name</Label>
                  <Input
                    id="meta-page-name"
                    placeholder="JKR Calling Facebook Page"
                    value={metaPageName}
                    onChange={(e) => setMetaPageName(e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="meta-token" className="text-xs font-medium">Page Access Token</Label>
                  <Input
                    id="meta-token"
                    type="password"
                    placeholder="EAABwz..."
                    value={metaToken}
                    onChange={(e) => setMetaToken(e.target.value)}
                    required
                    className="mt-1 font-mono text-xs"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Generated from Meta Developers with <code className="text-primary font-mono">leads_retrieval</code> and <code className="text-primary font-mono">pages_manage_ads</code> permissions.
                  </p>
                </div>
                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={modalLoading}>
                    Connect Meta Ads
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal: WhatsApp Business Configuration */}
      {activeModal === "whatsapp" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-emerald-400" /> Connect WhatsApp Business (Meta Cloud API)
                </CardTitle>
                <CardDescription className="text-xs">
                  Connect official Meta WABA for custom templates.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <div className="mb-3.5 p-2.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-300">
                Note: JKR Calling already has built-in transactional WhatsApp confirmations via Twilio. Configure this only if you want official Meta Cloud API WABA templates.
              </div>
              <form onSubmit={handleConnectWhatsapp} className="space-y-4">
                <div>
                  <Label htmlFor="wa-phone" className="text-xs font-medium">WhatsApp Business Phone Number</Label>
                  <Input
                    id="wa-phone"
                    placeholder="+919876543210"
                    value={waPhone}
                    onChange={(e) => setWaPhone(e.target.value)}
                    required
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">E.164 format with country code.</p>
                </div>
                <div>
                  <Label htmlFor="wa-waba" className="text-xs font-medium">WABA Account ID</Label>
                  <Input
                    id="wa-waba"
                    placeholder="waba_1092837482"
                    value={waWabaId}
                    onChange={(e) => setWaWabaId(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="wa-token" className="text-xs font-medium">System User Access Token</Label>
                  <Input
                    id="wa-token"
                    type="password"
                    placeholder="EAABwz..."
                    value={waToken}
                    onChange={(e) => setWaToken(e.target.value)}
                    required
                    className="mt-1 font-mono text-xs"
                  />
                </div>
                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={modalLoading}>
                    Connect WhatsApp
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal: n8n Configuration */}
      {activeModal === "n8n" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Network className="h-4 w-4 text-primary" /> Connect n8n Automation
                </CardTitle>
                <CardDescription className="text-xs">Provide your self-hosted or cloud n8n instance URL.</CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleVerifyN8n} className="space-y-4">
                <div>
                  <Label htmlFor="n8n-url" className="text-xs font-medium">Instance URL</Label>
                  <Input
                    id="n8n-url"
                    placeholder="https://n8n.yourdomain.com"
                    value={n8nUrl}
                    onChange={(e) => setN8nUrl(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="n8n-key" className="text-xs font-medium">API Key (Optional)</Label>
                  <Input
                    id="n8n-key"
                    type="password"
                    placeholder="n8n_api_key_..."
                    value={n8nKey}
                    onChange={(e) => setN8nKey(e.target.value)}
                    className="mt-1 font-mono text-xs"
                  />
                </div>
                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={modalLoading}>
                    Connect n8n
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
