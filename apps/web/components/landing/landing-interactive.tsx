"use client";

import * as React from "react";
import {
  ArrowRight,
  Bot,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Headphones,
  Megaphone,
  PhoneCall,
  Play,
  Radio,
  ShieldCheck,
  Sparkles,
  Square,
  Volume2,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { Badge, Button, Card, CardContent } from "@jkr/ui";
import { VoiceOrb } from "@/components/3d/voice-orb";

const THREE_STEPS = [
  {
    step: "01",
    title: "Create Your Multilingual Assistant",
    tagline: "Natural Indian Languages",
    description: "Select your business persona and configure Telugu, Hindi, or English dialogue. Our engine handles real-time code-switching and respectful honorifics like 'గారు'.",
    icon: Bot,
  },
  {
    step: "02",
    title: "Verify Guardrails & Calling Hours",
    tagline: "100% Compliant by Default",
    description: "Every outbound attempt verifies customer consent, TRAI calling-window rules, DND suppression list, and explicit AI disclosure before placing a dial.",
    icon: ShieldCheck,
  },
  {
    step: "03",
    title: "Automate Appointments & Lead Handoffs",
    tagline: "Outcome-Driven ROI",
    description: "The AI agent books confirmed slots directly into your calendar, dispatches WhatsApp confirmations, and escalates complex calls to human desks.",
    icon: Calendar,
  },
];

export function LandingInteractive() {
  const [activeVoice, setActiveVoice] = React.useState<"telugu" | "hindi" | "english" | null>(null);
  const [isPlaying, setIsPlaying] = React.useState(false);

  const handlePlayVoice = (lang: "telugu" | "hindi" | "english") => {
    if (activeVoice === lang && isPlaying) {
      setIsPlaying(false);
      setActiveVoice(null);
    } else {
      setActiveVoice(lang);
      setIsPlaying(true);
      setTimeout(() => {
        setIsPlaying(false);
        setActiveVoice(null);
      }, 4500);
    }
  };

  return (
    <div className="space-y-24">
      {/* Voice Demonstration Section */}
      <div className="relative mx-auto max-w-4xl px-4 text-center">
        <div className="relative mx-auto flex flex-col items-center justify-center">
          <Badge variant="outline" className="border-border bg-surface px-3 py-1 text-xs text-muted-foreground mb-4">
            Interactive Audio Demonstration
          </Badge>

          {/* Voice Orb Acoustic Canvas */}
          <div className="relative z-10 h-48 w-48 sm:h-56 sm:w-56 rounded-full border border-border/80 bg-surface flex items-center justify-center shadow-sm">
            <VoiceOrb isTyping={isPlaying} />
          </div>

          {/* Audio Sample Player Chips */}
          <div className="relative z-20 mt-6 flex flex-wrap items-center justify-center gap-2.5">
            {[
              { id: "telugu", label: "Telugu AI Voice (Priya)", sample: "నమస్కారం! మీ డెంటల్ అపాయింట్‌మెంట్ గురించి మాట్లాడుతున్నాను..." },
              { id: "hindi", label: "Hindi AI Voice (Kavya)", sample: "नमस्ते! आपके कार सर्विस फॉलो-अप के बारे में कॉल कर रहे हैं..." },
              { id: "english", label: "Indian English (Aarav)", sample: "Hello! Calling to confirm your scheduled consultation slot tomorrow..." },
            ].map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => handlePlayVoice(v.id as any)}
                className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-xs font-semibold transition-all duration-150 shadow-sm ${
                  activeVoice === v.id && isPlaying
                    ? "border-primary bg-primary text-black"
                    : "border-border/80 bg-surface hover:bg-surface-raised text-foreground hover:border-primary/50"
                }`}
              >
                {activeVoice === v.id && isPlaying ? (
                  <Square className="h-3.5 w-3.5 fill-current" />
                ) : (
                  <Play className="h-3.5 w-3.5 fill-current text-primary" />
                )}
                <span>{v.label}</span>
              </button>
            ))}
          </div>

          {activeVoice && isPlaying && (
            <p className="mt-3 text-xs font-mono text-primary animate-pulse">
              Playing live telephony sample: 8kHz Indian acoustic model
            </p>
          )}
        </div>
      </div>

      {/* Real Product UI Preview (Live Telemetry & Unit Economics) */}
      <section className="mx-auto max-w-5xl px-6">
        <div className="text-center mb-8">
          <Badge variant="outline" className="border-primary/40 text-primary mb-2 text-xs">
            Live Product Interface
          </Badge>
          <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Clear operational numbers and real-time oversight
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-lg mx-auto">
            Live telemetry console, outcome cost breakdown, and real conversation transcripts.
          </p>
        </div>

        <div className="rounded-2xl border border-border/80 bg-surface p-5 sm:p-6 shadow-sm">
          {/* Top Browser Bar */}
          <div className="flex items-center justify-between border-b border-border/60 pb-3 mb-5">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="ml-2 font-mono text-xs text-muted-foreground">
                app.jkr-calling.com/app/dashboard
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[11px] font-mono font-semibold text-emerald-400">4 Active Channels</span>
            </div>
          </div>

          {/* Outcome Figures */}
          <div className="grid gap-4 sm:grid-cols-3 mb-6">
            <div className="rounded-xl border border-border/60 bg-surface-raised p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Appointments Booked</span>
              <p className="mt-1 font-display text-2xl font-bold text-foreground num-tabular">142</p>
              <p className="text-[11px] text-emerald-400 mt-0.5">89% attendance confirmation</p>
            </div>
            <div className="rounded-xl border border-border/60 bg-surface-raised p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Connect Rate</span>
              <p className="mt-1 font-display text-2xl font-bold text-foreground num-tabular">68.5%</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Bilingual Telugu &amp; English</p>
            </div>
            <div className="rounded-xl border border-border/60 bg-surface-raised p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Unit Cost per Booking</span>
              <p className="mt-1 font-display text-2xl font-bold text-primary num-tabular">₹32 / appt</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">vs. ₹180 to ₹250 SDR</p>
            </div>
          </div>

          {/* Recent Live Call Stream Mock */}
          <div className="rounded-xl border border-border/60 bg-surface-raised/60 p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs pb-2 border-b border-border/40 font-semibold">
              <span className="text-foreground">Recent Live Call Session</span>
              <span className="font-mono text-emerald-400">Appointment Booked · Hot Lead</span>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex items-start gap-2">
                <span className="rounded bg-primary/20 px-1.5 py-0.5 text-[10px] font-bold text-primary shrink-0">AI</span>
                <p className="text-foreground font-sans">
                  నమస్కారం కార్తికేయ గారు, Aaha Dental Care నుండి కాల్ చేస్తున్నాను. రేపు ఉదయం 11 గంటల డాక్టర్ కన్సల్టేషన్ స్లాట్ కంఫర్మ్ చేయమంటారా?
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground shrink-0">Caller</span>
                <p className="text-foreground font-sans">
                  అవునండి, 11 AM బాగుంటుంది. కన్ఫర్మ్ చేసేయండి.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="rounded bg-primary/20 px-1.5 py-0.5 text-[10px] font-bold text-primary shrink-0">AI</span>
                <p className="text-foreground font-sans">
                  ఖచ్చితంగా అండి! స్లాట్ కంఫర్మ్ చేశాను. మీకు వివరాలు వాట్సాప్‌లో పంపించాము. ధన్యవాదాలు!
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3-Step "How It Works" Section */}
      <section className="mx-auto max-w-6xl px-6">
        <div className="text-center mb-12">
          <Badge variant="outline" className="border-border bg-surface text-muted-foreground mb-2 text-xs">
            Simple 3-Step Process
          </Badge>
          <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            How JKR AI Calling works
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
            From assistant setup to verified telephone outcomes in three structured steps.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {THREE_STEPS.map((s) => {
            const Icon = s.icon;
            return (
              <div
                key={s.step}
                className="rounded-2xl border border-border/80 bg-surface p-6 shadow-sm transition-all duration-200 hover:border-primary/50"
              >
                <div className="flex items-center justify-between mb-4">
                  <span className="font-mono text-xs font-bold text-muted-foreground">{s.step}</span>
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border/80 bg-surface-raised text-primary">
                    <Icon className="h-4 w-4" />
                  </div>
                </div>
                <h3 className="font-display text-base font-bold text-foreground mb-1">{s.title}</h3>
                <span className="text-[11px] font-semibold text-primary block mb-2">{s.tagline}</span>
                <p className="text-xs text-muted-foreground leading-relaxed">{s.description}</p>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
