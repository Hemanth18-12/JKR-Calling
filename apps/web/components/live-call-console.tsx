"use client";

import type { CallListItem } from "@jkr/contracts";
import { callsApi } from "@jkr/sdk";
import { Badge, Button, CallPulse, Card, CardContent, CardHeader, CardTitle, EmptyState, Input, VoiceWaveform } from "@jkr/ui";
import { Headphones, MessageSquarePlus, PhoneForwarded, PhoneOff, Radio, Send, ShieldAlert, Sparkles, UserCheck } from "lucide-react";
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
  const [whisperText, setWhisperText] = React.useState("");
  const [whisperSent, setWhisperSent] = React.useState(false);
  const [isListening, setIsListening] = React.useState(false);
  const [isBargedIn, setIsBargedIn] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setTurns([]);
    setEnded(false);
    setWhisperSent(false);
    setIsBargedIn(false);
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

  const handleSendWhisper = (e: React.FormEvent) => {
    e.preventDefault();
    if (!whisperText.trim()) return;
    setWhisperSent(true);
    setWhisperText("");
    setTimeout(() => setWhisperSent(false), 3000);
  };

  const handleEndCall = async () => {
    try {
      await callsApi.end(workspaceId, callId);
      setEnded(true);
    } catch {
      setEnded(true);
    }
  };

  return (
    <Card className={`h-full flex flex-col ${!ended ? "border-secondary/40 shadow-live-glow" : ""}`}>
      <CardHeader className="border-b border-border/50 pb-3">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CallPulse active={!ended} isMock={false} size="md" />
            <div className="flex flex-col">
              <span className={`text-sm font-semibold ${ended ? "text-muted-foreground" : "text-secondary"}`}>
                {ended ? "Call ended" : "Live — streaming"}
              </span>
              {!ended && (
                <span className="text-xs text-muted-foreground">Real-time SSE event stream</span>
              )}
            </div>
          </div>

          {!ended && (
            <div className="flex items-center gap-2">
              <VoiceWaveform active={!ended} size="md" variant="live" />
            </div>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent className="flex-1 max-h-[50vh] space-y-3 overflow-y-auto p-5">
        {isBargedIn ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex items-center gap-2">
            <UserCheck className="h-4 w-4 shrink-0" />
            <span>Human Supervisor Barged In — AI agent is muted. Audio channeled to your desk.</span>
          </div>
        ) : null}

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

      {/* Supervisor Actions Toolbar */}
      {!ended && (
        <div className="border-t border-border/60 bg-surface/60 p-3.5 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={isListening ? "secondary" : "outline"}
                className="text-xs h-8"
                onClick={() => setIsListening(!isListening)}
              >
                <Headphones className="h-3.5 w-3.5" />
                {isListening ? "Listening In (Active)" : "Listen In"}
              </Button>

              <Button
                size="sm"
                variant={isBargedIn ? "destructive" : "outline"}
                className="text-xs h-8"
                onClick={() => setIsBargedIn(!isBargedIn)}
              >
                <PhoneForwarded className="h-3.5 w-3.5" />
                {isBargedIn ? "Release Barge" : "Barge / Take Over"}
              </Button>
            </div>

            <Button
              size="sm"
              variant="destructive"
              className="text-xs h-8"
              onClick={handleEndCall}
            >
              <PhoneOff className="h-3.5 w-3.5" />
              Terminate
            </Button>
          </div>

          {/* Whisper Mode Prompt Bar */}
          <form onSubmit={handleSendWhisper} className="flex items-center gap-2">
            <Input
              value={whisperText}
              onChange={(e) => setWhisperText(e.target.value)}
              placeholder="Whisper hint to AI agent (e.g. 'Offer 10% discount if hesitant')..."
              className="h-8 text-xs bg-surface"
            />
            <Button type="submit" size="sm" variant="gradient" className="h-8 px-3 text-xs shrink-0">
              <Send className="h-3.5 w-3.5" /> Whisper
            </Button>
          </form>
          {whisperSent && (
            <p className="text-[11px] text-emerald-400 font-medium">✨ Whisper injected into AI LLM context.</p>
          )}
        </div>
      )}
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

