import { Badge, buttonVariants } from "@jkr/ui";
import { ArrowRight, Bot, Check, CheckCircle2, ChevronRight, Globe2, Headphones, Megaphone, PhoneCall, ShieldCheck, Sparkles, Zap } from "lucide-react";
import Link from "next/link";
import { LandingInteractive } from "@/components/landing/landing-interactive";

const FEATURES = [
  {
    icon: PhoneCall,
    title: "Calls that sound human, disclose they are AI",
    description:
      "Natural Telugu, Hindi, and English conversation with real interruption handling: every call opens with a brief, honest disclosure.",
    color: "text-primary",
  },
  {
    icon: Globe2,
    title: "Built for India, not translated for it",
    description:
      "Fluent Telugu-English and Hindi-English code-switching, authentic Indian names, rupee amounts, and calling-hours that respect local norms.",
    color: "text-amber-400",
  },
  {
    icon: ShieldCheck,
    title: "Safety before scale",
    description:
      "Consent, suppression, and calling-window checks run before every dial. No real call is ever placed without explicit authorization.",
    color: "text-emerald-400",
  },
];

const PRICING_TIERS = [
  {
    name: "Starter Recharge",
    price: "₹100",
    coins: "300 Coins",
    minutes: "5.0 Minutes of voice calls",
    features: [
      "Exact per-second billing (1 coin = 1 second)",
      "Telugu, Hindi, and English bilingual AI",
      "Real-time turn interruption handling",
      "Instant UPI QR activation",
    ],
    popular: false,
    cta: "Start Free",
  },
  {
    name: "Growth Tier",
    price: "₹250",
    coins: "850 Coins",
    minutes: "14.2 Minutes (+50 Bonus Coins)",
    features: [
      "Exact per-second billing with zero minute rounding",
      "Priority telephony routing via Twilio & Dograh",
      "Full conversation audio recordings & transcripts",
      "Live supervisor whisper & barge-in console",
    ],
    popular: true,
    cta: "Get Started",
  },
  {
    name: "Enterprise Scale",
    price: "₹400",
    coins: "1,350 Coins",
    minutes: "22.5 Minutes of talk time",
    features: [
      "Lowest cost per talk-second in India",
      "Dedicated low-latency streaming pipeline",
      "Multi-agent team support with custom personas",
      "Webhooks & calendar tool integrations",
    ],
    popular: false,
    cta: "Get Started",
  },
];

