"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { ArrowRight, Bot, Calendar, CheckCircle2, ChevronRight, Headphones, Megaphone, MessageSquareText, PhoneCall, Play, Radio, ShieldCheck, Sparkles, Square, Volume2, Zap } from "lucide-react";
import Link from "next/link";
import { Badge, Button, Card, CardContent } from "@jkr/ui";
import { VoiceOrb } from "@/components/3d/voice-orb";

const STAGES = [
  {
    step: "01",
    title: "Build Voice Persona",
    tagline: "Natural Indian Languages",
    description: "Design agents that speak Telugu, Hindi, English, or seamlessly code-switch with human cadence, tone, and instant interruption handling.",
    icon: Bot,
    accent: "border-primary/40 bg-primary/10 text-primary",
  },
  {
    step: "02",
    title: "Run Batch Campaigns",
    tagline: "Compliant & Safe",
    description: "Automated calling windows with mandatory TRAI calling-hours respect, DND suppression checks, and transparent AI disclosures.",
    icon: Megaphone,
    accent: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  },
  {
    step: "03",
    title: "Listen & Supervise",
    tagline: "Live Console SSE",
    description: "Watch live calls unfold turn-by-turn with sub-800ms pipeline latency. Whisper suggestions to the AI or barge in with 1 click.",
    icon: Headphones,
    accent: "border-secondary/40 bg-secondary/10 text-secondary",
  },
  {
    step: "04",
    title: "Convert to Revenue",
    tagline: "Outcome-Driven",
    description: "Book appointments directly into Google Calendar, send instant WhatsApp confirmations, and calculate unit economics down to the rupee.",
    icon: Calendar,
    accent: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
  },
];

