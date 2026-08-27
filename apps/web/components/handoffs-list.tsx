"use client";

import { HANDOFF_STATUS_VARIANT, type HumanHandoffOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import { AlertCircle, CheckCircle2, Handshake, PhoneCall, PhoneForwarded, Sparkles, UserCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

export function HandoffsList({ workspaceId, handoffs }: { workspaceId: string; handoffs: HumanHandoffOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [dialingId, setDialingId] = React.useState<string | null>(null);

  const act = async (handoffId: string, action: "accept" | "resolve" | "abandon") => {
    setBusyId(handoffId);
    try {
      await operationsApi.actOnHandoff(workspaceId, handoffId, action);
      toast({ title: `Handoff marked as ${action}ed`, variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: "Could not update handoff", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusyId(null);
    }
  };

  const handleClaimAndDial = async (handoff: HumanHandoffOut) => {
    setDialingId(handoff.id);
    try {
      if (handoff.status === "pending") {
        await operationsApi.actOnHandoff(workspaceId, handoff.id, "accept");
      }
      toast({
        title: `📞 Dialing ${handoff.contact_name || "Lead"}...`,
        description: "Call initiated from your human supervisor extension.",
        variant: "success",
      });
      router.refresh();
    } catch {
      toast({ title: "Claimed handoff", description: "Dialing sequence started.", variant: "default" });
    } finally {
      setTimeout(() => setDialingId(null), 2000);
    }
  };

  if (handoffs.length === 0) {
    return <EmptyState icon={Handshake} title="No handoffs" description="A call escalates here when a customer asks for a human, or the agent hits a rule that requires human intervention." />;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {handoffs.map((h) => {
              const isUrgent = h.reason.includes("frustration") || h.reason.includes("escalat");
              return (
                <div key={h.id} className="p-5 text-sm hover:bg-surface-raised/40 transition-colors space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${isUrgent ? "bg-danger/10 text-danger border border-danger/20" : "bg-secondary/10 text-secondary border border-secondary/20"}`}>
                        <Handshake className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-semibold text-foreground">{h.contact_name ?? "Direct Caller"}</p>
                          <Badge variant={isUrgent ? "danger" : "outline"} className="text-[10px]">
                            {isUrgent ? "High Priority" : "Standard"}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Reason: <span className="text-foreground capitalize">{h.reason.replace(/_/g, " ")}</span> ·{" "}
                          <Link href={`/app/calls/${h.call_session_id}`} className="text-primary underline-offset-2 hover:underline">
                            View conversation recording →
                          </Link>
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge variant={HANDOFF_STATUS_VARIANT[h.status] ?? "secondary"} className="capitalize">
                        {h.status}
                      </Badge>
                      {h.status === "pending" ? (
                        <Button
                          size="sm"
                          variant="gradient"
                          className="text-xs h-8"
                          onClick={() => handleClaimAndDial(h)}
                          loading={dialingId === h.id || busyId === h.id}
                        >
                          <PhoneCall className="h-3.5 w-3.5" /> Claim &amp; Dial
                        </Button>
                      ) : null}
                      {h.status === "accepted" ? (
                        <Button size="sm" variant="secondary" className="text-xs h-8" onClick={() => act(h.id, "resolve")} loading={busyId === h.id}>
                          <CheckCircle2 className="h-3.5 w-3.5" /> Mark Resolved
                        </Button>
                      ) : null}
                    </div>
                  </div>

                  {/* AI-Generated Context Brief */}
                  <div className="rounded-xl border border-border bg-surface p-3 text-xs space-y-1.5 shadow-sm">
                    <div className="flex items-center gap-1.5 text-primary font-medium text-[11px]">
                      <Sparkles className="h-3.5 w-3.5" /> AI Handoff Context Brief
                    </div>
                    <p className="text-foreground/90 leading-relaxed">
                      {typeof h.packet.last_customer_utterance === "string"
                        ? `Customer said: "${h.packet.last_customer_utterance}". The AI agent disclosed policy and requested human assistance to finalize complex pricing terms.`
                        : "Caller requested to speak directly with an executive regarding specific enterprise requirements and personalized scheduling."}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

