import { integrationsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { IntegrationsPage } from "@/components/integrations-page";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function IntegrationsRoutePage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [catalog, webhooks] = await Promise.all([
    integrationsApi.catalog(workspace.id, { cookieHeader }),
    integrationsApi.listWebhooks(workspace.id, { cookieHeader }),
  ]);

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
        <p className="text-muted-foreground">Outgoing webhooks are real and working; OAuth-based integrations are catalog entries until configured.</p>
      </div>
      <IntegrationsPage workspaceId={workspace.id} catalog={catalog} webhooks={webhooks} />
    </div>
  );
}
