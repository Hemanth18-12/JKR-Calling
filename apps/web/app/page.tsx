import { Badge, buttonVariants } from "@jkr/ui";
import { ArrowRight, Globe2, PhoneCall, ShieldCheck } from "lucide-react";
import Link from "next/link";

const FEATURES = [
  {
    icon: PhoneCall,
    title: "Calls that sound human, disclose they're not",
    description:
      "Natural Telugu, Hindi and English conversation with real interruption handling — every call opens with a brief, honest AI disclosure.",
  },
  {
    icon: Globe2,
    title: "Built for India, not translated for it",
    description:
      "Telugu-English and Hindi-English code-switching, Indian names, rupee amounts, and calling-hours that respect local norms.",
  },
  {
    icon: ShieldCheck,
    title: "Safety before scale",
    description:
      "Consent, suppression and calling-window checks run before every dial. No real call is ever placed without explicit authorization.",
  },
];

export default function LandingPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-6">
      <header className="flex items-center justify-between py-6">
        <span className="text-lg font-semibold tracking-tight">JKR AI Calling</span>
        <nav className="flex items-center gap-2">
          <Link href="/login" className={buttonVariants({ variant: "ghost" })}>
            Log in
          </Link>
          <Link href="/signup" className={buttonVariants({ variant: "gradient" })}>
            Get started <ArrowRight className="h-4 w-4" />
          </Link>
        </nav>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-8 py-20 text-center">
        <Badge variant="secondary" className="text-xs">
          India-first · Multilingual · Outcome-driven
        </Badge>
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          An AI revenue agent that calls leads, understands customers, and proves it worked.
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          Not a chatbot with text-to-speech bolted on. JKR AI Calling qualifies leads, answers from
          your approved knowledge, books appointments, and hands off to your team — in Telugu,
          Hindi, English, or a natural mix of both.
        </p>
        <div className="flex gap-3">
          <Link href="/signup" className={buttonVariants({ size: "lg", variant: "gradient" })}>
            Start free <ArrowRight className="h-4 w-4" />
          </Link>
          <Link href="/security" className={buttonVariants({ size: "lg", variant: "outline" })}>
            See our safety model
          </Link>
        </div>

        <div className="mt-16 grid gap-6 text-left sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-lg border border-border bg-surface p-6">
              <f.icon className="mb-3 h-6 w-6 text-primary" />
              <h3 className="mb-1 text-sm font-semibold">{f.title}</h3>
              <p className="text-sm text-muted-foreground">{f.description}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-border py-6 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} JKR AI Calling. No real call is ever placed without explicit
        authorization — every workspace defaults to mock providers.
      </footer>
    </div>
  );
}
