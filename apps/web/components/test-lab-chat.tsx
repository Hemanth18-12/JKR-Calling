"use client";

import { callsApi, ApiClientError } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label, useToast } from "@jkr/ui";
import { AlertCircle, CheckCircle2, MessageSquare, PhoneOff, Send, Smartphone, Zap } from "lucide-react";
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
  const [customerName, setCustomerName] = React.useState("Hemanth");
  const [phoneNumber, setPhoneNumber] = React.useState("+916301567773");
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
      const result = await callsApi.startTest(workspaceId, {
        agent_id: agentId,
        contact_name: customerName.trim() || "Test Customer",
        phone_e164: phoneNumber.trim() || "+916301567773",
      });
      setCallId(result.call_id);
      setMessages([{ id: "greeting", speaker: "agent", text: result.greeting }]);
      setState(result.conversation_state);
    } catch (err) {
      toast({
        title: "Could not start call",
        description: err instanceof ApiClientError ? err.message : undefined,
        variant: "danger",
      });
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
      toast({
        title: "Could not send",
        description: err instanceof ApiClientError ? err.message : undefined,
        variant: "danger",
      });
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
      toast({
        title: "Could not end call",
        description: err instanceof ApiClientError ? err.message : undefined,
        variant: "danger",
      });
    }
  };

  const knownFields = (state?.known_fields as Record<string, string>) ?? {};
  const toolResults = (state?.tool_results as Record<string, any>) ?? {};
  const apptResult = toolResults.book_appointment;
  const whatsappResult = apptResult?.whatsapp;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Text Simulation & Call Test</CardTitle>
          {callId ? (
            <Button onClick={endCall} variant="destructive" size="sm" disabled={!!ended}>
              <PhoneOff className="h-4 w-4" /> End call
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {!callId ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Simulate a real conversation call with your agent. Enter your real mobile number below to receive
                live appointment confirmation notifications.
              </p>
              <div className="grid gap-4 sm:grid-cols-2 rounded-lg border border-border/60 bg-surface p-4">
                <div>
                  <Label htmlFor="lab-name" className="text-xs font-medium">Customer Name</Label>
                  <Input
                    id="lab-name"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    placeholder="e.g. Hemanth"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="lab-phone" className="text-xs font-medium">Recipient Phone (E.164)</Label>
                  <Input
                    id="lab-phone"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    placeholder="+916301567773"
                    className="mt-1 font-mono text-sm"
                  />
                </div>
              </div>
              <Button onClick={startCall} loading={starting} variant="gradient" className="w-full sm:w-auto">
                <Zap className="h-4 w-4" /> Start Mock Call
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-border/40 pb-2 text-xs text-muted-foreground">
                <span>Customer: <strong className="text-foreground">{customerName}</strong></span>
                <span>Phone: <code className="font-mono text-foreground">{phoneNumber}</code></span>
              </div>
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
                    placeholder="Type the customer's reply (e.g. రేపు ఉదయం 11 గంటలకు కంఫర్మ్ చేయండి)…"
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

      <div className="space-y-6">
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

        {apptResult ? (
          <Card className="border-success/40 bg-success/5">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold text-success">
                <CheckCircle2 className="h-4 w-4" /> Appointment Confirmed
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div>
                <span className="text-muted-foreground">Scheduled For:</span>
                <p className="font-medium text-foreground">
                  {new Date(apptResult.scheduled_for).toLocaleString(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </p>
              </div>

              <div>
                <span className="text-muted-foreground">Recipient Number:</span>
                <p className="font-mono text-foreground font-medium">
                  {apptResult.contact_phone || phoneNumber}
                </p>
              </div>

              {whatsappResult ? (
                <div className="rounded border border-border/80 bg-background/80 p-2.5 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold flex items-center gap-1.5">
                      <MessageSquare className="h-3.5 w-3.5 text-primary" /> Confirmation Dispatch
                    </span>
                    <Badge variant={whatsappResult.status === "sent" ? "success" : "warning"}>
                      {whatsappResult.channel === "sms_fallback" ? "SMS Delivered" : (whatsappResult.status || "Dispatched")}
                    </Badge>
                  </div>
                  {whatsappResult.provider_message_id ? (
                    <div className="font-mono text-[11px] text-muted-foreground">
                      Twilio SID: <span className="text-foreground">{whatsappResult.provider_message_id}</span>
                    </div>
                  ) : null}
                  {whatsappResult.error ? (
                    <div className="text-[11px] text-amber-500 mt-1 flex items-start gap-1">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      <span>{whatsappResult.error}</span>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-muted-foreground">Notification status pending...</p>
              )}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
