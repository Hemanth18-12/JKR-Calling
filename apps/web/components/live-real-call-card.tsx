"use client";

import { ApiClientError, liveCallApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, useToast } from "@jkr/ui";
import { PhoneCall } from "lucide-react";
import Link from "next/link";
import * as React from "react";

export function LiveRealCallCard({ workspaceId, agentId }: { workspaceId: string; agentId: string }) {
  const { toast } = useToast();
  const [toNumber, setToNumber] = React.useState("");
  const [calling, setCalling] = React.useState(false);
  const [started, setStarted] = React.useState<{ call_id: string; call_sid: string } | null>(null);

  const call = async () => {
    setCalling(true);
    setStarted(null);
    try {
      const result = await liveCallApi.start(workspaceId, { agent_id: agentId, to_number: toNumber });
      setStarted(result);
      toast({ title: "Call placed", description: `Twilio SID ${result.call_sid} — your phone should ring shortly.`, variant: "success" });
    } catch (err) {
      toast({
        title: "Could not place the call",
        description: err instanceof ApiClientError ? err.message : "Unknown error",
        variant: "danger",
      });
    } finally {
      setCalling(false);
    }
  };

  return (
    <Card className="border-warning/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PhoneCall className="h-4 w-4" /> Live real call
        </CardTitle>
        <CardDescription>
          Places an actual phone call via Twilio with a real LLM driving the conversation — not a simulation.
          Requires <code>ENABLE_LIVE_CALLS=true</code>, Twilio + OpenAI credentials, and the destination number
          listed in <code>AUTHORIZED_TEST_NUMBERS</code>. Only dial numbers you own or have explicit permission
          to call.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <Label htmlFor="live-call-to">Your phone number (E.164)</Label>
          <Input id="live-call-to" placeholder="+919876543210" value={toNumber} onChange={(e) => setToNumber(e.target.value)} />
        </div>
        <Button onClick={call} loading={calling} disabled={!toNumber.trim()} variant="secondary" className="w-full">
          Call my phone
        </Button>
        {started ? (
          <div className="rounded-md border border-success/30 bg-success/5 p-3 text-sm">
            Call placed (SID <span className="font-mono text-xs">{started.call_sid}</span>). Once it ends, find the
            transcript on the{" "}
            <Link href="/app/calls" className="underline">
              Calls
            </Link>{" "}
            page.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
