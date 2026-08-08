"use client";

import type { CallListItem } from "@jkr/contracts";
import { callsApi } from "@jkr/sdk";
import { Badge, Card, CardContent, CardHeader, CardTitle, EmptyState } from "@jkr/ui";
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Radio className={`h-4 w-4 ${ended ? "text-muted-foreground" : "animate-pulse text-danger"}`} />
          {ended ? "Call ended" : "Live"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {turns.length === 0 ? (
          <p className="text-sm text-muted-foreground">Waiting for the first turn…</p>
        ) : (
          turns.map((t) => (
            <div key={t.turn_ref} className={`flex ${t.speaker === "agent" ? "justify-start" : "justify-end"}`}>
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${t.speaker === "agent" ? "bg-surface-raised" : "bg-primary/15"}`}>
                <p className="mb-0.5 text-xs font-medium uppercase text-muted-foreground">{t.speaker}</p>
                <p>{t.text}</p>
              </div>
            </div>
          ))
        )}
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
      <Card className="lg:col-span-1">
        <CardHeader>
          <CardTitle>In progress</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 p-0">
          {initialCalls.map((c) => (
            <button
              key={c.call_id}
              onClick={() => setSelected(c.call_id)}
              className={`flex w-full items-center justify-between px-5 py-3 text-left text-sm hover:bg-surface-raised ${
                selected === c.call_id ? "bg-surface-raised" : ""
              }`}
            >
              <span>{c.contact_name ?? "Test call"}</span>
              <Badge variant="warning">{c.status}</Badge>
            </button>
          ))}
        </CardContent>
      </Card>
      <div className="lg:col-span-2">{selected ? <LiveTranscript workspaceId={workspaceId} callId={selected} /> : null}</div>
    </div>
  );
}
