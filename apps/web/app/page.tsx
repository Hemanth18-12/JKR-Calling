import { Badge, buttonVariants } from "@jkr/ui";
import { ArrowRight, Globe2, PhoneCall, ShieldCheck, Zap } from "lucide-react";
import Link from "next/link";

const FEATURES = [
  {
    icon: PhoneCall,
    title: "Calls that sound human, disclose they're not",
    description:
      "Natural Telugu, Hindi and English conversation with real interruption handling — every call opens with a brief, honest AI disclosure.",
    color: "text-primary",
    bg: "bg-primary/10 border-primary/20",
  },
  {
    icon: Globe2,
    title: "Built for India, not translated for it",
    description:
      "Telugu-English and Hindi-English code-switching, Indian names, rupee amounts, and calling-hours that respect local norms.",
    color: "text-[#FFA94D]",
    bg: "bg-amber-500/10 border-amber-500/20",
  },
  {
    icon: ShieldCheck,
    title: "Safety before scale",
    description:
      "Consent, suppression and calling-window checks run before every dial. No real call is ever placed without explicit authorization.",
    color: "text-secondary",
    bg: "bg-secondary/10 border-secondary/20",
  },
];

const STATS = [
  { value: "3", label: "Languages" },
  { value: "10", label: "Safety checks" },
  { value: "0", label: "Real calls without consent" },
];

function WaveformHero() {
  const bars = [3, 7, 12, 18, 24, 18, 22, 14, 8, 20, 24, 16, 6, 22, 18, 10, 24, 16, 8, 14];
  return (
    <div className="flex items-end justify-center gap-[3px]" aria-hidden="true" style={{ height: 56 }}>
      {bars.map((h, i) => (
        <span
          key={i}
          className={`w-[3px] rounded-full bg-secondary/70 ${
            i % 4 === 0
              ? "animate-wave-1"
              : i % 4 === 1
                ? "animate-wave-2"
                : i % 4 === 2
                  ? "animate-wave-3"
                  : "animate-wave-4"
          }`}
          style={{ height: h }}
        />
      ))}
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background font-sans">
      {/* Ambient background gradient orbs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute left-1/4 top-0 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-primary/10 blur-[120px]" />
        <div className="absolute right-1/4 top-40 h-[400px] w-[400px] rounded-full bg-secondary/8 blur-[100px]" />
        <div className="absolute bottom-20 left-1/3 h-[300px] w-[300px] rounded-full bg-primary/6 blur-[80px]" />
      </div>

      {/* Navigation */}
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#5B3FE4] shadow-lg shadow-primary/30">
            <Zap className="h-4 w-4 text-white" />
          </div>
          <span className="font-display text-base font-bold tracking-tight text-foreground">JKR AI Calling</span>
        </div>
        <nav className="flex items-center gap-2">
          <Link href="/login" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Log in
          </Link>
          <Link href="/signup" className={buttonVariants({ variant: "gradient", size: "sm" })}>
            Get started <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <main className="relative z-10">
        <section className="mx-auto flex max-w-5xl flex-col items-center gap-8 px-6 pb-24 pt-16 text-center">
          <Badge variant="live" className="gap-2 px-3 py-1 text-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-secondary animate-pulse" />
            India-first · Multilingual · Outcome-driven
          </Badge>

          {/* Waveform motif */}
          <div className="w-full max-w-xs">
            <WaveformHero />
          </div>

          <h1 className="font-display max-w-3xl text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
            An AI revenue agent that{" "}
            <span className="bg-gradient-to-r from-primary to-[#A78BFF] bg-clip-text text-transparent">
              calls leads
            </span>
            , understands customers, and{" "}
            <span className="bg-gradient-to-r from-secondary to-[#5EEAD4] bg-clip-text text-transparent">
              proves it worked
            </span>
            .
          </h1>

          <p className="max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            Not a chatbot with text-to-speech bolted on. JKR AI Calling qualifies leads, answers from your approved
            knowledge, books appointments, and hands off to your team — in Telugu, Hindi, English, or a natural mix of
            both.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link href="/signup" className={buttonVariants({ size: "lg", variant: "gradient" })}>
              Start free <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/security" className={buttonVariants({ size: "lg", variant: "outline" })}>
              See our safety model
            </Link>
          </div>

          {/* Stats strip */}
          <div className="mt-4 flex items-center gap-8 rounded-2xl border border-border/60 bg-surface/60 px-8 py-4 backdrop-blur-md">
            {STATS.map((s, i) => (
              <div key={s.label} className={`text-center ${i !== 0 ? "border-l border-border/40 pl-8" : ""}`}>
                <p className="font-display text-2xl font-bold tabular-nums text-foreground">{s.value}</p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Feature cards */}
        <section className="mx-auto max-w-6xl px-6 pb-24">
          <div className="grid gap-5 sm:grid-cols-3">
            {FEATURES.map((f, i) => (
              <div
                key={f.title}
                className={`stagger-${i + 1} group rounded-2xl border p-6 transition-all duration-200 hover:-translate-y-1 hover:shadow-lg ${f.bg}`}
              >
                <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl border ${f.bg}`}>
                  <f.icon className={`h-5 w-5 ${f.color}`} />
                </div>
                <h3 className="mb-2 font-display text-sm font-semibold text-foreground">{f.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{f.description}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border/40 py-8 text-center">
        <p className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} JKR AI Calling.{" "}
          <span className="text-secondary">No real call is ever placed without explicit authorization</span> — every
          workspace defaults to mock providers.
        </p>
      </footer>
    </div>
  );
}
