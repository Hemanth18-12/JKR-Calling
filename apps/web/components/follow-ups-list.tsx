"use client";

import { FOLLOW_UP_STATUS_VARIANT, type FollowUpTaskOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import { CalendarClock } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export function FollowUpsList({ workspaceId, tasks }: { workspaceId: string; tasks: FollowUpTaskOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const complete = async (taskId: string) => {
    setBusyId(taskId);
    try {
      await operationsApi.completeFollowUp(workspaceId, taskId);
      router.refresh();
    } catch (err) {
      toast({ title: "Could not update follow-up", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusyId(null);
    }
  };

  if (tasks.length === 0) {
    return <EmptyState icon={CalendarClock} title="No follow-ups yet" description="Post-call intelligence creates these automatically once calls complete." />;
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="divide-y divide-border">
          {tasks.map((t) => (
            <div key={t.id} className="flex items-center justify-between px-5 py-3 text-sm">
              <div>
                <p className="font-medium">{t.contact_name}</p>
                <p className="text-xs text-muted-foreground">
                  {t.channel.replace(/_/g, " ")} · {(t.payload.outcome_category as string | undefined)?.replace(/_/g, " ") ?? "—"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={FOLLOW_UP_STATUS_VARIANT[t.status] ?? "secondary"}>{t.status}</Badge>
                {t.status === "pending" || t.status === "scheduled" ? (
                  <Button size="sm" variant="secondary" onClick={() => complete(t.id)} loading={busyId === t.id}>
                    Mark complete
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
