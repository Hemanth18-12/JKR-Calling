"use client";

import { type AgentDetail, type AgentVersionDetail } from "@jkr/contracts";
import { Badge } from "@jkr/ui";
import { Cpu, Globe, Info, Mic, Volume2 } from "lucide-react";
import * as React from "react";

interface AgentSummaryCardsProps {
  agent: AgentDetail;
  version?: AgentVersionDetail | null;
}

export function AgentSummaryCards({ agent, version }: { agent: AgentDetail; version?: AgentVersionDetail | null }) {
  const [activeInfo, setActiveInfo] = React.useState<string | null>(null);

  const voice = version?.voice_persona;
  const policy = version?.conversation_policy;

  // Resolve user-friendly language display
  const languageLabel = React.useMemo(() => {
    switch (agent.primary_language) {
      case "te-en-IN":
        return "Telugu • English (Bilingual)";
      case "te-IN":
        return "Telugu (తెలుగు)";
      case "hi-IN":
        return "Hindi (हिन्दी)";
      case "hi-en-IN":
        return "Hindi • English (Hinglish)";
      case "en-IN":
        return "English (India)";
      default:
        return agent.primary_language || "Telugu • English";
    }
  }, [agent.primary_language]);

  // Resolve voice display name
  const voiceLabel = React.useMemo(() => {
    if (!voice) return "Sarvam Bulbul (Priya)";
    if (voice.provider === "sarvam_tts" || voice.provider === "sarvam") {
      return `Sarvam Bulbul (${voice.voice_id || "Priya"})`;
    }
    if (voice.voice_id?.includes("female")) return "Sarvam Bulbul (Priya)";
    if (voice.voice_id?.includes("male")) return "Sarvam Bulbul (Shubh)";
    return voice.voice_id || "Sarvam Bulbul (Priya)";
  }, [voice]);

  const cards = [
    {
      id: "languages",
      title: "Languages",
      icon: Globe,
      value: languageLabel,
      tag: "Code-Switching",
      detailBadge: version?.code_switching_behavior || "adaptive",
      info: "Auto-detects when the caller switches languages mid-call (e.g., Telugu to English or Hindi) and smoothly adapts without restarting the sentence.",
    },
    {
      id: "tts",
      title: "Voice (TTS)",
      icon: Volume2,
      value: voiceLabel,
      tag: `${voice?.speaking_speed ?? 1.0}x Speed`,
      detailBadge: "8kHz Telephony",
      info: "Synthesized via Indian voice models tuned for natural conversational rhythm, telephony bandwidth, and colloquial inflections.",
    },
    {
      id: "llm",
      title: "AI Model (LLM)",
      icon: Cpu,
      value: "GPT-4o-mini",
      tag: "~350ms TTFT",
      detailBadge: "Low Latency",
      info: "High-speed streaming reasoning engine generating context-aware dialogue turns, objection handling, and slot extraction.",
    },
    {
      id: "stt",
      title: "Transcription (STT)",
      icon: Mic,
      value: "Sarvam Saarika",
      tag: "Streaming Indic",
      detailBadge: "Sub-150ms",
      info: "Streaming speech-to-text with specialized Indian acoustic models, high background noise tolerance, and real-time turn detection.",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 pb-4 lg:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon;
        const isInfoOpen = activeInfo === card.id;

        return (
          <div
            key={card.id}
            className="group relative flex flex-col justify-between rounded-xl border border-border/80 bg-surface/90 p-3.5 shadow-sm transition-all duration-200 hover:border-primary/50 hover:bg-surface"
          >
            <div className="flex items-center justify-between pb-1">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Icon className="h-3.5 w-3.5 text-primary" />
                <span>{card.title}</span>
              </div>
              <button
                type="button"
                onClick={() => setActiveInfo(isInfoOpen ? null : card.id)}
                className="rounded p-0.5 text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
                title="View details"
                aria-label={`Details for ${card.title}`}
              >
                <Info className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="my-1">
              <p className="truncate text-sm font-semibold tracking-tight text-foreground" title={card.value}>
                {card.value}
              </p>
            </div>

            <div className="flex items-center gap-1.5 pt-1 text-[11px]">
              <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-primary">
                {card.tag}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {card.detailBadge}
              </span>
            </div>

            {/* Info popover tooltip */}
            {isInfoOpen && (
              <div className="absolute left-0 top-full z-30 mt-1.5 w-64 rounded-lg border border-primary/30 bg-surface-raised p-2.5 text-xs text-foreground shadow-xl backdrop-blur-md">
                <div className="mb-1 flex items-center justify-between font-semibold text-primary">
                  <span>{card.title} Details</span>
                  <button
                    type="button"
                    onClick={() => setActiveInfo(null)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    ✕
                  </button>
                </div>
                <p className="leading-relaxed text-muted-foreground">{card.info}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
