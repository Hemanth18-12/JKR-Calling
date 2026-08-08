import { buttonVariants } from "@jkr/ui";
import Link from "next/link";

const INDUSTRIES = [
  { name: "Healthcare & dental", use_case: "Appointment booking, treatment enquiry follow-up" },
  { name: "Education", use_case: "Admission lead qualification, campus visit booking" },
  { name: "Professional services", use_case: "Consultation booking, lead qualification" },
];

export default function IndustriesPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        ← Back
      </Link>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">Industries</h1>
      <div className="mt-8 space-y-4">
        {INDUSTRIES.map((i) => (
          <div key={i.name} className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-sm font-semibold">{i.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{i.use_case}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
