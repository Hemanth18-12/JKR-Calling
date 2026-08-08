"use client";

import { HANDOFF_STATUS_VARIANT, type HumanHandoffOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import { Handshake } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

export function HandoffsList({ workspaceId, handoffs }: { workspaceId: string; handoffs: HumanHandoffOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const act = async (handoffId: string, action: "accept" | "resolve" | "abandon") => {
    setBusyId(handoffId);
    try {
      await operationsApi.actOnHandoff(workspaceId, handoffId, action);
      router.refresh();
    } catch (err) {
      toast({ title: "Could not update handoff", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusyId(null);
    }
  };

  if (handoffs.length === 0) {
    return <EmptyState icon={Handshake} title="No handoffs" description="A call escalates here when a customer asks for a human, or the agent hits a rule that requires one." />;
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="divide-y divide-border">
          {handoffs.map((h) => (
            <div key={h.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
              <div>
                <p className="font-medium">{h.contact_name ?? "Unknown contact"}</p>
                <p className="text-xs text-muted-foreground">
                  {h.reason.replace(/_/g, " ")} ·{" "}
                  <Link href={`/app/calls/${h.call_session_id}`} className="underline-offset-2 hover:underline">
                    view call
                  </Link>
                </p>
                {typeof h.packet.last_customer_utterance === "string" ? (
                  <p className="mt-1 text-xs text-muted-foreground">&quot;{h.packet.last_customer_utterance}&quot;</p>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={HANDOFF_STATUS_VARIANT[h.status] ?? "secondary"}>{h.status}</Badge>
                {h.status === "pending" ? (
                  <Button size="sm" variant="secondary" onClick={() => act(h.id, "accept")} loading={busyId === h.id}>
                    Accept
                  </Button>
                ) : null}
                {h.status === "accepted" ? (
                  <Button size="sm" variant="secondary" onClick={() => act(h.id, "resolve")} loading={busyId === h.id}>
                    Resolve
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
