"use client";

import { Badge, Button } from "@jkr/ui";
import {
  Bot,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  GripVertical,
  HelpCircle,
  MessageSquare,
  Minus,
  RotateCcw,
  Search,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

interface FAQItem {
  id: string;
  category: "voice" | "safety" | "workflows" | "platform";
  question: string;
  answer: string;
  bullets?: string[];
  linkHref?: string;
  linkLabel?: string;
  badge?: string;
}

const FAQ_DATA: FAQItem[] = [
  {
    id: "what-is-jkr",
    category: "platform",
    question: "What is JKR AI Calling?",
    answer:
      "JKR AI Calling is an India-first AI voice platform engineered for ultra-low latency telephone conversations. It combines streaming Indian language STT/TTS, deterministic turn routing, and multi-tenant telephony infrastructure.",
    bullets: [
      "Sub-second response latency with FastTurnRouter.",
      "Native support for Telugu, Hindi, and Indian English.",
      "Complete multi-tenant workspace isolation with PostgreSQL Row-Level Security.",
    ],
    badge: "Overview",
    linkHref: "/app/dashboard",
    linkLabel: "Go to Dashboard",
  },
  {
    id: "language-vocab",
    category: "voice",
    question: "How does the Indian language & phonetic vocabulary feature work?",
    answer:
      "Voice agents use Sarvam AI for real-time speech recognition and synthesis. The built-in Domain Vocabulary engine maps Indian regional accents, colloquialisms, and common phonetic mis-transcriptions to exact canonical terms.",
    bullets: [
      "Example: Automatically maps misheard words like 'fruit canals' to 'root canal'.",
      "Assign domain vocabularies to specific agents in the Persona Editor.",
      "Custom phonetic aliases for Telugu (te-IN), Hindi (hi-IN), and Indian English (en-IN).",
    ],
    badge: "Voice & AI",
    linkHref: "/app/agents",
    linkLabel: "Configure Agent Vocabularies",
  },
  {
    id: "safety-disclosure",
    category: "safety",
    question: "What is the Safety Disclosure & Consent Gate?",
    answer:
      "Every outbound and inbound call strictly enforces India compliance rules. Before collecting sensitive info or executing tools, the agent announces its AI identity and records customer consent.",
    bullets: [
      "Mandatory AI disclosure statement configured per agent persona.",
      "Explicit consent status (Granted / Revoked) logged with cryptographic timestamps.",
      "Immediate human callback handoff if customer requests a real representative.",
    ],
    badge: "Compliance",
    linkHref: "/app/compliance",
    linkLabel: "View Compliance Rules",
  },
  {
    id: "barge-in",
    category: "voice",
    question: "How does automatic Barge-in work when a customer interrupts?",
    answer:
      "When a customer begins speaking while the AI agent is mid-sentence, the low-latency Voice Activity Detection (VAD) pipeline detects speech in under 200ms.",
    bullets: [
      "Instantly halts TTS speech synthesis.",
      "Sends a clear packet to Twilio Media Streams to flush the caller's audio buffer.",
      "Seamlessly answers the customer's new question without awkward overlapping audio.",
    ],
    badge: "Real-time Voice",
  },
  {
    id: "appointments-crm",
    category: "workflows",
    question: "How do agents book appointments and update CRM leads?",
    answer:
      "Agents execute server-side tools during the call. When a customer agrees to a time slot, the agent calls the book_appointment tool, which validates availability and logs the event.",
    bullets: [
      "Available tools: check_calendar_slots, book_appointment, reschedule, cancel, create_crm_lead.",
      "All bookings appear immediately in the Appointments & Contacts tabs.",
      "Enforces daily & monthly workspace budget caps to prevent accidental overages.",
    ],
    badge: "Workflows",
    linkHref: "/app/appointments",
    linkLabel: "View Appointments",
  },
  {
    id: "providers-telephony",
    category: "platform",
    question: "Which telephony and AI providers are connected?",
    answer:
      "JKR AI Calling connects directly with best-in-class Indian voice and language infrastructure:",
    bullets: [
      "Telephony: Twilio Media Streams (WebSocket transport).",
      "STT & TTS: Sarvam AI for natural Indian accents and fast transcription.",
      "Intelligence: OpenAI GPT models for contextual reasoning and tool calling.",
    ],
    badge: "Integrations",
    linkHref: "/app/integrations",
    linkLabel: "Manage Providers",
  },
  {
    id: "launch-campaign",
    category: "workflows",
    question: "How do I launch an automated voice calling campaign?",
    answer:
      "You can launch targeted outbound campaigns in 4 simple steps:",
    bullets: [
      "1. Upload your customer contact list via CSV in the Contacts tab.",
      "2. Select or create a published Agent Persona.",
      "3. Set your campaign schedule, concurrency limits, and retry policy.",
      "4. Click 'Start Campaign' and monitor live call outcomes in real time.",
    ],
    badge: "Campaigns",
    linkHref: "/app/campaigns",
    linkLabel: "Create a Campaign",
  },
  {
    id: "data-isolation",
    category: "safety",
    question: "Is my organization's data isolated and secure?",
    answer:
      "Yes. JKR AI Calling employs strict multi-tenant architecture with PostgreSQL Row-Level Security (RLS). Users and API sessions are cryptographically bound to their active workspace.",
    bullets: [
      "Tenant-isolated databases and encrypted session cookies (SameSite & Secure).",
      "9 Granular RBAC permission roles (Workspace Owner, Admin, Agent Manager, etc.).",
      "Comprehensive immutable audit trail logging all actions and call recordings.",
    ],
    badge: "Security",
    linkHref: "/app/settings",
    linkLabel: "Workspace Settings",
  },
];

const CATEGORIES = [
  { id: "all", label: "All Questions" },
  { id: "voice", label: "Voice & AI" },
  { id: "safety", label: "Safety & Policy" },
  { id: "workflows", label: "Workflows & Tools" },
  { id: "platform", label: "Platform & Security" },
];

export function FaqChatbox() {
  const [isOpen, setIsOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedCategory, setSelectedCategory] = React.useState("all");
  const [expandedId, setExpandedId] = React.useState<string | null>("what-is-jkr");

  // Position state with default at bottom-right
  const [position, setPosition] = React.useState<{ x: number; y: number }>({ x: 24, y: 24 });
  const [isDragging, setIsDragging] = React.useState(false);
  const dragRef = React.useRef<{
    startX: number;
    startY: number;
    initialPosX: number;
    initialPosY: number;
    hasDragged: boolean;
  }>({
    startX: 0,
    startY: 0,
    initialPosX: 24,
    initialPosY: 24,
    hasDragged: false,
  });

  // Load saved position from localStorage on mount
  React.useEffect(() => {
    try {
      const saved = localStorage.getItem("jkr_faq_position");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.x === "number" && typeof parsed.y === "number") {
          setPosition(parsed);
        }
      }
    } catch {
      // Ignore storage errors
    }
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Only drag with left click or touch
    if (e.button !== 0) return;
    setIsDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialPosX: position.x,
      initialPosY: position.y,
      hasDragged: false,
    };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    const deltaX = dragRef.current.startX - e.clientX;
    const deltaY = dragRef.current.startY - e.clientY;

    if (Math.abs(deltaX) > 4 || Math.abs(deltaY) > 4) {
      dragRef.current.hasDragged = true;
    }

    const maxX = Math.max(20, window.innerWidth - (isOpen ? 400 : 70));
    const maxY = Math.max(20, window.innerHeight - (isOpen ? 540 : 70));

    const newX = Math.min(Math.max(16, dragRef.current.initialPosX + deltaX), maxX);
    const newY = Math.min(Math.max(16, dragRef.current.initialPosY + deltaY), maxY);

    setPosition({ x: newX, y: newY });
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setIsDragging(false);
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      localStorage.setItem("jkr_faq_position", JSON.stringify(position));
    } catch {
      // Ignore
    }
  };

  const resetPosition = () => {
    const defaultPos = { x: 24, y: 24 };
    setPosition(defaultPos);
    try {
      localStorage.setItem("jkr_faq_position", JSON.stringify(defaultPos));
    } catch {
      // Ignore
    }
  };

  const filteredFAQs = FAQ_DATA.filter((faq) => {
    const matchesCategory = selectedCategory === "all" || faq.category === selectedCategory;
    const q = searchQuery.toLowerCase().trim();
    const matchesSearch =
      !q ||
      faq.question.toLowerCase().includes(q) ||
      faq.answer.toLowerCase().includes(q) ||
      (faq.bullets && faq.bullets.some((b) => b.toLowerCase().includes(q)));
    return matchesCategory && matchesSearch;
  });

  return (
    <div
      style={{
        position: "fixed",
        right: `${position.x}px`,
        bottom: `${position.y}px`,
        zIndex: 9999,
      }}
      className="select-none font-sans"
    >
      {!isOpen ? (
        /* Collapsed Floating Launcher Button */
        <div
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onClick={() => {
            if (!dragRef.current.hasDragged) {
              setIsOpen(true);
            }
          }}
          className="group relative flex cursor-grab items-center gap-2 rounded-full border border-primary/40 bg-surface/90 px-4 py-3 shadow-2xl backdrop-blur-xl transition-all duration-200 hover:scale-105 hover:border-primary hover:shadow-primary/25 active:cursor-grabbing"
          title="Click to open FAQ assistant (Drag to move)"
        >
          {/* Ambient pulse glow */}
          <div className="absolute -inset-0.5 rounded-full bg-gradient-to-r from-primary to-[#5B3FE4] opacity-40 blur transition-all duration-300 group-hover:opacity-75" />

          <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-[#5B3FE4] text-white shadow-md">
            <MessageSquare className="h-4 w-4" />
          </div>

          <div className="relative hidden sm:block">
            <p className="text-xs font-semibold text-foreground">JKR AI Help</p>
            <p className="text-[10px] text-muted-foreground">FAQ & Quick Answers</p>
          </div>

          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-secondary opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-secondary" />
          </span>
        </div>
      ) : (
        /* Expanded Draggable Chatbox Window */
        <div
          className="flex h-[520px] w-[380px] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-2xl border border-border/80 bg-surface/95 shadow-2xl backdrop-blur-2xl transition-all duration-200"
          style={{ boxShadow: "0 20px 50px rgba(0, 0, 0, 0.4), 0 0 20px rgba(124, 92, 255, 0.15)" }}
        >
          {/* Drag Handle & Header */}
          <div
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            className="flex cursor-grab items-center justify-between border-b border-border/60 bg-surface-raised/80 px-4 py-3 active:cursor-grabbing"
          >
            <div className="flex items-center gap-2.5">
              <GripVertical className="h-4 w-4 text-muted-foreground/60" />
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[#5B3FE4] text-white shadow-sm">
                <Bot className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-foreground">JKR AI Voice Assistant</h3>
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
                  <span className="text-[10px] text-muted-foreground">Instant Q&A • Always online</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={resetPosition}
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                title="Reset position to bottom-right"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsOpen(false)}
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                title="Minimize FAQ"
              >
                <Minus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Search Box */}
          <div className="border-b border-border/40 p-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search questions (e.g. voice, safety, book)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-border bg-background/80 py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground/70 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {searchQuery ? (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              ) : null}
            </div>

            {/* Category Filter Pills */}
            <div className="mt-2.5 flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-none">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`whitespace-nowrap rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors ${
                    selectedCategory === cat.id
                      ? "bg-primary text-white shadow-sm"
                      : "bg-surface-raised text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>

          {/* FAQ Accordion List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
            {filteredFAQs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <HelpCircle className="h-8 w-8 text-muted-foreground/40 mb-2" />
                <p className="text-xs font-medium">No matching questions found</p>
                <p className="text-[10px] text-muted-foreground/70 mt-0.5">Try searching with a different keyword</p>
                <button
                  onClick={() => {
                    setSearchQuery("");
                    setSelectedCategory("all");
                  }}
                  className="mt-3 text-[11px] font-medium text-primary hover:underline"
                >
                  Clear search
                </button>
              </div>
            ) : (
              filteredFAQs.map((faq) => {
                const isExpanded = expandedId === faq.id;
                return (
                  <div
                    key={faq.id}
                    className={`overflow-hidden rounded-xl border transition-all duration-150 ${
                      isExpanded
                        ? "border-primary/50 bg-surface-raised/70 shadow-sm"
                        : "border-border/60 bg-background/50 hover:border-border hover:bg-surface-raised/40"
                    }`}
                  >
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : faq.id)}
                      className="flex w-full items-start justify-between gap-2 p-3 text-left"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-1">
                          {faq.badge ? (
                            <Badge variant="outline" className="text-[9px] px-1.5 py-0">
                              {faq.badge}
                            </Badge>
                          ) : null}
                        </div>
                        <h4 className="text-xs font-semibold text-foreground leading-snug">
                          {faq.question}
                        </h4>
                      </div>
                      <div className="shrink-0 mt-0.5 text-muted-foreground">
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4 text-primary" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </div>
                    </button>

                    {isExpanded ? (
                      <div className="border-t border-border/40 px-3 pb-3 pt-2 text-xs text-muted-foreground space-y-2">
                        <p className="text-foreground/90 leading-relaxed">{faq.answer}</p>

                        {faq.bullets && faq.bullets.length > 0 ? (
                          <ul className="space-y-1 pl-1 text-[11px] text-muted-foreground/90">
                            {faq.bullets.map((b, idx) => (
                              <li key={idx} className="flex items-start gap-1.5">
                                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-primary" />
                                <span>{b}</span>
                              </li>
                            ))}
                          </ul>
                        ) : null}

                        {faq.linkHref && faq.linkLabel ? (
                          <div className="pt-1.5">
                            <Link
                              href={faq.linkHref as never}
                              onClick={() => setIsOpen(false)}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
                            >
                              <span>{faq.linkLabel}</span>
                              <ExternalLink className="h-3 w-3" />
                            </Link>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>

          {/* Footer Notice */}
          <div className="border-t border-border/50 bg-surface-raised/40 px-3 py-2 text-center text-[10px] text-muted-foreground">
            <span>💡 Tip: Click & drag top bar anywhere to move this box</span>
          </div>
        </div>
      )}
    </div>
  );
}
