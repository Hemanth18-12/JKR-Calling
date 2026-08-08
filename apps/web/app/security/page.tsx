import { buttonVariants } from "@jkr/ui";
import Link from "next/link";

const PRINCIPLES = [
  {
    title: "No real call by default",
    body: "Every workspace defaults every provider to a mock adapter. A real telephony dial requires an explicit environment flag and an authorized destination number — never on by default.",
  },
  {
    title: "Consent and suppression before every dial",
    body: "A ten-check safety gate — consent, suppression, calling-hours, attempt limits, duplicate-dispatch locks, budget and rate limits — runs before any outbound attempt, mock or real.",
  },
  {
    title: "Immediate, unconditional opt-out",
    body: "A do-not-call request takes effect synchronously, before the triggering call or flow even finishes. No retry or relaunch can override it.",
  },
  {
    title: "Tenant isolation at two layers",
    body: "Application-layer filtering and Postgres row-level security both scope every query to the active workspace — a bug in one layer doesn't expose another client's data.",
  },
  {
    title: "AI disclosure is enforced, not just written",
    body: "An agent's opening script is validated for a disclosure clause before it can be published, and every transcript is re-checked after the call.",
  },
];

export default function SecurityPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        ← Back
      </Link>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">Security &amp; safety model</h1>
      <p className="mt-3 text-muted-foreground">
        The short version: this platform is built so that unsafe or non-consensual calling is
        structurally hard to do by accident, not just discouraged in documentation.
      </p>
      <div className="mt-10 space-y-6">
        {PRINCIPLES.map((p) => (
          <div key={p.title} className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-sm font-semibold">{p.title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{p.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
