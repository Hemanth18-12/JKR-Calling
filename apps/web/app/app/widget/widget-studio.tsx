"use client";

import type { AgentOut } from "@jkr/contracts";
import { Badge, Button } from "@jkr/ui";
import {
  Check,
  Code2,
  Coins,
  Copy,
  ExternalLink,
  Laptop,
  MessageSquare,
  Mic,
  Palette,
  Play,
  RotateCcw,
  Sparkles,
  Volume2,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

const PRESET_COLORS = [
  { name: "Indigo", hex: "#4f46e5" },
  { name: "Emerald", hex: "#059669" },
  { name: "Violet", hex: "#7c3aed" },
  { name: "Rose", hex: "#e11d48" },
  { name: "Amber", hex: "#d97706" },
  { name: "Sky", hex: "#0284c7" },
  { name: "Slate", hex: "#334155" },
];

export function WidgetStudio({
  workspaceId,
  agents,
  walletCoins,
}: {
  workspaceId: string;
  agents: AgentOut[];
  walletCoins: number;
}) {
  const [selectedAgentId, setSelectedAgentId] = React.useState<string>(
    agents[0]?.id ?? ""
  );
  const [themeColor, setThemeColor] = React.useState<string>("#4f46e5");
  const [position, setPosition] = React.useState<"bottom-right" | "bottom-left">("bottom-right");
  const [launcherText, setLauncherText] = React.useState<string>("Talk to AI Assistant");
  const [language, setLanguage] = React.useState<string>("te-IN");
  const [copied, setCopied] = React.useState<boolean>(false);
  const [codeTab, setCodeTab] = React.useState<"html" | "react">("html");

  // Interactive Live Preview State
  const [previewOpen, setPreviewOpen] = React.useState<boolean>(false);
  const [previewInput, setPreviewInput] = React.useState<string>("");
  const [previewMessages, setPreviewMessages] = React.useState<
    Array<{ sender: "user" | "agent"; text: string; appointment?: boolean }>
  >([
    {
      sender: "agent",
      text: "నమస్కారం! నేను ఏఐ అసిస్టెంట్‌ని. ఆహా డెంటల్ కేర్‌లో అపాయింట్‌మెంట్ బుకింగ్ లేదా సేవల వివరాల కోసం ఎలా సహాయపడగలను?",
    },
  ]);
  const [isSimulatingSpeech, setIsSimulatingSpeech] = React.useState<boolean>(false);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];

  const apiBase =
    typeof window !== "undefined" && window.location.origin.includes("localhost")
      ? "http://localhost:8000"
      : "https://jkr-calling-api.onrender.com";

  const scriptTagCode = `<!-- JKR Calling AI Voice & Chat Widget -->
<script
  src="${apiBase}/jkr-widget.js"
  data-agent-id="${selectedAgentId || "YOUR_AGENT_ID"}"
  data-theme-color="${themeColor}"
  data-position="${position}"
  data-language="${language}"
  data-api-base="${apiBase}"
  async>
</script>`;

  const reactSnippet = `import Script from 'next/script';

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Script
          src="${apiBase}/jkr-widget.js"
          data-agent-id="${selectedAgentId || "YOUR_AGENT_ID"}"
          data-theme-color="${themeColor}"
          data-position="${position}"
          data-language="${language}"
          data-api-base="${apiBase}"
          strategy="lazyOnload"
        />
      </body>
    </html>
  );
}`;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  const handleSimulateSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!previewInput.trim()) return;
    const userText = previewInput.trim();
    setPreviewInput("");

    setPreviewMessages((prev) => [...prev, { sender: "user", text: userText }]);
    setIsSimulatingSpeech(true);

    setTimeout(() => {
      let reply = "మీ సందేశం అందింది! రేపు ఉదయం 11:00 గంటలకు డాక్టర్ అపాయింట్‌మెంట్ ఖరారైంది.";
      let appointment = false;
      if (language === "hi-IN") {
        reply = "नमस्ते! कल सुबह 11:00 बजे डॉक्टर के साथ आपका अपॉइंटमेंट पक्का कर दिया गया है।";
        appointment = true;
      } else if (language === "en-IN") {
        reply = "Certainly! I have booked your dental checkup consultation for tomorrow at 11:00 AM.";
        appointment = true;
      } else {
        appointment = true;
      }

      setPreviewMessages((prev) => [
        ...prev,
        { sender: "agent", text: reply, appointment },
      ]);
      setIsSimulatingSpeech(false);
    }, 900);
  };

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500">
              <Sparkles className="h-5 w-5" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Website Voice &amp; Chat Widget Studio
            </h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Embed your native JKR AI voice agent into any website with real-time Telugu/Hindi/English speech recognition, Sarvam TTS playback, and automated appointment booking.
          </p>
        </div>

        {/* Coin Metering Status */}
        <div className="flex items-center gap-3 rounded-xl border border-border/80 bg-card p-3 shadow-sm">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10 text-amber-500">
            <Coins className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Wallet Balance
              </span>
              <Badge variant={walletCoins > 0 ? "success" : "danger"}>
                {walletCoins > 0 ? "Active" : "Depleted"}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-foreground">{walletCoins.toLocaleString()} Coins</span>
              <Link
                href="/app/billing"
                className="text-xs font-medium text-primary hover:underline flex items-center gap-0.5"
              >
                Top up <ExternalLink className="h-3 w-3" />
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left Column: Widget Customization Controls */}
        <div className="space-y-6 lg:col-span-5">
          <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-5">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
              <Palette className="h-4 w-4 text-primary" /> 1. Configuration &amp; Branding
            </h3>

            {/* Agent Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Assign AI Agent
              </label>
              <select
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                value={selectedAgentId}
                onChange={(e) => setSelectedAgentId(e.target.value)}
              >
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} ({agent.primary_language || "te-IN"})
                  </option>
                ))}
              </select>
            </div>

            {/* Theme Color Picker */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Primary Brand Color
              </label>
              <div className="flex items-center gap-2">
                {PRESET_COLORS.map((color) => (
                  <button
                    key={color.hex}
                    type="button"
                    title={color.name}
                    className={`h-7 w-7 rounded-full transition-transform ${
                      themeColor === color.hex ? "scale-125 ring-2 ring-foreground ring-offset-2" : "hover:scale-110"
                    }`}
                    style={{ backgroundColor: color.hex }}
                    onClick={() => setThemeColor(color.hex)}
                  />
                ))}
              </div>
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="color"
                  value={themeColor}
                  onChange={(e) => setThemeColor(e.target.value)}
                  className="h-8 w-10 cursor-pointer rounded border border-border bg-transparent p-0"
                />
                <input
                  type="text"
                  value={themeColor}
                  onChange={(e) => setThemeColor(e.target.value)}
                  className="w-28 rounded-md border border-border bg-background px-2.5 py-1 text-xs font-mono text-foreground uppercase"
                />
              </div>
            </div>

            {/* Launcher Text */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Launcher Button Text
              </label>
              <input
                type="text"
                value={launcherText}
                onChange={(e) => setLauncherText(e.target.value)}
                placeholder="Talk to AI Assistant"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* Default Language */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Default Voice &amp; Chat Language
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "te-IN", label: "తెలుగు" },
                  { id: "hi-IN", label: "हिंदी" },
                  { id: "en-IN", label: "English" },
                ].map((lang) => (
                  <button
                    key={lang.id}
                    type="button"
                    onClick={() => setLanguage(lang.id)}
                    className={`rounded-lg border px-3 py-2 text-xs font-medium transition-all ${
                      language === lang.id
                        ? "border-primary bg-primary/10 text-primary font-semibold"
                        : "border-border bg-background text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {lang.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Widget Position */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Screen Position
              </label>
              <div className="grid grid-cols-2 gap-2">
                {(["bottom-right", "bottom-left"] as const).map((pos) => (
                  <button
                    key={pos}
                    type="button"
                    onClick={() => setPosition(pos)}
                    className={`rounded-lg border px-3 py-2 text-xs font-medium capitalize transition-all ${
                      position === pos
                        ? "border-primary bg-primary/10 text-primary font-semibold"
                        : "border-border bg-background text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {pos.replace("-", " ")}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Embed Code Snippet Card */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-foreground flex items-center gap-2">
                <Code2 className="h-4 w-4 text-primary" /> 2. Embed on Your Website
              </h3>
              <div className="flex items-center gap-1 rounded-md bg-muted p-0.5">
                <button
                  type="button"
                  onClick={() => setCodeTab("html")}
                  className={`rounded px-2 py-1 text-xs font-medium ${
                    codeTab === "html" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"
                  }`}
                >
                  HTML Script
                </button>
                <button
                  type="button"
                  onClick={() => setCodeTab("react")}
                  className={`rounded px-2 py-1 text-xs font-medium ${
                    codeTab === "react" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"
                  }`}
                >
                  Next.js / React
                </button>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Paste this tag into your website's HTML before the closing <code className="text-foreground">&lt;/body&gt;</code> tag. It runs with zero external dependencies.
            </p>

            <div className="relative">
              <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3.5 text-xs font-mono text-emerald-400">
                {codeTab === "html" ? scriptTagCode : reactSnippet}
              </pre>
              <button
                type="button"
                onClick={() => copyToClipboard(codeTab === "html" ? scriptTagCode : reactSnippet)}
                className="absolute right-2 top-2 rounded-md bg-white/10 px-2.5 py-1 text-xs font-medium text-white backdrop-blur hover:bg-white/20 flex items-center gap-1.5 transition-colors"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Live Interactive Sandbox Simulator */}
        <div className="space-y-4 lg:col-span-7">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Laptop className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold text-foreground">Interactive Simulator Preview</span>
              <Badge variant="secondary" className="text-xs">Live Sandbox</Badge>
            </div>
            <button
              type="button"
              onClick={() => {
                setPreviewMessages([
                  {
                    sender: "agent",
                    text:
                      language === "hi-IN"
                        ? "नमस्ते! मैं आपका एआई असिस्टेंट हूँ। मैं आपकी क्या मदद कर सकता हूँ?"
                        : language === "en-IN"
                        ? "Hello! I am your AI Assistant. How can I help you today?"
                        : "నమస్కారం! నేను ఏఐ అసిస్టెంట్‌ని. ఆహా డెంటల్ కేర్‌లో అపాయింట్‌మెంట్ బుకింగ్ కోసం ఎలా సహాయపడగలను?",
                  },
                ]);
              }}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="h-3 w-3" /> Reset preview
            </button>
          </div>

          {/* Realistic Website Mockup Frame */}
          <div className="relative h-[650px] w-full rounded-2xl border border-border bg-slate-900 shadow-2xl overflow-hidden flex flex-col">
            {/* Browser chrome header */}
            <div className="flex items-center gap-2 border-b border-white/10 bg-slate-950 px-4 py-3">
              <div className="flex items-center gap-1.5">
                <div className="h-3 w-3 rounded-full bg-red-500/80" />
                <div className="h-3 w-3 rounded-full bg-amber-500/80" />
                <div className="h-3 w-3 rounded-full bg-emerald-500/80" />
              </div>
              <div className="mx-auto flex h-6 w-3/5 items-center justify-center rounded-md bg-slate-900 px-3 text-xs text-slate-400 font-mono">
                https://aaha-dental-care.com
              </div>
            </div>

            {/* Host Website Content Mockup */}
            <div className="flex-1 p-6 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 overflow-y-auto">
              <div className="max-w-md space-y-4">
                <span className="inline-block rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-semibold text-indigo-400">
                  Aaha Dental Care &amp; Multi-Speciality Clinic
                </span>
                <h2 className="text-2xl font-extrabold text-white tracking-tight">
                  Advanced Dental Care with Friendly AI Specialists
                </h2>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Book appointments instantly, check doctor timings, and ask queries directly through our native AI voice assistant on the bottom corner.
                </p>
                <div className="flex gap-3 pt-2">
                  <div className="h-9 w-28 rounded-lg bg-white/10 animate-pulse" />
                  <div className="h-9 w-24 rounded-lg bg-white/5 animate-pulse" />
                </div>
              </div>
            </div>

            {/* Embedded Floating Widget UI */}
            <div
              className={`absolute bottom-6 z-20 flex flex-col ${
                position === "bottom-left" ? "left-6 items-start" : "right-6 items-end"
              }`}
            >
              {/* Expandable Chat Window */}
              {previewOpen && (
                <div className="mb-3 flex h-[480px] w-[340px] flex-col rounded-2xl border border-white/15 bg-slate-950 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                  {/* Header */}
                  <div
                    className="flex items-center justify-between p-3.5 text-white"
                    style={{
                      background: `linear-gradient(135deg, ${themeColor}dd, #0f172a)`,
                    }}
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/20 text-lg backdrop-blur">
                        🤖
                      </div>
                      <div>
                        <div className="text-xs font-bold leading-tight">
                          {selectedAgent?.name || "AI Assistant"}
                        </div>
                        <div className="flex items-center gap-1 text-[10px] text-emerald-300">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          Live • Dograh &amp; Sarvam
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="rounded-lg p-1.5 text-white/80 hover:bg-white/10"
                        title="Voice Active"
                      >
                        <Volume2 className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewOpen(false)}
                        className="rounded-lg p-1.5 text-white/80 hover:bg-white/10"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  {/* Messages Area */}
                  <div className="flex-1 space-y-2.5 overflow-y-auto p-3.5">
                    {previewMessages.map((msg, i) => (
                      <div
                        key={i}
                        className={`flex flex-col ${
                          msg.sender === "user" ? "items-end" : "items-start"
                        }`}
                      >
                        <div
                          className={`max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed ${
                            msg.sender === "user"
                              ? "text-white"
                              : "border border-white/10 bg-slate-900 text-slate-100"
                          }`}
                          style={{
                            backgroundColor: msg.sender === "user" ? themeColor : undefined,
                          }}
                        >
                          {msg.text}
                        </div>
                        {msg.appointment && (
                          <div className="mt-2 w-full rounded-lg border border-emerald-500/40 bg-emerald-950/40 p-2.5 text-xs text-emerald-300 flex items-center gap-2">
                            <span className="text-base">📅</span>
                            <div>
                              <strong className="block font-semibold">Appointment Scheduled!</strong>
                              <span className="text-[11px] text-emerald-400/80">
                                Synced with Clinic CRM &amp; Calendar.
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                    {isSimulatingSpeech && (
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400 italic">
                        <span className="h-2 w-2 rounded-full bg-slate-400 animate-ping" />
                        AI is thinking...
                      </div>
                    )}
                  </div>

                  {/* Footer Input */}
                  <form onSubmit={handleSimulateSend} className="flex items-center gap-2 border-t border-white/10 bg-slate-900 p-2.5">
                    <button
                      type="button"
                      onClick={() => {
                        setPreviewInput("నాకు రేపు అపాయింట్‌మెంట్ కావాలి");
                      }}
                      title="Simulate Voice Input"
                      className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
                    >
                      <Mic className="h-4 w-4" />
                    </button>
                    <input
                      type="text"
                      value={previewInput}
                      onChange={(e) => setPreviewInput(e.target.value)}
                      placeholder="Type a message..."
                      className="flex-1 rounded-lg border border-white/10 bg-slate-950 px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      type="submit"
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-white transition-transform hover:scale-105"
                      style={{ backgroundColor: themeColor }}
                    >
                      ➤
                    </button>
                  </form>
                </div>
              )}

              {/* Launcher Floating Button */}
              {!previewOpen && (
                <button
                  type="button"
                  onClick={() => setPreviewOpen(true)}
                  className="flex items-center gap-2.5 rounded-full px-4 py-2.5 text-xs font-semibold text-white shadow-xl transition-transform hover:scale-105"
                  style={{ backgroundColor: themeColor }}
                >
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  </span>
                  <span>{launcherText}</span>
                  <MessageSquare className="h-4 w-4 ml-0.5" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
