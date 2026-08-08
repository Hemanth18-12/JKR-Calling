"use client";

import { WebhookEndpointCreate, type IntegrationCatalogItem, type WebhookEndpointOut } from "@jkr/contracts";
import { ApiClientError, integrationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label, useToast } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

function NewWebhookForm({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<WebhookEndpointCreate>({ resolver: zodResolver(WebhookEndpointCreate), defaultValues: { event_types: ["call.completed"] } });

  const onSubmit = async (data: WebhookEndpointCreate) => {
    setFormError(null);
    try {
      await integrationsApi.createWebhook(workspaceId, data);
      reset({ event_types: ["call.completed"] });
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not register webhook.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add webhook endpoint</CardTitle>
        <CardDescription>Fires on call.completed. Payload is HMAC-signed with your secret (X-JKR-Signature header).</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="webhook-url">URL</Label>
            <Input id="webhook-url" placeholder="https://example.com/webhooks/jkr" {...register("url")} />
            <FieldError>{errors.url?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="webhook-secret">Signing secret</Label>
            <Input id="webhook-secret" type="password" placeholder="At least 8 characters" {...register("secret")} />
            <FieldError>{errors.secret?.message}</FieldError>
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Add webhook
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
      router.refresh();
    } catch (err) {
      toast({ title: "Could not deactivate", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center justify-between px-5 py-3 text-sm">
      <div>
        <p className="font-mono text-xs">{endpoint.url}</p>
        <p className="text-xs text-muted-foreground">{endpoint.event_types.join(", ")}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={endpoint.is_active ? "success" : "secondary"}>{endpoint.is_active ? "active" : "inactive"}</Badge>
        {endpoint.is_active ? (
          <Button size="sm" variant="ghost" onClick={deactivate} loading={busy}>
            Deactivate
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function IntegrationsPage({
  workspaceId, catalog, webhooks,
}: {
  workspaceId: string; catalog: IntegrationCatalogItem[]; webhooks: WebhookEndpointOut[];
}) {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.map((item) => (
          <Card key={item.type}>
            <CardContent className="flex items-center justify-between p-4">
              <div>
                <p className="text-sm font-medium">{item.label}</p>
                {item.requires_oauth ? <p className="text-xs text-muted-foreground">Requires OAuth — not configured</p> : null}
              </div>
              <Badge variant={item.status === "connected" ? "success" : "secondary"}>{item.status.replace(/_/g, " ")}</Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Webhook endpoints</CardTitle>
            <CardDescription>{webhooks.length} registered.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {webhooks.length === 0 ? (
              <p className="p-5 text-sm text-muted-foreground">No webhooks registered yet.</p>
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
    </div>
  );
}
