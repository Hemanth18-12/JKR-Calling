"use client";

import type { CallListItem } from "@jkr/contracts";
import { callsApi } from "@jkr/sdk";
import { Badge, CallPulse, Card, CardContent, CardHeader, CardTitle, EmptyState, VoiceWaveform } from "@jkr/ui";
import { Radio } from "lucide-react";
import * as React from "react";

interface LiveTurn {
  turn_ref: string;
  speaker: string;
  text: string;
  is_interrupted: boolean;
}

function LiveTranscript({ workspaceId, callId }: { workspaceId: string; callId: string }) {
  const [turns, setTurns] = React.useState<LiveTurn[]>([]);
  const [ended, setEnded] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setTurns([]);
    setEnded(false);
    const source = new EventSource(callsApi.eventsUrl(workspaceId, callId), { withCredentials: true });

    source.addEventListener("turn", (e) => {
      const turn = JSON.parse((e as MessageEvent).data) as LiveTurn;
      setTurns((prev) => (prev.some((t) => t.turn_ref === turn.turn_ref) ? prev : [...prev, turn]));
    });
    source.addEventListener("call_ended", () => {
      setEnded(true);
      source.close();
    });
    source.addEventListener("error", () => {
      source.close();
    });

    return () => source.close();
  }, [workspaceId, callId]);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  return (
    <Card className={`h-full ${!ended ? "border-secondary/40 shadow-live-glow" : ""}`}>
      <CardHeader className="border-b border-border/50 pb-3">
        <CardTitle className="flex items-center gap-3">
          <CallPulse active={!ended} isMock={false} size="md" />
          <div className="flex flex-col">
            <span className={`text-sm font-semibold ${ended ? "text-muted-foreground" : "text-secondary"}`}>
              {ended ? "Call ended" : "Live — streaming"}
            </span>
            {!ended && (
              <span className="text-xs text-muted-foreground">Turns appear as they happen via SSE</span>
            )}
          </div>
          {!ended && (
            <div className="ml-auto">
              <VoiceWaveform active={!ended} size="md" variant="live" />
            </div>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-[60vh] space-y-3 overflow-y-auto p-5">
        {turns.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <VoiceWaveform active size="lg" variant="live" />
            <p className="text-sm text-muted-foreground">Waiting for the first turn…</p>
          </div>
        ) : (
          turns.map((t) => (
            <div key={t.turn_ref} className={`flex ${t.speaker === "agent" ? "justify-start" : "justify-end"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
                  t.speaker === "agent"
                    ? "bg-surface-raised border border-border/60"
                    : "bg-primary/15 border border-primary/20"
                } ${t.is_interrupted ? "opacity-60 line-through" : ""}`}
              >
                <p className={`mb-1 text-[10px] font-semibold uppercase tracking-wider ${t.speaker === "agent" ? "text-secondary" : "text-primary"}`}>
                  {t.speaker}
                </p>
                <p className="leading-relaxed text-foreground">{t.text}</p>
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </CardContent>
    </Card>
  );
}

export function LiveCallConsole({ workspaceId, initialCalls }: { workspaceId: string; initialCalls: CallListItem[] }) {
  const [selected, setSelected] = React.useState<string | null>(initialCalls[0]?.call_id ?? null);

  if (initialCalls.length === 0) {
    return (
      <EmptyState
        icon={Radio}
        title="No calls in progress"
        description="Start a Test Lab call or launch a campaign — it'll show up here while it's running."
      />
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Call selector */}
      <Card className="lg:col-span-1">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <span className="flex h-2 w-2 items-center">
              <span className="absolute inline-flex h-3 w-3 animate-ping rounded-full bg-secondary/50" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-secondary" />
            </span>
            In progress
            <Badge variant="live" className="ml-auto">{initialCalls.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 p-0 pb-2">
          {initialCalls.map((c) => (
            <button
              key={c.call_id}
              onClick={() => setSelected(c.call_id)}
              className={`flex w-full items-center justify-between px-4 py-3 text-left text-sm transition-colors hover:bg-surface-raised ${
                selected === c.call_id ? "border-l-2 border-secondary bg-secondary/5 pl-3.5" : ""
              }`}
            >
              <div className="flex items-center gap-2.5">
                <CallPulse active size="sm" />
                <span className="font-medium text-foreground">{c.contact_name ?? "Test call"}</span>
              </div>
              <Badge variant="live">{c.status.replace(/_/g, " ")}</Badge>
            </button>
          ))}
        </CardContent>
      </Card>

      {/* Transcript panel */}
      <div className="lg:col-span-2">
        {selected ? <LiveTranscript workspaceId={workspaceId} callId={selected} /> : null}
      </div>
    </div>
  );
}
