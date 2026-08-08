import { complianceApi } from "@jkr/sdk";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@jkr/ui";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";

export default async function CompliancePage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [overview, auditLog] = await Promise.all([
    complianceApi.overview(workspace.id, { cookieHeader }),
    complianceApi.auditLog(workspace.id, 50, { cookieHeader }),
  ]);

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compliance</h1>
        <p className="text-muted-foreground">Consent, suppression, calling-hours policy, and the audit trail — see docs/SECURITY_AND_COMPLIANCE.md.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Calling hours</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">
              {overview.calling_window_start.slice(0, 5)}–{overview.calling_window_end.slice(0, 5)}
            </p>
            <p className="text-xs text-muted-foreground">{overview.timezone} · edit in Settings</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Contacts</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">{overview.total_contacts}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Suppressed</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">{overview.suppressed_contacts}</p>
            <Link href="/app/contacts" className="text-xs text-primary underline-offset-2 hover:underline">
              manage in Contacts
            </Link>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Consent on file</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1">
            {overview.consent_purpose_breakdown.length === 0 ? (
              <p className="text-sm text-muted-foreground">None yet</p>
            ) : (
              overview.consent_purpose_breakdown.map((c) => (
                <Badge key={c.purpose} variant="outline">
                  {c.purpose}: {c.count}
                </Badge>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>Every successful mutating action in this workspace, most recent first.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {auditLog.length === 0 ? (
            <p className="p-5 text-sm text-muted-foreground">No audited actions yet.</p>
          ) : (
            <div className="divide-y divide-border">
              {auditLog.map((entry) => (
                <div key={entry.id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                  <div>
                    <span className="font-mono text-xs">{entry.action}</span>
                    <p className="text-xs text-muted-foreground">
                      {entry.actor_name ?? "system"} · {new Date(entry.created_at).toLocaleString()}
                    </p>
                  </div>
                  <Badge variant="outline">{entry.resource_type}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