export function LandingInteractive() {
  const [activeVoice, setActiveVoice] = React.useState<"telugu" | "hindi" | "english" | null>(null);
  const [isPlaying, setIsPlaying] = React.useState(false);

  // Initialize Lenis smooth scroll on client
  React.useEffect(() => {
    let lenisInstance: any = null;
    import("lenis").then(({ default: Lenis }) => {
      lenisInstance = new Lenis({
        duration: 1.2,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        orientation: "vertical",
        smoothWheel: true,
      });

      function raf(time: number) {
        lenisInstance?.raf(time);
        requestAnimationFrame(raf);
      }
      requestAnimationFrame(raf);
    }).catch(() => {});

    return () => {
      lenisInstance?.destroy();
    };
  }, []);

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
      }, 5000);
    }
  };

  // 3D Card tilt state for dashboard mockup
  const mockRef = React.useRef<HTMLDivElement>(null);
  const [mockTilt, setMockTilt] = React.useState({ x: 0, y: 0, glareX: 50, glareY: 50, active: false });

  const handleMockMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!mockRef.current) return;
    const rect = mockRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    setMockTilt({
      x: ((y - centerY) / centerY) * -5,
      y: ((x - centerX) / centerX) * 5,
      glareX: (x / rect.width) * 100,
      glareY: (y / rect.height) * 100,
      active: true,
    });
  };

  const handleMockLeave = () => {
    setMockTilt({ x: 0, y: 0, glareX: 50, glareY: 50, active: false });
  };

  return (
    <div className="space-y-28">
      {/* 3D Voice Orb Hero Feature */}
      <div className="relative mx-auto max-w-4xl px-4 text-center">
        <div className="relative mx-auto flex flex-col items-center justify-center">
          {/* Ambient Glowing Halo */}
          <div className="pointer-events-none absolute h-72 w-72 rounded-full bg-primary/15 blur-[90px] animate-ambient-glow" />

          {/* 3D Voice Orb Canvas */}
          <div className="relative z-10 h-56 w-56 sm:h-64 sm:w-64">
            <VoiceOrb isTyping={isPlaying} />
          </div>

          {/* Interactive Voice Sample Chips */}
          <div className="relative z-20 mt-6 flex flex-wrap items-center justify-center gap-2.5">
            {[
              { id: "telugu", label: "Telugu AI Voice", sample: "నమస్కారం! నేను JKR AI నుండి కాల్ చేస్తున్నాను..." },
              { id: "hindi", label: "Hindi AI Voice", sample: "नमस्ते! JKR AI कॉलिंग प्लैटफ़ॉर्म में आपका स्वागत है..." },
              { id: "english", label: "Indian English", sample: "Hello! This is JKR AI Calling with your appointment update..." },
            ].map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => handlePlayVoice(v.id as any)}
                className={`flex items-center gap-2 rounded-full border px-4 py-2 text-xs font-semibold transition-all duration-200 shadow-sm ${
                  activeVoice === v.id && isPlaying
                    ? "border-primary bg-primary text-black scale-105 shadow-primary/20"
                    : "border-border/80 bg-surface/80 hover:bg-surface-raised text-foreground hover:border-primary/40"
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
            <motion.p
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-3 text-xs font-mono text-primary animate-pulse"
            >
              ▶ Synthesizing live neural voice stream via Sarvam &amp; Dograh Engine...
            </motion.p>
          )}
        </div>
      </div>

      {/* 3D Dashboard Interactive Mockup */}
      <section className="mx-auto max-w-5xl px-6 perspective-1000">
        <div className="text-center mb-8">
          <Badge variant="outline" className="border-primary/40 text-primary mb-2 text-xs">
            Studio Experience
          </Badge>
          <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Built for enterprise clarity and real-time control
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-xl mx-auto">
            Interactive preview of the live telemetry console, cost-per-outcome economics, and conversation transcripts.
          </p>
        </div>

        <div
          ref={mockRef}
          onMouseMove={handleMockMove}
          onMouseLeave={handleMockLeave}
          className="relative rounded-2xl border border-border/80 bg-surface/90 p-4 sm:p-6 shadow-2xl backdrop-blur-xl preserve-3d transition-transform duration-200 ease-out card-3d"
          style={{
            transform: mockTilt.active
              ? `perspective(1000px) rotateX(${mockTilt.x}deg) rotateY(${mockTilt.y}deg) scale3d(1.01, 1.01, 1.01)`
              : undefined,
          }}
        >
          {/* Specular glare reflection */}
          <div
            className="pointer-events-none absolute inset-0 z-20 rounded-2xl transition-opacity duration-200"
            style={{
              opacity: mockTilt.active ? 0.35 : 0,
              background: `radial-gradient(circle at ${mockTilt.glareX}% ${mockTilt.glareY}%, rgba(255, 212, 0, 0.22) 0%, transparent 65%)`,
            }}
            aria-hidden="true"
          />

          {/* Top Bar of Mockup */}
          <div className="flex items-center justify-between border-b border-border/60 pb-4 mb-5">
            <div className="flex items-center gap-2.5">
              <span className="h-3 w-3 rounded-full bg-red-500/80 inline-block" />
              <span className="h-3 w-3 rounded-full bg-yellow-500/80 inline-block" />
              <span className="h-3 w-3 rounded-full bg-green-500/80 inline-block" />
              <span className="ml-3 font-mono text-xs text-muted-foreground font-semibold">
                app.jkr-calling.com/app/dashboard
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-secondary animate-pulse" />
              <span className="text-[11px] font-mono font-bold text-secondary">LIVE 4 ACTIVE CHANNELS</span>
            </div>
          </div>

          {/* Grid inside mockup */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-border/60 bg-surface-raised/70 p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Total Calls</span>
              <p className="mt-1 font-display text-2xl font-bold text-foreground">1,284</p>
              <p className="text-[11px] text-emerald-400 mt-0.5">↑ +18.4% this week</p>
            </div>
            <div className="rounded-xl border border-border/60 bg-surface-raised/70 p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Connect Rate</span>
              <p className="mt-1 font-display text-2xl font-bold text-foreground">68.5%</p>
              <p className="text-[11px] text-primary mt-0.5">Telugu / Hindi / English</p>
            </div>
            <div className="rounded-xl border border-border/60 bg-surface-raised/70 p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Unit Acquisition Cost</span>
              <p className="mt-1 font-display text-2xl font-bold text-amber-400">₹32 / appt</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">vs. ₹220 Human BDR</p>
            </div>
          </div>
        </div>
      </section>

      {/* 4-Stage Storytelling Section */}
      <section className="mx-auto max-w-6xl px-6">
        <div className="text-center mb-12">
          <Badge variant="outline" className="border-secondary/40 text-secondary mb-2 text-xs">
            How It Works
          </Badge>
          <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            From prompt to pipeline in 4 seamless stages
          </h2>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map((s) => {
            const Icon = s.icon;
            return (
              <div
                key={s.step}
                className="group relative rounded-2xl border border-border/70 bg-surface/80 p-6 shadow-md transition-all duration-300 hover:border-primary/50 hover:-translate-y-1 hover:shadow-xl"
              >
                <div className="flex items-center justify-between mb-4">
                  <span className="font-mono text-xs font-bold text-muted-foreground">{s.step}</span>
                  <div className={`flex h-9 w-9 items-center justify-center rounded-xl border ${s.accent}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                </div>
                <h3 className="font-display text-base font-bold text-foreground mb-1">{s.title}</h3>
                <span className="text-[11px] font-semibold text-primary/90 block mb-2">{s.tagline}</span>
                <p className="text-xs text-muted-foreground leading-relaxed">{s.description}</p>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
