import { CALL_STATUS_VARIANT } from "@jkr/contracts";
import { callsApi } from "@jkr/sdk";
import { Badge, Card, CardContent, EmptyState } from "@jkr/ui";
import { Phone } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";

export default async function CallsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const calls = await callsApi.list(workspace.id, undefined, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Calls</h1>
        <p className="text-muted-foreground">Every call this workspace has run, mock or otherwise.</p>
      </div>

      {calls.length === 0 ? (
        <EmptyState icon={Phone} title="No calls yet" description="Start a Test Lab call or launch a campaign to see calls here." />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {calls.map((c) => (
                <Link key={c.call_id} href={`/app/calls/${c.call_id}`} className="flex items-center justify-between px-5 py-3 text-sm hover:bg-surface-raised">
                  <div>
                    <p className="font-medium">{c.contact_name ?? "Test call"}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.direction} · {c.started_at ? new Date(c.started_at).toLocaleString() : "not started"}
                      {c.duration_seconds !== null ? ` · ${c.duration_seconds}s` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.outcome_category ? <Badge variant="outline">{c.outcome_category.replace(/_/g, " ")}</Badge> : null}
                    <Badge variant={CALL_STATUS_VARIANT[c.status] ?? "secondary"}>{c.status.replace(/_/g, " ")}</Badge>
                  </div>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
