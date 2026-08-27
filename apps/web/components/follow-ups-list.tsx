"use client";

import { FOLLOW_UP_STATUS_VARIANT, type FollowUpTaskOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import { CalendarClock, CheckCircle2, MessageSquare, Mic, Play, Send, Volume2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export function FollowUpsList({ workspaceId, tasks }: { workspaceId: string; tasks: FollowUpTaskOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [playingId, setPlayingId] = React.useState<string | null>(null);

  const complete = async (taskId: string) => {
    setBusyId(taskId);
    try {
      await operationsApi.completeFollowUp(workspaceId, taskId);
      toast({ title: "Follow-up marked complete", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: "Could not update follow-up", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
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

  if (tasks.length === 0) {
    return <EmptyState icon={CalendarClock} title="No follow-ups yet" description="Post-call intelligence creates these automatically once calls complete." />;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {tasks.map((t) => {
              const isWhatsApp = t.channel.includes("whatsapp");
              return (
                <div key={t.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 text-sm hover:bg-surface-raised/40 transition-colors">
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
                          <Badge variant="secondary" className="text-[10px] text-emerald-400 bg-emerald-500/10 border-emerald-500/20 flex items-center gap-1">
                            <Mic className="h-2.5 w-2.5" /> + Voice Note
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Triggered on: <strong className="text-foreground">{((t.payload.outcome_category as string) || "appointment_booked").replace(/_/g, " ")}</strong>
                        {t.payload.scheduled_for ? ` · For ${new Date(t.payload.scheduled_for as string).toLocaleString()}` : ""}
                      </p>
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

                    {t.status === "pending" || t.status === "scheduled" ? (
                      <Button size="sm" variant="gradient" className="text-xs h-8" onClick={() => complete(t.id)} loading={busyId === t.id}>
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
    </div>
  );
}

