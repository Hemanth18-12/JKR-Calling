"use client";

import { callsApi, ApiClientError } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, useToast } from "@jkr/ui";
import { PhoneOff, Send, Zap } from "lucide-react";
import * as React from "react";

interface ChatMessage {
  id: string;
  speaker: "agent" | "customer";
  text: string;
  interrupted?: boolean;
  interruptionClassification?: string;
}

export function TestLabChat({ workspaceId, agentId }: { workspaceId: string; agentId: string }) {
  const { toast } = useToast();
  const [callId, setCallId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [state, setState] = React.useState<Record<string, unknown> | null>(null);
  const [input, setInput] = React.useState("");
  const [starting, setStarting] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [ended, setEnded] = React.useState<{ outcome_category: string; lead_score: string } | null>(null);

  const startCall = async () => {
    setStarting(true);
    setMessages([]);
    setEnded(null);
    try {
      const result = await callsApi.startTest(workspaceId, { agent_id: agentId, contact_name: "Test Customer" });
      setCallId(result.call_id);
      setMessages([{ id: "greeting", speaker: "agent", text: result.greeting }]);
      setState(result.conversation_state);
    } catch (err) {
      toast({ title: "Could not start call", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setStarting(false);
    }
  };

  const send = async () => {
    if (!callId || !input.trim()) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), speaker: "customer", text }]);
    setSending(true);
    try {
      const result = await callsApi.submitUserTurn(workspaceId, callId, text);
      setMessages((prev) => {
        const updated = [...prev];
        if (result.interruption_classification === "meaningful") {
          // Mark the most recent agent message as interrupted.
          for (let i = updated.length - 1; i >= 0; i--) {
            const candidate = updated[i];
            if (candidate?.speaker === "agent") {
              updated[i] = { ...candidate, interrupted: true };
              break;
            }
          }
        }
        const lastIndex = updated.length - 1;
        const last = updated[lastIndex];
        if (last) {
          updated[lastIndex] = { ...last, interruptionClassification: result.interruption_classification };
        }
        if (result.agent_turn) {
          updated.push({ id: result.agent_turn.turn_ref, speaker: "agent", text: result.agent_turn.text });
        }
        return updated;
      });
      setState(result.conversation_state);
    } catch (err) {
      toast({ title: "Could not send", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setSending(false);
    }
  };

  const endCall = async () => {
    if (!callId) return;
    try {
      const result = await callsApi.end(workspaceId, callId);
      setEnded(result);
      toast({ title: "Call ended", description: `Outcome: ${result.outcome_category}`, variant: "success" });
    } catch (err) {
      toast({ title: "Could not end call", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    }
  };

  const knownFields = (state?.known_fields as Record<string, string>) ?? {};

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Text simulation</CardTitle>
          {!callId ? (
            <Button onClick={startCall} loading={starting} variant="gradient" size="sm">
              <Zap className="h-4 w-4" /> Start mock call
            </Button>
          ) : (
            <Button onClick={endCall} variant="destructive" size="sm" disabled={!!ended}>
              <PhoneOff className="h-4 w-4" /> End call
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {!callId ? (
            <p className="text-sm text-muted-foreground">
              Starts a real conversation-engine call against this agent&apos;s latest version — no real
              phone, no cost. Reply quickly (within a couple seconds) to see barge-in / interruption
              handling kick in.
            </p>
          ) : (
            <div className="space-y-4">
              <div className="max-h-96 space-y-3 overflow-y-auto rounded-md border border-border bg-background p-4">
                {messages.map((m) => (
                  <div key={m.id} className={`flex ${m.speaker === "agent" ? "justify-start" : "justify-end"}`}>
                    <div
                      className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                        m.speaker === "agent" ? "bg-surface-raised text-foreground" : "bg-primary/20 text-foreground"
                      }`}
                    >
                      <p>{m.text}</p>
                      <div className="mt-1 flex gap-1">
                        {m.interrupted ? (
                          <Badge variant="warning" className="text-[10px]">interrupted</Badge>
                        ) : null}
                        {m.interruptionClassification === "false_positive" ? (
                          <Badge variant="secondary" className="text-[10px]">filler (ignored)</Badge>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {!ended ? (
                <div className="flex gap-2">
                  <Input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && send()}
                    placeholder="Type the customer's reply…"
                    disabled={sending}
                  />
                  <Button onClick={send} loading={sending} disabled={!input.trim()}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <div className="rounded-md border border-success/30 bg-success/5 p-3 text-sm">
                  Outcome: <strong>{ended.outcome_category}</strong> · Lead score: <strong>{ended.lead_score}</strong>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Conversation state</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {state ? (
            <>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Objective</p>
                <p>{String(state.objective)} — <Badge variant="outline">{String(state.objective_status)}</Badge></p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Extracted fields</p>
                {Object.keys(knownFields).length === 0 ? (
                  <p className="text-muted-foreground">None yet</p>
                ) : (
                  <ul className="space-y-1">
                    {Object.entries(knownFields).map(([k, v]) => (
                      <li key={k}>
                        <span className="font-mono text-xs text-muted-foreground">{k}:</span> {v}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Missing fields</p>
                <p>{(state.missing_fields as string[])?.join(", ") || "None"}</p>
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">Start a call to see live state here.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
