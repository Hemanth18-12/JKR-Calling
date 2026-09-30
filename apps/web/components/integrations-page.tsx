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
  Calendar,
  CheckCircle2,
  Database,
  ExternalLink,
  FileSpreadsheet,
  Globe,
  Loader2,
  MessageSquare,
  Network,
  Radio,
  Share2,
  Unplug,
  Webhook,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

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

  // Form states for modals
  const [googleEmail, setGoogleEmail] = React.useState("gowthamkrishna19123@gmail.com");
  const [calendarId, setCalendarId] = React.useState("primary");
  const [sheetsSpreadsheetId, setSheetsSpreadsheetId] = React.useState("");
  const [sheetsName, setSheetsName] = React.useState("Appointments & Leads");

  const [n8nUrl, setN8nUrl] = React.useState("https://n8n.io");
  const [n8nKey, setN8nKey] = React.useState("");
  const [crmUrl, setCrmUrl] = React.useState("https://api.hubspot.com/webhooks/v1/leads");
  const [crmName, setCrmName] = React.useState("HubSpot");
  const [metaPageId, setMetaPageId] = React.useState("108294719284102");
  const [metaPageName, setMetaPageName] = React.useState("JKR Calling Page");
  const [metaToken, setMetaToken] = React.useState("");
  const [waPhone, setWaPhone] = React.useState("+919876543210");
  const [waWabaId, setWaWabaId] = React.useState("waba_jkr_prod");
  const [waToken, setWaToken] = React.useState("");

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
      await integrationsApi.connectMeta(workspaceId, {
        page_id: metaPageId,
        page_name: metaPageName,
        access_token: metaToken || undefined,
      });
      toast({
        title: "Meta Lead Ads Connected",
        description: `Page ${metaPageName} (ID: ${metaPageId}) is now active.`,
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
        description: `WhatsApp line ${waPhone} is now active for notifications & confirmations.`,
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
      toast({ title: "n8n Connected", description: `Successfully connected instance at ${n8nUrl}`, variant: "success" });
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
      await integrationsApi.verifyCrm(workspaceId, { webhook_url: crmUrl, crm_name: crmName });
      toast({ title: "CRM Connected", description: `Connected ${crmName} at ${crmUrl}`, variant: "success" });
      setActiveModal(null);
      router.refresh();
    } catch (err) {
      setModalError(err instanceof ApiClientError ? err.message : "Failed to verify CRM webhook.");
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
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.map((item) => {
          const Icon = INTEGRATION_ICONS[item.type] || Globe;
          const isConnected = item.status === "connected";

          return (
            <Card
              key={item.type}
              onClick={() => {
                if (isConnected && item.external_url) {
                  window.open(item.external_url, "_blank", "noopener,noreferrer");
                }
              }}
              className={`relative overflow-hidden transition-all duration-200 border-border/60 ${
                isConnected
                  ? "cursor-pointer hover:border-emerald-500/50 hover:shadow-md hover:shadow-emerald-500/5"
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
                            : "bg-surface-raised border-border text-muted-foreground"
                        }`}
                      >
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-medium text-sm text-foreground flex items-center gap-1.5">
                          {item.label}
                          {isConnected && item.external_url ? (
                            <ExternalLink className="h-3.5 w-3.5 text-muted-foreground opacity-60" />
                          ) : null}
                        </h3>
                        {isConnected ? (
                          <p className="text-xs text-emerald-400 font-medium flex items-center gap-1 mt-0.5">
                            <CheckCircle2 className="h-3 w-3" />
                            {item.connected_account || "Connected"}
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {item.requires_oauth ? "OAuth / Direct" : "Not connected"}
                          </p>
                        )}
                      </div>
                    </div>
                    <Badge variant={isConnected ? "success" : "secondary"} className="capitalize">
                      {isConnected ? "Connected" : "Not Connected"}
                    </Badge>
                  </div>

                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {item.description || (isConnected ? "Active external connection." : "Not connected yet.")}
                  </p>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-border/40">
                  {isConnected ? (
                    <>
                      {item.external_url ? (
                        <a
                          href={item.external_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium"
                        >
                          Open Service <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">Active in pipeline</span>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-danger/80 hover:text-danger hover:bg-danger/10"
                        loading={disconnectingType === item.type}
                        onClick={(e) => handleDisconnect(item.type, e)}
                      >
                        <Unplug className="h-3 w-3 mr-1" /> Disconnect
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="text-xs text-muted-foreground font-mono">Status: Idle</span>
                      {item.type === "google_calendar" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          onClick={() => {
                            setModalError(null);
                            setActiveModal("google_calendar");
                          }}
                        >
                          Connect Calendar
                        </Button>
                      ) : item.type === "google_sheets" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          onClick={() => {
                            setModalError(null);
                            setActiveModal("google_sheets");
                          }}
                        >
                          Connect Sheets
                        </Button>
                      ) : item.type === "n8n" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          onClick={() => {
                            setModalError(null);
                            setActiveModal("n8n");
                          }}
                        >
                          Connect n8n
                        </Button>
                      ) : item.type === "crm" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          onClick={() => {
                            setModalError(null);
                            setActiveModal("crm");
                          }}
                        >
                          Connect CRM
                        </Button>
                      ) : item.type === "meta_lead_ads" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          onClick={() => {
                            setModalError(null);
                            setActiveModal("meta");
                          }}
                        >
                          Connect Meta
                        </Button>
                      ) : item.type === "whatsapp" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs"
                          onClick={() => {
                            setModalError(null);
                            setActiveModal("whatsapp");
                          }}
                        >
                          Connect WA
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">Via Webhooks</span>
                      )}
                    </>
                  )}
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
                  Add an endpoint below to receive signed call.completed & CRM events.
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

      {/* Modal: Google Calendar Configuration */}
      {activeModal === "google_calendar" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-primary" /> Connect Google Calendar
                </CardTitle>
                <CardDescription className="text-xs">
                  Sync booked appointments directly to your Google Calendar.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleConnectGoogleCalendar} className="space-y-4">
                <div>
                  <Label htmlFor="google-email" className="text-xs font-medium">Google Account Email</Label>
                  <Input
                    id="google-email"
                    type="email"
                    placeholder="youremail@gmail.com"
                    value={googleEmail}
                    onChange={(e) => setGoogleEmail(e.target.value)}
                    required
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">Calendar events will be created and viewable under this account.</p>
                </div>
                <div>
                  <Label htmlFor="calendar-id" className="text-xs font-medium">Calendar ID</Label>
                  <Input
                    id="calendar-id"
                    placeholder="primary"
                    value={calendarId}
                    onChange={(e) => setCalendarId(e.target.value)}
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">Use primary or your specific Google Calendar ID.</p>
                </div>
                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex flex-col gap-2 pt-2">
                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                      Cancel
                    </Button>
                    <Button type="submit" size="sm" loading={modalLoading}>
                      Connect Calendar
                    </Button>
                  </div>
                  <div className="border-t border-border/40 pt-2 text-center">
                    <button
                      type="button"
                      onClick={() => handleOAuthGoogle("google_calendar")}
                      className="text-[11px] text-primary hover:underline"
                    >
                      Or authorize via official Google OAuth screen &rarr;
                    </button>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal: Google Sheets Configuration */}
      {activeModal === "google_sheets" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-emerald-400" /> Connect Google Sheets
                </CardTitle>
                <CardDescription className="text-xs">
                  Automatically append confirmed appointments and caller leads.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleConnectGoogleSheets} className="space-y-4">
                <div>
                  <Label htmlFor="gsheet-email" className="text-xs font-medium">Google Account Email</Label>
                  <Input
                    id="gsheet-email"
                    type="email"
                    placeholder="youremail@gmail.com"
                    value={googleEmail}
                    onChange={(e) => setGoogleEmail(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="gsheet-id" className="text-xs font-medium">Spreadsheet ID or URL (Optional)</Label>
                  <Input
                    id="gsheet-id"
                    placeholder="1BxiMVs0XRX... or leave blank for auto-sheet"
                    value={sheetsSpreadsheetId}
                    onChange={(e) => setSheetsSpreadsheetId(e.target.value)}
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">Leave empty to connect your default JKR Appointments & Leads sheet.</p>
                </div>
                <div>
                  <Label htmlFor="gsheet-name" className="text-xs font-medium">Sheet Tab Name</Label>
                  <Input
                    id="gsheet-name"
                    placeholder="Appointments & Leads"
                    value={sheetsName}
                    onChange={(e) => setSheetsName(e.target.value)}
                    className="mt-1"
                  />
                </div>
                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex flex-col gap-2 pt-2">
                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                      Cancel
                    </Button>
                    <Button type="submit" size="sm" loading={modalLoading}>
                      Connect Google Sheets
                    </Button>
                  </div>
                  <div className="border-t border-border/40 pt-2 text-center">
                    <button
                      type="button"
                      onClick={() => handleOAuthGoogle("google_sheets")}
                      className="text-[11px] text-primary hover:underline"
                    >
                      Or authorize via official Google OAuth screen &rarr;
                    </button>
                  </div>
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
                  Connect Facebook & Instagram Lead Ads to trigger AI voice outreach.
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
                  <Label htmlFor="meta-token" className="text-xs font-medium">Page Access Token (Optional)</Label>
                  <Input
                    id="meta-token"
                    type="password"
                    placeholder="EAABwz..."
                    value={metaToken}
                    onChange={(e) => setMetaToken(e.target.value)}
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">From Meta Business Manager or Developer portal.</p>
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
                  <MessageSquare className="h-4 w-4 text-emerald-400" /> Connect WhatsApp Business
                </CardTitle>
                <CardDescription className="text-xs">
                  Send automated appointment confirmations and brochures over WhatsApp.
                </CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
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
                  <p className="text-[11px] text-muted-foreground mt-1">E.164 formatted number with country code.</p>
                </div>
                <div>
                  <Label htmlFor="wa-waba" className="text-xs font-medium">WABA Account ID (Optional)</Label>
                  <Input
                    id="wa-waba"
                    placeholder="waba_jkr_prod"
                    value={waWabaId}
                    onChange={(e) => setWaWabaId(e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="wa-token" className="text-xs font-medium">System Access Token (Optional)</Label>
                  <Input
                    id="wa-token"
                    type="password"
                    placeholder="EAABwz..."
                    value={waToken}
                    onChange={(e) => setWaToken(e.target.value)}
                    className="mt-1"
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
                    className="mt-1"
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

      {/* Modal: CRM Configuration */}
      {activeModal === "crm" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Database className="h-4 w-4 text-primary" /> Connect CRM Lead Pipeline
                </CardTitle>
                <CardDescription className="text-xs">Configure your CRM webhook receiver or college ERP endpoint.</CardDescription>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setActiveModal(null)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleVerifyCrm} className="space-y-4">
                <div>
                  <Label htmlFor="crm-name" className="text-xs font-medium">CRM Name</Label>
                  <Input
                    id="crm-name"
                    placeholder="HubSpot / Salesforce / CollPoll"
                    value={crmName}
                    onChange={(e) => setCrmName(e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="crm-url" className="text-xs font-medium">Webhook URL</Label>
                  <Input
                    id="crm-url"
                    placeholder="https://api.hubspot.com/webhooks/v1/leads"
                    value={crmUrl}
                    onChange={(e) => setCrmUrl(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                {modalError ? <p className="text-xs text-danger">{modalError}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setActiveModal(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={modalLoading}>
                    Connect CRM
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
