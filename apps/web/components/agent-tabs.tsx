"use client";

import { type AgentDetail, type AgentVersionDetail } from "@jkr/contracts";
import { liveCallApi, ApiClientError } from "@jkr/sdk";
import { Badge, Button, Input, useToast } from "@jkr/ui";
import {
  Bot,
  Check,
  Copy,
  Headphones,
  MessageSquare,
  PhoneCall,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { AgentSummaryCards } from "./agent-summary-cards";
import { BackButton } from "./back-button";

const TABS = [
  { label: "Overview", segment: "" },
  { label: "Persona", segment: "persona" },
  { label: "Voice", segment: "voice" },
  { label: "Versions", segment: "versions" },
  { label: "Knowledge", segment: "knowledge" },
  { label: "Tools", segment: "tools" },
  { label: "Test Lab", segment: "test" },
];

interface AgentTabsProps {
  agentId: string;
  agentName: string;
  status: string;
  workspaceId?: string;
  agent?: AgentDetail | null;
  version?: AgentVersionDetail | null;
}

export function AgentTabs({
  agentId,
  agentName,
  status,
  workspaceId,
  agent,
  version,
}: AgentTabsProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { toast } = useToast();

  const base = `/app/agents/${agentId}`;

  // Quick Phone Call modal state
  const [showPhoneModal, setShowPhoneModal] = React.useState(false);
  const [phoneNumber, setPhoneNumber] = React.useState("+916301567773");
  const [isCalling, setIsCalling] = React.useState(false);
  const [callResult, setCallResult] = React.useState<{ call_sid: string } | null>(null);

  // Ask AI modal state
  const [showAiModal, setShowAiModal] = React.useState(false);
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [aiResponse, setAiResponse] = React.useState<string | null>(null);
  const [isGenerating, setIsGenerating] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const handlePlaceQuickCall = async () => {
    if (!workspaceId) {
      toast({ title: "Workspace not found", variant: "danger" });
      return;
    }
    if (!phoneNumber.trim()) {
      toast({ title: "Please enter a valid phone number", variant: "danger" });
      return;
    }

    setIsCalling(true);
    setCallResult(null);
    try {
      const res = await liveCallApi.start(workspaceId, {
        agent_id: agentId,
        to_number: phoneNumber.trim(),
      });
      setCallResult(res);
      toast({
        title: "Call Dispatched! 📞",
        description: `Twilio Call SID: ${res.call_sid}. Your phone will ring shortly.`,
        variant: "success",
      });
    } catch (err) {
      toast({
        title: "Could not place test call",
        description: err instanceof ApiClientError ? err.message : "Ensure Twilio credentials and authorized test numbers are set.",
        variant: "danger",
      });
    } finally {
      setIsCalling(false);
    }
  };

  const handleAskAi = (promptText?: string) => {
    const q = promptText || aiPrompt;
    if (!q.trim()) return;

    setIsGenerating(true);
    setAiResponse(null);

    // AI suggestion simulation for persona and greeting optimizations
    setTimeout(() => {
      let response = "";
      const lower = q.toLowerCase();

      if (lower.includes("greeting") || lower.includes("telugu") || lower.includes("welcome")) {
        response = `Recommended Telugu-English Greeting:
"నమస్కారం {name} గారు, నేను ${agent?.business_identity || "Aaha Dental Care"} నుండి మాట్లాడుతున్న AI అసిస్టెంట్‌ని. మీ appointment enquiry గురించి మాట్లాడొచ్చా అండి?"

💡 Tips:
• Warm honorific "గారు" builds immediate trust in Andhra/Telangana.
• Kept concise (14 words) to minimize initial turn latency.
• Ends with permission question so caller feels in control.`;
      } else if (lower.includes("objection") || lower.includes("price") || lower.includes("cost")) {
        response = `Recommended Objection Handling Rule:
"When caller hesitates on pricing:
1. Acknowledge respectfully: 'అర్థమైంది అండి' (I understand).
2. Clarify that consultation includes complete diagnosis and customized treatment plan with flexible EMI options.
3. Offer a low-friction next step: 'మేము డాక్టర్ గారి ఫ్రీ కన్సల్టేషన్ స్లాట్ బుక్ చేద్దామా?'"`;
      } else {
        response = `AI Recommendation for "${agentName}":
• Primary Objective: ${version?.primary_objective || "qualify_lead"}
• Suggested pacing: Keep response length to 'short' (1-2 sentences) for telephony clarity.
• Code-switching behavior: 'Adaptive' ensures fluent Telugu-English transition when caller replies in English.`;
      }

      setAiResponse(response);
      setIsGenerating(false);
    }, 700);
  };

  const copyAiResponse = () => {
    if (!aiResponse) return;
    navigator.clipboard.writeText(aiResponse);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="border-b border-border bg-surface px-6 pt-5 sm:px-8">
      {/* Top Header Row with Name and Quick Test Buttons (Pattern 3) */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <BackButton fallbackHref="/app/agents" label="Agents" />
          <h1 className="text-xl font-bold tracking-tight text-foreground">{agentName}</h1>
          <Badge variant={status === "active" ? "success" : "secondary"}>{status}</Badge>
        </div>

        {/* Quick Test Buttons (Pattern 3: Chat, Web Call, Phone Call, Ask AI) */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Chat Test */}
          <Link
            href={`${base}/test?mode=chat` as never}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-surface-raised px-3 py-1.5 text-xs font-semibold text-foreground transition-all duration-150 hover:border-primary hover:bg-surface-raised/80 hover:text-primary"
            title="Open Chat Simulation"
          >
            <MessageSquare className="h-3.5 w-3.5 text-primary" />
            <span>Chat</span>
          </Link>

          {/* Web Call */}
          <Link
            href={`${base}/test?mode=audio` as never}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-surface-raised px-3 py-1.5 text-xs font-semibold text-foreground transition-all duration-150 hover:border-primary hover:bg-surface-raised/80 hover:text-primary"
            title="Launch Voice Simulation"
          >
            <Headphones className="h-3.5 w-3.5 text-primary" />
            <span>Web Call</span>
          </Link>

          {/* Phone Call */}
          <button
            type="button"
            onClick={() => setShowPhoneModal(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition-all duration-150 hover:border-primary hover:bg-primary/20"
            title="Call Real Phone Number"
          >
            <PhoneCall className="h-3.5 w-3.5" />
            <span>Phone Call</span>
          </button>

          {/* Ask AI */}
          <button
            type="button"
            onClick={() => setShowAiModal(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-gradient-to-r from-amber-500/15 to-yellow-500/15 px-3 py-1.5 text-xs font-semibold text-amber-300 transition-all duration-150 hover:border-amber-400 hover:from-amber-500/25 hover:to-yellow-500/25"
            title="Ask AI Assistant"
          >
            <Sparkles className="h-3.5 w-3.5 text-amber-400" />
            <span>Ask AI</span>
          </button>
        </div>
      </div>

      {/* Pattern 1: Compact Assistant Settings Summary Cards */}
      {agent && (
        <div className="mb-2">
          <AgentSummaryCards agent={agent} version={version} />
        </div>
      )}

      {/* Navigation Tabs */}
      <nav className="flex gap-1 overflow-x-auto">
        {TABS.map((tab) => {
          const href = tab.segment ? `${base}/${tab.segment}` : base;
          const active = pathname === href;
          return (
            <Link
              key={tab.label}
              href={href as never}
              className={`rounded-t-md px-3.5 py-2 text-sm font-medium transition-colors ${
                active
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {/* Modal: Quick Phone Call */}
      {showPhoneModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-primary/40 bg-surface-raised p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/20 text-primary">
                  <PhoneCall className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground">Quick Test Phone Call</h3>
                  <p className="text-xs text-muted-foreground">Dial a live number to test {agentName}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowPhoneModal(false)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-semibold text-muted-foreground">
                  Your Phone Number (E.164 with Country Code)
                </label>
                <Input
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+916301567773"
                  className="font-mono"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  The AI will call your phone directly via Twilio telephony.
                </p>
              </div>

              {callResult && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-400">
                  Call placed successfully! Twilio SID:{" "}
                  <code className="font-mono font-bold text-foreground">{callResult.call_sid}</code>
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <Button
                  variant="secondary"
                  className="flex-1"
                  onClick={() => setShowPhoneModal(false)}
                >
                  Close
                </Button>
                <Button
                  variant="gradient"
                  className="flex-1"
                  loading={isCalling}
                  onClick={handlePlaceQuickCall}
                >
                  <PhoneCall className="mr-1.5 h-4 w-4" />
                  Call Now
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Ask AI Copilot */}
      {showAiModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-amber-500/40 bg-surface-raised p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground">Ask AI Assistant</h3>
                  <p className="text-xs text-muted-foreground">Optimize prompt, greeting &amp; Telugu dialogue for {agentName}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAiModal(false)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3">
              {/* Quick Prompt Chips */}
              <div className="flex flex-wrap gap-1.5">
                {[
                  "Suggest a warm Telugu greeting",
                  "Tighten objection handling",
                  "Make voice persona more polite",
                ].map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => {
                      setAiPrompt(chip);
                      handleAskAi(chip);
                    }}
                    className="rounded-full border border-border/80 bg-surface px-2.5 py-1 text-[11px] text-muted-foreground transition hover:border-amber-400 hover:text-foreground"
                  >
                    ✨ {chip}
                  </button>
                ))}
              </div>

              <div>
                <Input
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="Ask how to improve this voice assistant..."
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAskAi();
                  }}
                />
              </div>

              {isGenerating && (
                <div className="py-6 text-center text-xs text-muted-foreground">
                  <Sparkles className="mx-auto mb-2 h-5 w-5 animate-spin text-amber-400" />
                  Analyzing agent context and crafting recommendations...
                </div>
              )}

              {aiResponse && (
                <div className="relative rounded-xl border border-border/80 bg-surface p-3.5 text-xs">
                  <button
                    type="button"
                    onClick={copyAiResponse}
                    className="absolute right-2.5 top-2.5 flex items-center gap-1 rounded bg-surface-raised px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
                    title="Copy to clipboard"
                  >
                    {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                    <span>{copied ? "Copied" : "Copy"}</span>
                  </button>
                  <pre className="whitespace-pre-wrap font-sans text-muted-foreground leading-relaxed">
                    {aiResponse}
                  </pre>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="secondary" onClick={() => setShowAiModal(false)}>
                  Close
                </Button>
                <Button
                  variant="gradient"
                  loading={isGenerating}
                  onClick={() => handleAskAi()}
                >
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                  Generate Suggestions
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
