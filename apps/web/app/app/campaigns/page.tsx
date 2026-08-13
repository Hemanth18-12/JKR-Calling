import { CAMPAIGN_STATUS_VARIANT } from "@jkr/contracts";
import { campaignsApi } from "@jkr/sdk";
import { Badge, buttonVariants, Card, CardContent, EmptyState } from "@jkr/ui";
import { Megaphone, Plus, Zap } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";

const STATUS_ACCENT: Record<string, string> = {
  active: "border-secondary/30 bg-secondary/5",
  draft: "border-border",
  paused: "border-amber-500/30 bg-amber-500/5",
  completed: "border-border",
  cancelled: "border-danger/20 bg-danger/5",
};

export default async function CampaignsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const campaigns = await campaignsApi.list(workspace.id, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">Campaigns</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Every dispatch runs the 10-check safety gate — see docs/SECURITY_AND_COMPLIANCE.md.
          </p>
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
          {campaigns.map((c, i) => (
            <Link key={c.id} href={`/app/campaigns/${c.id}`}>
              <Card
                className={`stagger-${Math.min(i + 1, 8)} group h-full transition-all duration-200 hover:-translate-y-1 hover:shadow-lg ${
                  STATUS_ACCENT[c.status] ?? "border-border"
                }`}
              >
                <CardContent className="p-5">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                      <Megaphone className="h-4 w-4 text-primary" />
                    </div>
                    <Badge
                      variant={
                        c.status === "active"
                          ? "live"
                          : c.status === "paused"
                            ? "warning"
                            : c.status === "completed"
                              ? "success"
                              : "secondary"
                      }
                    >
                      {c.status}
                    </Badge>
                  </div>
                  <h3 className="font-display font-semibold text-foreground">{c.name}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{c.objective.replace(/_/g, " ")}</p>
                  <div className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground/70">
                    <Zap className="h-3 w-3" />
                    max {c.max_attempts} attempts
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
