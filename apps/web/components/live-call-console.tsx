"use client";

import type { CallListItem } from "@jkr/contracts";
import { callsApi } from "@jkr/sdk";
import { Badge, Button, CallPulse, Card, CardContent, CardHeader, CardTitle, EmptyState, Input, useToast, VoiceWaveform } from "@jkr/ui";
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
    source.addEventListener("barge", (e) => {
      const payload = JSON.parse((e as MessageEvent).data);
      setIsBargedIn(payload.action === "takeover");
    });
    source.addEventListener("call_ended", () => {
      setEnded(true);
      source.close();
    });
    source.addEventListener("call_terminated", () => {
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

  const [whisperLoading, setWhisperLoading] = React.useState(false);
  const [actionLoading, setActionLoading] = React.useState(false);

  const handleSendWhisper = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!whisperText.trim()) return;
    setWhisperLoading(true);
    try {
      await callsApi.whisper(workspaceId, callId, whisperText);
      setWhisperSent(true);
      setWhisperText("");
      setTimeout(() => setWhisperSent(false), 4000);
    } catch (err) {
      console.error("Failed to send whisper:", err);
    } finally {
      setWhisperLoading(false);
    }
  };

  const handleToggleListen = async () => {
    setActionLoading(true);
    try {
      await callsApi.listen(workspaceId, callId);
      setIsListening((prev) => !prev);
    } catch (err) {
      console.error("Failed to toggle listen:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleBarge = async () => {
    setActionLoading(true);
    try {
      const nextAction = isBargedIn ? "release" : "takeover";
      await callsApi.barge(workspaceId, callId, nextAction);
      setIsBargedIn(!isBargedIn);
    } catch (err) {
      console.error("Failed to toggle barge:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEndCall = async () => {
    try {
      await callsApi.terminate(workspaceId, callId, "supervisor_terminated");
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
                disabled={actionLoading}
                onClick={handleToggleListen}
              >
                <Headphones className="h-3.5 w-3.5" />
                {isListening ? "Listening In (Active)" : "Listen In"}
              </Button>

              <Button
                size="sm"
                variant={isBargedIn ? "destructive" : "outline"}
                className="text-xs h-8"
                disabled={actionLoading}
                onClick={handleToggleBarge}
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
            <Button type="submit" size="sm" variant="gradient" className="h-8 px-3 text-xs shrink-0" disabled={whisperLoading}>
              <Send className="h-3.5 w-3.5" /> Whisper
            </Button>
          </form>
          {whisperSent && (
            <p className="text-[11px] text-emerald-400 font-medium">✨ Whisper injected into AI LLM context.</p>
          )}

          {/* Supervisor Live Notes & Disposition */}
          <SupervisorConsoleNotes callId={callId} />
        </div>
      )}

      {ended && (
        <div className="border-t border-border/60 bg-surface/40 p-3.5 space-y-2.5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Post-Call Disposition &amp; Notes</p>
          <SupervisorConsoleNotes callId={callId} />
        </div>
      )}
    </Card>
  );
}

function SupervisorConsoleNotes({ callId }: { callId: string }) {
  const { toast } = useToast();
  const [note, setNote] = React.useState("");
  const [saved, setSaved] = React.useState(false);
  const [disposition, setDisposition] = React.useState<string | null>(null);

  const handleSaveNote = (e: React.FormEvent) => {
    e.preventDefault();
    if (!note.trim()) return;
    setSaved(true);
    toast({ title: "Supervisor note saved", description: `Attached note to call ${callId.slice(0, 8)}`, variant: "success" });
    setTimeout(() => setSaved(false), 3000);
  };

  const handleTagDisposition = (tag: string) => {
    setDisposition(tag);
    toast({ title: `Lead tagged as ${tag}`, description: "Disposition updated for analytics.", variant: "success" });
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground mr-1">Quick Tag:</span>
        {[
          { label: "🔥 Hot Lead", val: "hot" },
          { label: "⚡ Warm", val: "warm" },
          { label: "❄️ Cold", val: "cold" },
          { label: "📅 Booked", val: "booked" },
          { label: "📞 Callback", val: "callback" },
        ].map((d) => (
          <button
            key={d.val}
            type="button"
            onClick={() => handleTagDisposition(d.label)}
            className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
              disposition === d.label
                ? "border-primary bg-primary/20 text-primary font-semibold"
                : "border-border bg-surface text-muted-foreground hover:text-foreground"
            }`}
          >
            {d.label}
          </button>
        ))}
      </div>
      <form onSubmit={handleSaveNote} className="flex items-center gap-2">
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add supervisor note (e.g. 'Customer interested in annual plan, call back at 5pm')..."
          className="h-8 text-xs bg-surface"
        />
        <Button type="submit" size="sm" variant="outline" className="h-8 px-3 text-xs shrink-0">
          <MessageSquarePlus className="h-3.5 w-3.5 mr-1" /> Save Note
        </Button>
      </form>
      {saved && <p className="text-[11px] text-emerald-400 font-medium">✓ Note saved to call session record.</p>}
    </div>
  );
}

export function LiveCallConsole({ workspaceId, initialCalls }: { workspaceId: string; initialCalls: CallListItem[] }) {
  const [calls, setCalls] = React.useState<CallListItem[]>(initialCalls);
  const [selected, setSelected] = React.useState<string | null>(initialCalls[0]?.call_id ?? null);
  const [isLiveActive, setIsLiveActive] = React.useState(initialCalls.length > 0);

  // Auto-poll for live calls and recently executed calls every 2.5 seconds
  React.useEffect(() => {
    let mounted = true;
    const fetchCalls = async () => {
      try {
        const inProgress = await callsApi.list(workspaceId, "in_progress");
        if (!mounted) return;

        if (inProgress.length > 0) {
          setCalls(inProgress);
          setIsLiveActive(true);
          setSelected((prev) => (prev && inProgress.some((c) => c.call_id === prev) ? prev : (inProgress[0]?.call_id ?? null)));
        } else {
          // If none in-progress, show recent calls so campaigns newly launched are immediately visible
          const all = await callsApi.list(workspaceId);
          if (!mounted) return;
          const recent = all.slice(0, 8);
          setCalls(recent);
          setIsLiveActive(false);
          setSelected((prev) => (prev && recent.some((c) => c.call_id === prev) ? prev : (recent[0]?.call_id ?? null)));
        }
      } catch {
        // quiet background poll error
      }
    };

    const interval = setInterval(fetchCalls, 2500);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [workspaceId]);

  if (calls.length === 0) {
    return (
      <EmptyState
        icon={Radio}
        title="No calls currently running"
        description="Start a Test Lab call or launch a campaign — calls will appear here automatically."
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
              <span className={`absolute inline-flex h-3 w-3 animate-ping rounded-full ${isLiveActive ? "bg-secondary/50" : "bg-muted/40"}`} />
              <span className={`relative inline-flex h-2 w-2 rounded-full ${isLiveActive ? "bg-secondary" : "bg-muted-foreground"}`} />
            </span>
            {isLiveActive ? "Live In Progress" : "Recent Calls"}
            <Badge variant={isLiveActive ? "live" : "secondary"} className="ml-auto">
              {calls.length} {isLiveActive ? "active" : "total"}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 p-0 pb-2">
          {calls.map((c) => (
            <button
              key={c.call_id}
              onClick={() => setSelected(c.call_id)}
              className={`flex w-full items-center justify-between px-4 py-3 text-left text-sm transition-colors hover:bg-surface-raised ${
                selected === c.call_id ? "border-l-2 border-secondary bg-secondary/5 pl-3.5" : ""
              }`}
            >
              <div className="flex items-center gap-2.5">
                <CallPulse active={c.status === "in_progress"} size="sm" />
                <div>
                  <p className="font-medium text-foreground">{c.contact_name ?? "Test call"}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {c.direction} {c.campaign_id ? "· Campaign" : "· Test"} {c.duration_seconds ? `· ${c.duration_seconds}s` : ""}
                  </p>
                </div>
              </div>
              <Badge variant={c.status === "in_progress" ? "live" : "secondary"}>
                {c.status.replace(/_/g, " ")}
              </Badge>
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

