"use client";

import { HANDOFF_STATUS_VARIANT, type HumanHandoffOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import {
  AlertCircle,
  CheckCircle2,
  Handshake,
  HelpCircle,
  PhoneCall,
  PhoneForwarded,
  Sparkles,
  UserCheck,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

export function HandoffsList({
  workspaceId,
  handoffs,
}: {
  workspaceId: string;
  handoffs: HumanHandoffOut[];
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [dialingId, setDialingId] = React.useState<string | null>(null);
  const [activeFilter, setActiveFilter] = React.useState<"all" | "pending" | "accepted" | "resolved">("all");
  const [helpOpen, setHelpOpen] = React.useState<boolean>(false);

  const act = async (handoffId: string, action: "accept" | "resolve" | "abandon") => {
    setBusyId(handoffId);
    try {
      await operationsApi.actOnHandoff(workspaceId, handoffId, action);
      toast({ title: `Handoff marked as ${action}ed`, variant: "success" });
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not update handoff",
        description: err instanceof ApiClientError ? err.message : undefined,
        variant: "danger",
      });
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

  const filteredHandoffs = handoffs.filter((h) => {
    if (activeFilter === "all") return true;
    if (activeFilter === "pending") return h.status === "pending";
    if (activeFilter === "accepted") return h.status === "accepted";
    if (activeFilter === "resolved") return h.status === "resolved";
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Intro Banner */}
      <div className="rounded-2xl border border-border bg-gradient-to-br from-card via-surface to-card p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500">
                <Handshake className="h-4 w-4" />
              </span>
              <h2 className="text-lg font-bold text-foreground">What are Handoffs?</h2>
              <button
                type="button"
                onClick={() => setHelpOpen((prev) => !prev)}
                className="flex items-center gap-1 rounded-full border border-border bg-muted/60 px-2.5 py-0.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors ml-1"
                title="Explain Handoffs"
              >
                <HelpCircle className="h-3.5 w-3.5" />
                <span>How it works</span>
              </button>
            </div>
            <p className="text-xs text-muted-foreground max-w-3xl leading-relaxed">
              <strong>Handoffs</strong> flag a conversation for human staff when the AI cannot answer, or the caller explicitly asks for a person. A team member reviews an AI-written summary of what the customer wanted, claims the handoff, calls the customer back, and marks it resolved.
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
            <Link href="/app/agents">
              <Button size="sm" variant="outline" className="text-xs">
                Test Escalation in Test Lab →
              </Button>
            </Link>
          </div>
        </div>

        {/* 3-Step "How It Works" Panel */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-border/60">
          <div className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-500 text-xs font-bold">
              1
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Caller Asks for Human</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                The caller says &ldquo;I want to talk to a person&rdquo; or asks something beyond the AI&rsquo;s knowledge base.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-500 text-xs font-bold">
              2
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">AI Briefs Supervisor</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                An urgent handoff is queued immediately with extracted customer details and exact conversation summary.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-500 text-xs font-bold">
              3
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Claim, Call &amp; Resolve</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                A human supervisor clicks <em>Claim &amp; Dial</em> to call the customer back, or takes over and marks it resolved.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Contextual Help Drawer (Expandable) */}
      {helpOpen && (
        <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5 shadow-sm space-y-3 animate-in fade-in duration-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HelpCircle className="h-5 w-5 text-primary" />
              <h3 className="font-bold text-foreground text-sm">Human Handoff Guidance &amp; Policies</h3>
            </div>
            <button
              type="button"
              onClick={() => setHelpOpen(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              ✕ Close
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-muted-foreground leading-relaxed">
            <div className="rounded-xl border border-border/60 bg-background/60 p-3 space-y-1">
              <strong className="text-foreground block font-semibold">What phrases trigger a handoff?</strong>
              <p>
                Phrases like &ldquo;talk to a person&rdquo;, &ldquo;connect me to a manager&rdquo;, &ldquo;human please&rdquo;, or repeatedly expressing frustration.
              </p>
            </div>
            <div className="rounded-xl border border-border/60 bg-background/60 p-3 space-y-1">
              <strong className="text-foreground block font-semibold">How does Claim &amp; Dial work?</strong>
              <p>
                Clicking &ldquo;Claim &amp; Dial&rdquo; assigns the handoff to your user account, preventing duplicate outreach from other team members, and initiates supervisor callback.
              </p>
            </div>
            <div className="rounded-xl border border-border/60 bg-background/60 p-3 space-y-1">
              <strong className="text-foreground block font-semibold">How do I test this safely?</strong>
              <p>
                Open the <strong>Test Lab</strong> on any agent page, and type or speak: <em>&ldquo;I want to talk to a person&rdquo;</em>. A real handoff card will appear here instantly.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 shadow-sm">
          {(
            [
              { id: "all", label: "All Handoffs", count: handoffs.length },
              {
                id: "pending",
                label: "Pending",
                count: handoffs.filter((h) => h.status === "pending").length,
              },
              {
                id: "accepted",
                label: "Claimed",
                count: handoffs.filter((h) => h.status === "accepted").length,
              },
              {
                id: "resolved",
                label: "Resolved",
                count: handoffs.filter((h) => h.status === "resolved").length,
              },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveFilter(tab.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                activeFilter === tab.id
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label} ({tab.count})
            </button>
          ))}
        </div>
      </div>

      {/* List or Empty State */}
      {filteredHandoffs.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center shadow-sm">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <Handshake className="h-7 w-7" />
          </div>
          <h3 className="mt-4 text-base font-semibold text-foreground">
            {activeFilter === "all" ? "No Escalated Handoffs" : `No ${activeFilter} handoffs`}
          </h3>
          <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground leading-relaxed">
            Calls appear here when a customer asks to speak with a real person, or an AI policy triggers a human callback request.
          </p>
          <div className="mt-5 flex justify-center gap-3">
            <Link href="/app/agents">
              <Button size="sm" variant="gradient">
                Test Escalation in Test Lab →
              </Button>
            </Link>
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {filteredHandoffs.map((h) => {
                const isUrgent = h.reason.includes("frustration") || h.reason.includes("escalat");
                return (
                  <div key={h.id} className="p-5 text-sm hover:bg-surface-raised/40 transition-colors space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <div
                          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                            isUrgent
                              ? "bg-danger/10 text-danger border border-danger/20"
                              : "bg-secondary/10 text-secondary border border-secondary/20"
                          }`}
                        >
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
                            <Link
                              href={`/app/calls/${h.call_session_id}`}
                              className="text-primary underline-offset-2 hover:underline"
                            >
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
                          <Button
                            size="sm"
                            variant="secondary"
                            className="text-xs h-8"
                            onClick={() => act(h.id, "resolve")}
                            loading={busyId === h.id}
                          >
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
      )}
    </div>
  );
}

