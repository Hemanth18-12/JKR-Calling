import { CAMPAIGN_STATUS_VARIANT } from "@jkr/contracts";
import { campaignsApi } from "@jkr/sdk";
import { Badge, buttonVariants, Card, CardContent, EmptyState } from "@jkr/ui";
import { Megaphone, Plus } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";

export default async function CampaignsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const campaigns = await campaignsApi.list(workspace.id, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
          <p className="text-muted-foreground">Every dispatch runs the 10-check safety gate — see docs/SECURITY_AND_COMPLIANCE.md.</p>
        </div>
        <Link href="/app/campaigns/new" className={buttonVariants({ variant: "gradient" })}>
          <Plus className="h-4 w-4" /> New campaign
        </Link>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="No campaigns yet"
          description="Create a campaign, add contacts, dry-run it, then launch."
          action={
            <Link href="/app/campaigns/new" className={buttonVariants({ variant: "gradient" })}>
              <Plus className="h-4 w-4" /> New campaign
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {campaigns.map((c) => (
            <Link key={c.id} href={`/app/campaigns/${c.id}`}>
              <Card className="h-full transition-colors hover:border-primary/50">
                <CardContent className="p-5">
                  <div className="mb-2 flex items-center justify-between">
                    <Megaphone className="h-5 w-5 text-primary" />
                    <Badge variant={CAMPAIGN_STATUS_VARIANT[c.status] ?? "secondary"}>{c.status}</Badge>
                  </div>
                  <h3 className="font-semibold">{c.name}</h3>
                  <p className="text-sm text-muted-foreground">{c.objective.replace(/_/g, " ")}</p>
                  <p className="mt-2 font-mono text-xs text-muted-foreground">max {c.max_attempts} attempts</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
