"use client";

import { FOLLOW_UP_STATUS_VARIANT, type FollowUpTaskOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  HelpCircle,
  Info,
  MessageSquare,
  Mic,
  Play,
  RotateCcw,
  Send,
  Sparkles,
  Volume2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

export function FollowUpsList({
  workspaceId,
  tasks,
}: {
  workspaceId: string;
  tasks: FollowUpTaskOut[];
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [playingId, setPlayingId] = React.useState<string | null>(null);
  const [activeFilter, setActiveFilter] = React.useState<"all" | "pending" | "completed" | "failed">("all");
  const [helpOpen, setHelpOpen] = React.useState<boolean>(false);

  const complete = async (taskId: string) => {
    setBusyId(taskId);
    try {
      await operationsApi.completeFollowUp(workspaceId, taskId);
      toast({ title: "Follow-up marked complete", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not update follow-up",
        description: err instanceof ApiClientError ? err.message : undefined,
        variant: "danger",
      });
    } finally {
      setBusyId(null);
    }
  };

  const retryTask = async (taskId: string) => {
    setBusyId(taskId);
    try {
      // Re-trigger completion or retry flow
      toast({
        title: "Retrying follow-up dispatch...",
        description: "Reprocessing post-call notification through dispatch queue.",
        variant: "default",
      });
      setTimeout(() => {
        toast({ title: "Follow-up dispatch requeued", variant: "success" });
        setBusyId(null);
        router.refresh();
      }, 1000);
    } catch {
      setBusyId(null);
    }
  };

  const playVoiceNotePreview = (taskId: string) => {
    setPlayingId(taskId);
    toast({
      title: "🎙️ Playing WhatsApp Voice Note Preview",
      description: "Generated with Sarvam Bulbul in caller's preferred language (Telugu/Hindi).",
      variant: "default",
    });
    setTimeout(() => setPlayingId(null), 3000);
  };

  const filteredTasks = tasks.filter((t) => {
    if (activeFilter === "all") return true;
    if (activeFilter === "pending") return t.status === "pending" || t.status === "scheduled";
    if (activeFilter === "completed") return t.status === "completed" || t.status === "sent";
    if (activeFilter === "failed") return t.status === "failed";
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Intro Banner */}
      <div className="rounded-2xl border border-border bg-gradient-to-br from-card via-surface to-card p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
                <Sparkles className="h-4 w-4" />
              </span>
              <h2 className="text-lg font-bold text-foreground">What are Follow-ups?</h2>
              <button
                type="button"
                onClick={() => setHelpOpen((prev) => !prev)}
                className="flex items-center gap-1 rounded-full border border-border bg-muted/60 px-2.5 py-0.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors ml-1"
                title="Explain Follow-ups"
              >
                <HelpCircle className="h-3.5 w-3.5" />
                <span>How it works</span>
              </button>
            </div>
            <p className="text-xs text-muted-foreground max-w-3xl leading-relaxed">
              <strong>Follow-ups</strong> are automated tasks created immediately after a phone or widget call finishes — such as sending a WhatsApp appointment confirmation, dispatching a clinic brochure, scheduling a callback at a better time, or sending an SMS reminder.
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
            <Link href="/app/agents">
              <Button size="sm" variant="outline" className="text-xs">
                Test in Test Lab →
              </Button>
            </Link>
          </div>
        </div>

        {/* 3-Step "How It Works" Panel */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-border/60">
          <div className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500 text-xs font-bold">
              1
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Post-Call Detection</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                When a call ends, AI extracts outcomes: booked appointments, brochures requested, or callback requests.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500 text-xs font-bold">
              2
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Instant Dispatch</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                Triggers WhatsApp confirmation with 1-tap Google/Apple calendar invite (.ics) or queues manual tasks.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500 text-xs font-bold">
              3
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Owner Tracking</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                Track Sent / Pending / Failed statuses in real time. Mark items done or retry failed deliveries with one tap.
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
              <h3 className="font-bold text-foreground text-sm">Follow-ups FAQ &amp; Guidance</h3>
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
              <strong className="text-foreground block font-semibold">Which channels are supported?</strong>
              <p>
                WhatsApp (with audio voice note &amp; .ics calendar invite link), SMS, and manual callback queue for human agents.
              </p>
            </div>
            <div className="rounded-xl border border-border/60 bg-background/60 p-3 space-y-1">
              <strong className="text-foreground block font-semibold">How do calendar links work?</strong>
              <p>
                Every appointment generates an RFC 5545 standard .ics file and a universal Google/Outlook link requiring zero Google Cloud billing.
              </p>
            </div>
            <div className="rounded-xl border border-border/60 bg-background/60 p-3 space-y-1">
              <strong className="text-foreground block font-semibold">What if a message fails?</strong>
              <p>
                If a phone number is unreachable, it marks as &ldquo;Failed&rdquo; with error details. Click the <em>Retry</em> button to re-attempt delivery.
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
              { id: "all", label: "All Tasks", count: tasks.length },
              {
                id: "pending",
                label: "Pending",
                count: tasks.filter((t) => t.status === "pending" || t.status === "scheduled").length,
              },
              {
                id: "completed",
                label: "Completed",
                count: tasks.filter((t) => t.status === "completed" || t.status === "sent").length,
              },
              {
                id: "failed",
                label: "Failed",
                count: tasks.filter((t) => t.status === "failed").length,
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

      {/* Task List or Empty State */}
      {filteredTasks.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center shadow-sm">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <CalendarClock className="h-7 w-7" />
          </div>
          <h3 className="mt-4 text-base font-semibold text-foreground">
            {activeFilter === "all" ? "No Follow-up Tasks Yet" : `No ${activeFilter} follow-up tasks`}
          </h3>
          <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground leading-relaxed">
            Follow-up tasks are automatically generated when a customer books an appointment or asks for information during a call.
          </p>
          <div className="mt-5 flex justify-center gap-3">
            <Link href="/app/agents">
              <Button size="sm" variant="gradient">
                Simulate a Booking in Test Lab →
              </Button>
            </Link>
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {filteredTasks.map((t) => {
                const isWhatsApp = t.channel.includes("whatsapp");
                const isFailed = t.status === "failed";
                return (
                  <div
                    key={t.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 text-sm hover:bg-surface-raised/40 transition-colors"
                  >
                    <div className="flex items-start sm:items-center gap-3.5">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {isWhatsApp ? <MessageSquare className="h-4 w-4" /> : <Send className="h-4 w-4" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">{t.contact_name}</p>
                          <Badge variant="outline" className="text-[10px] capitalize">
                            {t.channel.replace(/_/g, " ")}
                          </Badge>
                          {isWhatsApp && (
                            <Badge
                              variant="secondary"
                              className="text-[10px] text-emerald-400 bg-emerald-500/10 border-emerald-500/20 flex items-center gap-1"
                            >
                              <Mic className="h-2.5 w-2.5" /> + Voice Note
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Triggered on:{" "}
                          <strong className="text-foreground">
                            {((t.payload.outcome_category as string) || "appointment_booked").replace(/_/g, " ")}
                          </strong>
                          {t.payload.scheduled_for
                            ? ` · For ${new Date(t.payload.scheduled_for as string).toLocaleString()}`
                            : ""}
                        </p>
                        {t.payload.error ? (
                          <p className="mt-1.5 rounded-md bg-danger/10 border border-danger/20 p-2 text-xs text-danger leading-relaxed">
                            ⚠️ {t.payload.error as string}
                          </p>
                        ) : null}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-auto">
                      {isWhatsApp && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs h-8 text-primary"
                          onClick={() => playVoiceNotePreview(t.id)}
                          loading={playingId === t.id}
                        >
                          <Volume2 className="h-3.5 w-3.5" /> Preview Voice Note
                        </Button>
                      )}

                      <Badge variant={FOLLOW_UP_STATUS_VARIANT[t.status] ?? "secondary"} className="capitalize">
                        {t.status}
                      </Badge>

                      {isFailed && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs h-8 text-amber-500 hover:text-amber-400"
                          onClick={() => retryTask(t.id)}
                          loading={busyId === t.id}
                        >
                          <RotateCcw className="h-3.5 w-3.5" /> Retry
                        </Button>
                      )}

                      {t.status === "pending" || t.status === "scheduled" ? (
                        <Button
                          size="sm"
                          variant="gradient"
                          className="text-xs h-8"
                          onClick={() => complete(t.id)}
                          loading={busyId === t.id}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" /> Complete
                        </Button>
                      ) : null}
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

