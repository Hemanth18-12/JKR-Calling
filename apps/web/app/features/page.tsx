import { buttonVariants } from "@jkr/ui";
import Link from "next/link";

const FEATURE_GROUPS = [
  { title: "Voice", items: ["Telugu / Hindi / English + code-switching", "Real interruption handling", "Human handoff"] },
  { title: "Revenue operations", items: ["Campaign engine with safety gate", "Lead scoring", "Appointment booking"] },
  { title: "Trust", items: ["Consent & suppression", "AI disclosure enforcement", "Full audit log"] },
];

export default function FeaturesPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        ← Back
      </Link>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">Features</h1>
      <div className="mt-8 grid gap-6 sm:grid-cols-3">
        {FEATURE_GROUPS.map((g) => (
          <div key={g.title} className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-sm font-semibold">{g.title}</h2>
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {g.items.map((i) => (
                <li key={i}>• {i}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
