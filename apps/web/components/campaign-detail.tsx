"use client";

import {
  CAMPAIGN_CONTACT_STATUS_VARIANT,
  CAMPAIGN_STATUS_VARIANT,
  type CampaignContactOut,
  type CampaignDetail as CampaignDetailType,
  type ContactOut,
  type DryRunResponse,
} from "@jkr/contracts";
import { ApiClientError, campaignsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Label, useToast } from "@jkr/ui";
import { AlertTriangle, CheckCircle2, PhoneCall, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { BackButton } from "./back-button";

// days_of_week values follow Python's datetime.weekday(): 0=Monday..6=Sunday
// (see packages/db/jkr_db/safety_gate.py within_calling_hours).
const DAY_LABELS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

function SchedulePanel({
  workspaceId, campaignId, schedule,
}: { workspaceId: string; campaignId: string; schedule: CampaignDetailType["schedule"] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [start, setStart] = React.useState(schedule?.calling_window_start?.slice(0, 5) ?? "09:00");
  const [end, setEnd] = React.useState(schedule?.calling_window_end?.slice(0, 5) ?? "20:00");
  const [days, setDays] = React.useState<Set<number>>(new Set(schedule?.days_of_week ?? [0, 1, 2, 3, 4, 5]));
  const [busy, setBusy] = React.useState(false);

  const toggleDay = (value: number) => {
    setDays((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const save = async () => {
    setBusy(true);
    try {
      await campaignsApi.updateSchedule(workspaceId, campaignId, {
        calling_window_start: `${start}:00`,
        calling_window_end: `${end}:00`,
        days_of_week: Array.from(days).sort(),
      });
      toast({ title: "Calling hours updated", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: "Could not update calling hours", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Calling hours</CardTitle>
        <CardDescription>
          The safety gate blocks dispatch outside this window ({schedule?.timezone ?? "Asia/Kolkata"}). Applies only to this campaign.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="schedule-start">From</Label>
            <input
              id="schedule-start"
              type="time"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="flex h-9 w-full rounded-md border border-border bg-surface px-2 text-sm"
            />
          </div>
          <div>
            <Label htmlFor="schedule-end">To</Label>
            <input
              id="schedule-end"
              type="time"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="flex h-9 w-full rounded-md border border-border bg-surface px-2 text-sm"
            />
          </div>
        </div>
        <div>
          <Label>Days</Label>
          <div className="mt-1 flex flex-wrap gap-1">
            {DAY_LABELS.map((d) => (
              <button
                key={d.value}
                type="button"
                onClick={() => toggleDay(d.value)}
                className={`rounded-md border px-2 py-1 text-xs ${
                  days.has(d.value)
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-surface text-muted-foreground"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
        <Button onClick={save} loading={busy} disabled={days.size === 0} size="sm" className="w-full">
          Save calling hours
        </Button>
      </CardContent>
    </Card>
  );
}

function DryRunPanel({ workspaceId, campaignId }: { workspaceId: string; campaignId: string }) {
  const [result, setResult] = React.useState<DryRunResponse | null>(null);
  const [loading, setLoading] = React.useState(false);

  const run = async () => {
    setLoading(true);
    try {
      setResult(await campaignsApi.dryRun(workspaceId, campaignId));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Dry-run</CardTitle>
        <CardDescription>Runs the full safety gate for every contact — no side effects, nothing dispatched.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={run} loading={loading} variant="secondary">
          Run dry-run
        </Button>
        {result ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              {result.would_dispatch} of {result.evaluated} would dispatch · {result.blocked} blocked
            </p>
            <ul className="space-y-2">
              {result.results.map((r) => (
                <li key={r.campaign_contact_id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                  <span>{r.contact_name}</span>
                  {r.would_dispatch ? (
                    <span className="flex items-center gap-1 text-success"><CheckCircle2 className="h-4 w-4" /> would dispatch</span>
                  ) : (
                    <span className="flex items-center gap-1 text-danger"><XCircle className="h-4 w-4" /> blocked: {r.failed_check}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function AddContactsPanel({ workspaceId, campaignId, allContacts, addedContactIds }: {
  workspaceId: string; campaignId: string; allContacts: ContactOut[]; addedContactIds: Set<string>;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [busy, setBusy] = React.useState(false);
  const available = allContacts.filter((c) => !addedContactIds.has(c.id));

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const add = async () => {
    setBusy(true);
    try {
      const result = await campaignsApi.addContacts(workspaceId, campaignId, { contact_ids: Array.from(selected) });
      toast({ title: `${result.added} contact${result.added === 1 ? "" : "s"} added`, variant: "success" });
      setSelected(new Set());
      router.refresh();
    } catch (err) {
      toast({ title: "Could not add contacts", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  if (available.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Add contacts</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Every workspace contact is already in this campaign.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add contacts</CardTitle>
        <CardDescription>{available.length} contact{available.length === 1 ? "" : "s"} not yet in this campaign.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="max-h-64 space-y-1 overflow-y-auto">
          {available.map((c) => (
            <label key={c.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-raised">
              <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
              <span>{c.full_name}</span>
              <span className="text-xs text-muted-foreground">{c.phone_masked}</span>
              {c.is_suppressed ? <Badge variant="danger">suppressed</Badge> : null}
            </label>
          ))}
        </div>
        <Button onClick={add} disabled={selected.size === 0} loading={busy} className="w-full" size="sm">
          Add {selected.size || ""} selected
        </Button>
      </CardContent>
    </Card>
  );
}

export function CampaignDetail({
  workspaceId, campaign, campaignContacts, allContacts,
}: {
  workspaceId: string; campaign: CampaignDetailType; campaignContacts: CampaignContactOut[]; allContacts: ContactOut[];
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [busy, setBusy] = React.useState(false);
  const [showDeleteModal, setShowDeleteModal] = React.useState(false);

  // Auto-refresh contact status while active
  React.useEffect(() => {
    if (campaign.status !== "active") return;
    const interval = setInterval(() => {
      router.refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, [campaign.status, router]);

  const act = async (action: "launch" | "pause" | "cancel") => {
    setBusy(true);
    try {
      await campaignsApi[action](workspaceId, campaign.id);
      toast({ title: `Campaign ${action === "launch" ? "launched" : action + "d"}`, variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: `Could not ${action} campaign`, description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    try {
      await campaignsApi.delete(workspaceId, campaign.id);
      toast({ title: "Campaign deleted", variant: "success" });
      router.push(`/app/campaigns`);
    } catch (err) {
      toast({ title: "Could not delete campaign", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
      setBusy(false);
    }
  };

  const addedContactIds = new Set(campaignContacts.map((c) => c.contact_id));
  const isTerminal = ["cancelled", "completed", "failed", "draft"].includes(campaign.status);

  return (
    <div className="space-y-6">
      {/* Execution Mode Banner */}
      <div className="flex items-center justify-between rounded-xl border border-secondary/30 bg-secondary/5 p-4 text-sm">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-secondary/20 p-2 text-secondary">
            <PhoneCall className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <p className="font-medium text-foreground">
              Mock Telephony Mode Active
            </p>
            <p className="text-xs text-muted-foreground">
              Dispatches use local simulated call sessions. Completed calls automatically record full transcripts, extraction summaries, and analytics in your Calls log.
            </p>
          </div>
        </div>
        <Link href="/app/calls">
          <Button variant="outline" size="sm" className="whitespace-nowrap gap-1">
            View Calls Log &rarr;
          </Button>
        </Link>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <BackButton fallbackHref="/app/campaigns" label="Campaigns" />
            <h1 className="text-2xl font-bold tracking-tight">{campaign.name}</h1>
            <Badge variant={CAMPAIGN_STATUS_VARIANT[campaign.status] ?? "secondary"}>{campaign.status}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{campaign.objective.replace(/_/g, " ")} · max {campaign.max_attempts} attempts</p>
        </div>
        <div className="flex gap-2">
          {campaign.status === "draft" || campaign.status === "paused" ? (
            <Button onClick={() => act("launch")} loading={busy} className="bg-primary">Launch</Button>
          ) : null}
          {campaign.status === "active" ? (
            <Button variant="secondary" onClick={() => act("pause")} loading={busy}>Pause</Button>
          ) : null}
          {campaign.status === "active" || campaign.status === "paused" ? (
            <Button variant="destructive" onClick={() => act("cancel")} loading={busy}>Cancel</Button>
          ) : null}
          {isTerminal ? (
            <Button variant="outline" className="text-danger hover:bg-danger/10 border-danger/30" onClick={() => setShowDeleteModal(true)} loading={busy}>
              <Trash2 className="h-4 w-4 mr-1" /> Delete
            </Button>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {campaign.contact_counts.map((c) => (
          <Badge key={c.status} variant={CAMPAIGN_CONTACT_STATUS_VARIANT[c.status] ?? "secondary"}>
            {c.count} {c.status.replace(/_/g, " ")}
          </Badge>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Contacts</CardTitle>
          </CardHeader>
          <CardContent>
            {campaignContacts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No contacts added yet.</p>
            ) : (
              <div className="divide-y divide-border">
                {campaignContacts.map((cc) => (
                  <div key={cc.id} className="flex items-center justify-between py-2.5 text-sm">
                    <div>
                      <p className="font-medium">{cc.contact_name}</p>
                      <p className="text-xs text-muted-foreground">{cc.phone_masked}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{cc.attempt_count} attempt{cc.attempt_count === 1 ? "" : "s"}</span>
                      <Badge variant={CAMPAIGN_CONTACT_STATUS_VARIANT[cc.status] ?? "secondary"}>{cc.status.replace(/_/g, " ")}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <div className="space-y-6">
          <DryRunPanel workspaceId={workspaceId} campaignId={campaign.id} />
          <SchedulePanel workspaceId={workspaceId} campaignId={campaign.id} schedule={campaign.schedule} />
          <AddContactsPanel workspaceId={workspaceId} campaignId={campaign.id} allContacts={allContacts} addedContactIds={addedContactIds} />
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-danger">
              <AlertTriangle className="h-6 w-6 shrink-0" />
              <h2 className="text-lg font-semibold">Delete Campaign</h2>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Are you sure you want to delete <strong className="text-foreground">{campaign.name}</strong>? This will permanently remove the campaign configuration, schedule, contacts list, and dry-run history.
            </p>
            <p className="text-xs text-amber font-medium bg-amber/10 border border-amber/20 rounded-md p-2.5">
              Note: Call records already made during this campaign will NOT be deleted.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowDeleteModal(false)} disabled={busy}>
                Cancel
              </Button>
              <Button variant="destructive" size="sm" onClick={handleDelete} loading={busy}>
                Confirm Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

