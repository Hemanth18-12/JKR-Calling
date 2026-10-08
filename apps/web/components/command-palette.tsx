"use client";

import {
  BarChart3,
  Bot,
  Calendar,
  Coins,
  FileText,
  Handshake,
  Home,
  Megaphone,
  MessageSquareText,
  Phone,
  PhoneCall,
  Search,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface CommandItem {
  id: string;
  title: string;
  category: "Navigation" | "Actions";
  href?: string;
  icon: React.ComponentType<{ className?: string }>;
  keywords?: string[];
  action?: () => void;
}

const COMMANDS: CommandItem[] = [
  { id: "dash", title: "Dashboard", category: "Navigation", href: "/app/dashboard", icon: Home, keywords: ["home", "stats", "overview"] },
  { id: "agents", title: "Agents & Studio", category: "Navigation", href: "/app/agents", icon: Bot, keywords: ["bot", "voice", "prompts"] },
  { id: "widget", title: "Website Widget Studio", category: "Navigation", href: "/app/widget", icon: Sparkles, keywords: ["embed", "floating", "web"] },
  { id: "knowledge", title: "Knowledge Base Documents", category: "Navigation", href: "/app/knowledge/documents", icon: MessageSquareText, keywords: ["docs", "faq", "rag"] },
  { id: "campaigns", title: "Outbound Calling Campaigns", category: "Navigation", href: "/app/campaigns", icon: Megaphone, keywords: ["broadcast", "run", "batch"] },
  { id: "contacts", title: "Contact Lists & Leads", category: "Navigation", href: "/app/contacts", icon: Users, keywords: ["phonebook", "audience"] },
  { id: "calls", title: "Call Logs & Transcripts", category: "Navigation", href: "/app/calls", icon: Phone, keywords: ["history", "recordings", "audio"] },
  { id: "live", title: "Live Real-Time Call Console", category: "Navigation", href: "/app/calls/live", icon: PhoneCall, keywords: ["active", "monitor", "listen"] },
  { id: "followups", title: "Follow-up SMS & WhatsApp", category: "Navigation", href: "/app/follow-ups", icon: MessageSquareText, keywords: ["messaging", "post-call"] },
  { id: "handoffs", title: "Human Agent Handoffs", category: "Navigation", href: "/app/handoffs", icon: Handshake, keywords: ["transfer", "escalation"] },
  { id: "appointments", title: "Scheduled Appointments", category: "Navigation", href: "/app/appointments", icon: Calendar, keywords: ["booking", "calendar"] },
  { id: "analytics", title: "Analytics & Conversion Metrics", category: "Navigation", href: "/app/analytics", icon: BarChart3, keywords: ["roi", "charts", "graphs"] },
  { id: "billing", title: "Billing, Plans & Coins Wallet", category: "Navigation", href: "/app/billing", icon: Coins, keywords: ["credits", "recharge", "tokens"] },
  { id: "settings", title: "Workspace & Voice Engine Settings", category: "Navigation", href: "/app/settings", icon: Settings, keywords: ["config", "api keys", "twilio"] },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [selectedIndex, setSelectedIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Global Ctrl+K / Cmd+K listener
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      } else if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  // Focus input when opened
  React.useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filteredCommands = React.useMemo(() => {
    if (!query.trim()) return COMMANDS;
    const q = query.toLowerCase();
    return COMMANDS.filter(
      (cmd) =>
        cmd.title.toLowerCase().includes(q) ||
        cmd.category.toLowerCase().includes(q) ||
        cmd.keywords?.some((k) => k.toLowerCase().includes(q))
    );
  }, [query]);

  // Reset selected index when filtered list changes
  React.useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleSelect = (cmd: CommandItem) => {
    setOpen(false);
    if (cmd.href) {
      router.push(cmd.href as never);
    } else if (cmd.action) {
      cmd.action();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, filteredCommands.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filteredCommands.length) % Math.max(1, filteredCommands.length));
    } else if (e.key === "Enter" && filteredCommands[selectedIndex]) {
      e.preventDefault();
      handleSelect(filteredCommands[selectedIndex]);
    }
  };

  return (
    <>
      {/* Quick trigger button for top bar / header */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-border/80 bg-surface/60 hover:bg-surface-raised text-muted-foreground hover:text-foreground text-xs font-medium transition-all shadow-sm group"
        title="Open Command Palette (Cmd+K)"
      >
        <Search className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
        <span>Quick Jump...</span>
        <kbd className="hidden lg:inline-flex items-center gap-0.5 rounded border border-border bg-background px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground shadow-2xs">
          ⌘K
        </kbd>
      </button>

      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              aria-hidden="true"
            />

            {/* Modal Dialog */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -10 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              className="relative w-full max-w-lg rounded-2xl border border-primary/30 bg-surface/95 p-3 shadow-2xl backdrop-blur-xl z-10 overflow-hidden"
              onKeyDown={handleKeyDown}
            >
              {/* Search input header */}
              <div className="relative flex items-center border-b border-border/80 pb-2.5 pt-1 px-2">
                <Search className="h-4 w-4 text-primary shrink-0 mr-2.5" />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Type a command, page or search..."
                  className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-surface-raised transition-colors ml-2"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* List */}
              <div className="max-h-72 overflow-y-auto py-2 space-y-1">
                {filteredCommands.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    No results found for &quot;{query}&quot;
                  </div>
                ) : (
                  filteredCommands.map((cmd, index) => {
                    const isSelected = index === selectedIndex;
                    const Icon = cmd.icon;
                    return (
                      <button
                        key={cmd.id}
                        type="button"
                        onClick={() => handleSelect(cmd)}
                        onMouseEnter={() => setSelectedIndex(index)}
                        className={`w-full flex items-center justify-between rounded-xl px-3 py-2 text-left text-xs transition-colors ${
                          isSelected
                            ? "bg-primary/15 text-primary font-semibold border-l-2 border-primary"
                            : "text-foreground hover:bg-surface-raised"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon className={`h-4 w-4 ${isSelected ? "text-primary" : "text-muted-foreground"}`} />
                          <span>{cmd.title}</span>
                        </div>
                        <span className="text-[10px] text-muted-foreground/70 uppercase tracking-wider font-mono">
                          {cmd.category}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>

              {/* Footer hotkeys hint */}
              <div className="flex items-center justify-between border-t border-border/60 pt-2 px-2 text-[11px] text-muted-foreground">
                <div className="flex items-center gap-3">
                  <span>Use ↑ ↓ to navigate</span>
                  <span>↵ to select</span>
                </div>
                <span>ESC to close</span>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