function BrandWaveform() {
  const bars = [4, 8, 14, 20, 26, 20, 24, 16, 9, 22, 26, 18, 7, 24, 20, 12, 26, 18, 9, 15];
  return (
    <div className="flex items-end justify-center gap-[3px] h-12" aria-hidden="true">
      {bars.map((h, i) => (
        <span
          key={i}
          className="w-[3px] rounded-full bg-primary/80 animate-pulse"
          style={{
            height: `${h}px`,
            animationDuration: `${0.7 + (i % 5) * 0.2}s`,
            animationDelay: `${(i % 4) * 0.1}s`,
          }}
        />
      ))}
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background font-sans text-foreground">
      {/* Background grid */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(#ffffff06_1px,transparent_1px)] [background-size:24px_24px]" aria-hidden="true" />

      {/* Navigation */}
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-5 border-b border-border/40">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-black font-bold shadow-sm">
            <Zap className="h-4 w-4 fill-black" />
          </div>
          <span className="font-display text-base font-bold tracking-tight text-foreground">JKR AI Calling</span>
        </div>
        <nav className="flex items-center gap-2.5">
          <Link href="/pricing" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Pricing
          </Link>
          <Link href="/login" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Log in
          </Link>
          <Link href="/signup" className={buttonVariants({ variant: "default", size: "sm" })}>
            <span className="font-bold">Get started</span>
            <ArrowRight className="h-3.5 w-3.5 ml-1" />
          </Link>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="relative z-10">
        <section className="mx-auto flex max-w-5xl flex-col items-center gap-7 px-6 pb-20 pt-16 text-center">
          <Badge variant="outline" className="gap-2 px-3 py-1 text-xs border-primary/40 text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
            India-first · Multilingual · Outcome-driven
          </Badge>

          {/* Waveform motif */}
          <div className="w-full max-w-xs my-1">
            <BrandWaveform />
          </div>

          <h1 className="font-display max-w-3xl text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl leading-[1.1]">
            An AI revenue agent that{" "}
            <span className="text-primary font-black">
              calls leads
            </span>
            , understands customers, and{" "}
            <span className="underline decoration-primary decoration-4 underline-offset-4">
              proves it worked
            </span>
            .
          </h1>

          <p className="max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            Not a toy bot. JKR AI Calling qualifies leads, answers from your approved
            knowledge, books appointments, and hands off to your team in Telugu, Hindi, English, or natural bilingual mixes.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <Link href="/signup" className={buttonVariants({ size: "lg", variant: "default" })}>
              <span className="font-bold">Start free in 2 minutes</span>
              <ArrowRight className="h-4 w-4 ml-1.5" />
            </Link>
            <Link href="/security" className={buttonVariants({ size: "lg", variant: "outline" })}>
              See our safety model
            </Link>
          </div>

          {/* Real Metrics Strip */}
          <div className="mt-6 grid grid-cols-3 gap-6 rounded-xl border border-border/80 bg-surface px-8 py-4 shadow-sm">
            <div className="text-center">
              <p className="font-display text-2xl font-bold tabular-nums text-foreground">3</p>
              <p className="text-xs text-muted-foreground font-medium">Native Indic Languages</p>
            </div>
            <div className="text-center border-x border-border/40 px-6">
              <p className="font-display text-2xl font-bold tabular-nums text-primary">10</p>
              <p className="text-xs text-muted-foreground font-medium">Compliance Safety Checks</p>
            </div>
            <div className="text-center">
              <p className="font-display text-2xl font-bold tabular-nums text-foreground">₹32</p>
              <p className="text-xs text-muted-foreground font-medium">Avg. Cost Per Booking</p>
            </div>
          </div>
        </section>

        {/* Live Interactive Product Preview & Voice Player */}
        <section className="pb-24">
          <LandingInteractive />
        </section>

        {/* Value Proposition Cards */}
        <section className="mx-auto max-w-6xl px-6 pb-24">
          <div className="text-center mb-10">
            <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              Engineered for genuine business trust
            </h2>
            <p className="text-sm text-muted-foreground mt-1 max-w-lg mx-auto">
              Every turn is governed by strict tenant isolation, safety checks, and compliant disclosure.
            </p>
          </div>

          <div className="grid gap-5 sm:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group rounded-xl border border-border/80 bg-surface p-6 shadow-sm transition-all duration-200 hover:border-primary/50"
              >
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-border/80 bg-surface-raised">
                  <f.icon className={`h-5 w-5 ${f.color}`} />
                </div>
                <h3 className="mb-2 font-display text-base font-semibold text-foreground">{f.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{f.description}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Honest Pricing in Coins Section */}
        <section className="mx-auto max-w-6xl px-6 pb-28 border-t border-border/40 pt-20">
          <div className="text-center mb-12">
            <Badge variant="outline" className="border-primary/40 text-primary mb-2 text-xs">
              Transparent Pricing
            </Badge>
            <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              Transparent coin packages. Zero hidden telephony fees.
            </h2>
            <p className="text-sm text-muted-foreground mt-1.5 max-w-xl mx-auto">
              1 Coin = 1 Second of live AI conversation. Pay only for exact talk seconds without minute rounding.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {PRICING_TIERS.map((tier) => (
              <div
                key={tier.name}
                className={`relative rounded-2xl border p-6 flex flex-col justify-between transition-all ${
                  tier.popular
                    ? "border-primary bg-surface shadow-md"
                    : "border-border/80 bg-surface/70"
                }`}
              >
                {tier.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-[11px] font-bold text-black uppercase tracking-wider">
                    Most Popular
                  </div>
                )}

                <div>
                  <h3 className="font-display text-base font-bold text-foreground">{tier.name}</h3>
                  <div className="mt-3 flex items-baseline gap-1">
                    <span className="font-display text-3xl font-extrabold text-foreground num-tabular">{tier.price}</span>
                    <span className="text-xs text-muted-foreground">one-time</span>
                  </div>
                  <div className="mt-1 rounded-md bg-surface-raised px-2.5 py-1 text-xs font-semibold text-primary inline-block">
                    {tier.coins} · <span className="text-foreground">{tier.minutes}</span>
                  </div>

                  <ul className="mt-6 space-y-2.5 text-xs text-muted-foreground">
                    {tier.features.map((feat) => (
                      <li key={feat} className="flex items-start gap-2">
                        <Check className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="pt-6 mt-6 border-t border-border/40">
                  <Link
                    href="/signup"
                    className={buttonVariants({
                      variant: tier.popular ? "default" : "outline",
                      className: "w-full font-bold text-xs h-10",
                    })}
                  >
                    {tier.cta}
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border/40 py-8 text-center bg-surface/40">
        <p className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} JKR AI Calling.{" "}
          <span className="text-foreground font-medium">No real call is ever placed without explicit authorization:</span> every
          workspace defaults to mock providers.
        </p>
      </footer>
    </div>
  );
}
