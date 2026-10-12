"use client";

import { ApiClientError, liveCallApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, useToast } from "@jkr/ui";
import { Clock, Coins, ExternalLink, Headphones, PhoneCall, Radio, ShieldCheck } from "lucide-react";
import Link from "next/link";
import * as React from "react";

export function LiveRealCallCard({ workspaceId, agentId }: { workspaceId: string; agentId: string }) {
  const { toast } = useToast();
  const [customerName, setCustomerName] = React.useState("Karthikeya");
  const [toNumber, setToNumber] = React.useState("");
  const [calling, setCalling] = React.useState(false);
  const [started, setStarted] = React.useState<{ call_id: string; call_sid: string } | null>(null);
  const [callDuration, setCallDuration] = React.useState(0);

  // Timer simulation when call is connected
  React.useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (started) {
      interval = setInterval(() => {
        setCallDuration((prev) => prev + 1);
      }, 1000);
    } else {
      setCallDuration(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [started]);

  const formatTimer = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainder = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
  };

  const call = async () => {
    setCalling(true);
    setStarted(null);
    try {
      const result = await liveCallApi.start(workspaceId, {
        agent_id: agentId,
        to_number: toNumber,
        customer_name: customerName.trim() || undefined,
      });
      setStarted(result);
      toast({
        title: "Call dispatched successfully",
        description: `Twilio SID: ${result.call_sid}. Your phone will ring shortly.`,
        variant: "success",
      });
    } catch (err) {
      toast({
        title: "Could not place the call",
        description: err instanceof ApiClientError ? err.message : "Unknown error occurred",
        variant: "danger",
      });
    } finally {
      setCalling(false);
    }
  };

  return (
    <Card className="border-border/80 bg-surface shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base font-bold text-foreground">
            <PhoneCall className="h-4 w-4 text-primary" />
            <span>Place Live Test Phone Call</span>
          </CardTitle>
          {started && (
            <Badge variant="success" className="animate-pulse">
              Live Connected
            </Badge>
          )}
        </div>
        <CardDescription className="text-xs text-muted-foreground leading-relaxed">
          Dispatches a direct telephone call to your mobile number with real bilingual turn dialogue.
          Ensure your destination number is verified on your telephony account.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {started ? (
          <div className="rounded-xl border border-primary/40 bg-surface-raised p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-3 w-3 items-center justify-center">
                  <span className="absolute inline-flex h-4 w-4 animate-ping rounded-full bg-primary/40" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-primary" />
                </div>
                <span className="text-xs font-semibold text-foreground">Call In Progress</span>
              </div>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Clock className="h-3.5 w-3.5 text-primary" />
                  <span className="num-tabular font-semibold text-foreground">{formatTimer(callDuration)}</span>
                </span>
                <span className="flex items-center gap-1 text-primary">
                  <Coins className="h-3.5 w-3.5" />
                  <span className="num-tabular font-semibold">2.4 / min</span>
                </span>
              </div>
            </div>

            {/* Voice Waveform Live Indicator */}
            <div className="flex items-center justify-center gap-1 py-3 bg-surface rounded-lg border border-border/40">
              <span className="h-3 w-1 bg-primary rounded-full animate-pulse" style={{ animationDuration: "0.6s" }} />
              <span className="h-6 w-1 bg-primary rounded-full animate-pulse" style={{ animationDuration: "0.9s", animationDelay: "0.1s" }} />
              <span className="h-8 w-1 bg-primary rounded-full animate-pulse" style={{ animationDuration: "0.7s", animationDelay: "0.2s" }} />
              <span className="h-4 w-1 bg-primary rounded-full animate-pulse" style={{ animationDuration: "1.0s", animationDelay: "0.15s" }} />
              <span className="h-7 w-1 bg-primary rounded-full animate-pulse" style={{ animationDuration: "0.8s", animationDelay: "0.25s" }} />
              <span className="h-2 w-1 bg-primary rounded-full animate-pulse" style={{ animationDuration: "0.5s" }} />
            </div>

            <div className="flex items-center justify-between text-xs pt-1">
              <span className="text-muted-foreground font-mono text-[11px]">
                SID: <span className="text-foreground">{started.call_sid}</span>
              </span>
              <Link
                href="/app/calls"
                className="inline-flex items-center gap-1 font-semibold text-primary hover:underline"
              >
                <span>View Full Transcript</span>
                <ExternalLink className="h-3 w-3" />
              </Link>
            </div>
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="live-call-name" className="text-xs">Customer Name</Label>
            <Input
              id="live-call-name"
              placeholder="e.g. Karthikeya"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="live-call-to" className="text-xs">Your Phone Number (+91 Mobile)</Label>
            <Input
              id="live-call-to"
              placeholder="+919876543210"
              value={toNumber}
              onChange={(e) => setToNumber(e.target.value)}
              className="mt-1 font-mono"
            />
          </div>
        </div>

        <Button
          onClick={call}
          loading={calling}
          disabled={!toNumber.trim()}
          variant="default"
          className="w-full font-bold"
        >
          <PhoneCall className="mr-1.5 h-4 w-4" />
          Call My Phone Now
        </Button>
      </CardContent>
    </Card>
  );
}
