import { buttonVariants } from "@jkr/ui";
import Link from "next/link";

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-16 text-center">
      <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        ← Back
      </Link>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">Pricing</h1>
      <p className="mt-3 text-muted-foreground">
        Usage-based pricing tied to telephony seconds, STT/LLM/TTS usage and messages — see{" "}
        <span className="font-mono text-sm">/app/billing</span> once inside a workspace for a live
        breakdown. Talk to us for a plan tailored to your call volume.
      </p>
      <Link href="/signup" className={buttonVariants({ variant: "gradient", className: "mt-6" })}>
        Start free
      </Link>
    </div>
  );
}
