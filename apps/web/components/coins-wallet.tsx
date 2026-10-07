"use client";

import {
  COIN_TIERS,
  type CoinTier,
  type CoinTopupRequestOut,
  type CoinTransactionOut,
  type CoinWalletOut,
} from "@jkr/contracts";
import { coinsApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  useToast,
} from "@jkr/ui";
import {
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  Check,
  CheckCircle2,
  Clock,
  Coins,
  CreditCard,
  ExternalLink,
  History,
  PhoneCall,
  QrCode,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
  Upload,
  XCircle,
  Zap,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import * as React from "react";

interface CoinsWalletProps {
  workspaceId: string;
  initialWallet: CoinWalletOut;
  initialRequests: CoinTopupRequestOut[];
  initialTransactions: CoinTransactionOut[];
}

const TIER_FEATURES: Record<string, string[]> = {
  tier_100: [
    "300 Coins (5.0 Minutes of live talk time)",
    "Exact per-second billing (1 coin = 1 second)",
    "Telugu, Hindi, and English bilingual voice AI",
    "Real-time turn barge-in and audio streaming",
    "Standard concurrency (up to 5 lines)",
    "Instant UPI QR code payment activation",
  ],
  tier_250: [
    "850 Coins (14.2 Minutes — Includes +50 Bonus Coins)",
    "Exact per-second billing with zero minute rounding",
    "Priority telephony routing via Twilio & Dograh",
    "Telugu, Hindi, and English conversational models",
    "Call recording and transcript storage",
    "Real-time sentiment and slot extraction",
  ],
  tier_400: [
    "1,350 Coins (22.5 Minutes of high-volume talk time)",
    "Maximum coin yield per rupee spent",
    "Dedicated low-latency streaming pipeline",
    "Multi-agent team support with custom personas",
    "Full campaign webhooks and CRM integrations",
    "Highest priority support & account onboarding",
  ],
};

export function CoinsWallet({
  workspaceId,
  initialWallet,
  initialRequests,
  initialTransactions,
}: CoinsWalletProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [wallet, setWallet] = React.useState<CoinWalletOut>(initialWallet);
  const [requests, setRequests] = React.useState<CoinTopupRequestOut[]>(initialRequests);
  const [transactions, setTransactions] = React.useState<CoinTransactionOut[]>(initialTransactions);
  const [activeTab, setActiveTab] = React.useState<"tiers" | "requests" | "deductions">("tiers");

  const [previewModalUrl, setPreviewModalUrl] = React.useState<string | null>(null);

  const refreshData = async () => {
    try {
      const [w, r, t] = await Promise.all([
        coinsApi.getWallet(workspaceId),
        coinsApi.getTopupRequests(workspaceId),
        coinsApi.getTransactions(workspaceId),
      ]);
      setWallet(w);
      setRequests(r);
      setTransactions(t);
    } catch {
      // ignore
    }
  };

  const pendingRequests = requests.filter((r) => r.status === "pending");
  const balanceMinutes = Math.floor(wallet.balance_coins / 60);
  const balanceSeconds = wallet.balance_coins % 60;

  return (
    <div className="space-y-8">
      {/* Pattern 6 / OmniDimension Top Strip: Balance, Rate, Concurrency */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/80 bg-surface px-4 py-3 shadow-sm sm:px-6">
        <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm text-foreground">
          {/* Balance */}
          <div className="flex items-center gap-1.5 font-bold">
            <Coins className="h-4 w-4 text-primary" />
            <span>
              Balance:{" "}
              <strong className="text-foreground">
                🪙 {wallet.balance_coins.toLocaleString()} Coins
              </strong>{" "}
              <span className="text-muted-foreground">
                ({balanceMinutes}m {balanceSeconds}s available)
              </span>
            </span>
          </div>

          <span className="text-border">•</span>

          {/* Rate */}
          <div className="flex items-center gap-1.5">
            <Tag className="h-4 w-4 text-emerald-400" />
            <span>
              Rate: <strong className="text-foreground">1 coin / sec</strong>{" "}
              <span className="text-muted-foreground">(₹60/min equivalent)</span>
            </span>
          </div>

          <span className="text-border">•</span>

          {/* Concurrency */}
          <div className="flex items-center gap-1.5">
            <Zap className="h-4 w-4 text-amber-400" />
            <span>
              Concurrency: <strong className="text-foreground">5 Simultaneous Channels</strong>
            </span>
          </div>

          <span className="text-border">•</span>

          {/* Status */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span className="text-muted-foreground">UPI Checkout Active</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            const el = document.getElementById("recharge-tiers");
            el?.scrollIntoView({ behavior: "smooth" });
          }}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-black shadow-sm transition hover:bg-primary/90"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Recharge Wallet</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Main Coin Balance Card */}
        <Card className="relative overflow-hidden border-primary/40 bg-gradient-to-br from-primary/10 via-surface to-surface shadow-md">
          <div className="absolute right-3 top-3 opacity-15">
            <Coins className="h-20 w-20 text-primary" />
          </div>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
              Available Coin Balance
            </CardDescription>
            <CardTitle className="text-3xl font-black flex items-center gap-2 text-foreground">
              <span>🪙</span>
              <span>{wallet.balance_coins.toLocaleString()}</span>
              <span className="text-xs font-normal text-muted-foreground self-end pb-1">coins</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-1">
            <p>
              ⚡ <strong>1 coin = 1 second</strong> of live conversation.
            </p>
            <p>
              Available talk time:{" "}
              <strong className="text-foreground">
                {balanceMinutes}m {balanceSeconds}s
              </strong>
            </p>
          </CardContent>
        </Card>

        {/* Total Recharged */}
        <Card className="border-border/70 bg-surface">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <ArrowDownRight className="h-3.5 w-3.5 text-emerald-400" />
              Total Coins Recharged
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-foreground">
              +{wallet.total_recharged_coins.toLocaleString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Lifetime approved UPI top-up credits.
          </CardContent>
        </Card>

        {/* Total Spent */}
        <Card className="border-border/70 bg-surface">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <ArrowUpRight className="h-3.5 w-3.5 text-amber-400" />
              Total Call Seconds Spent
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-foreground">
              -{wallet.total_spent_coins.toLocaleString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Exact per-second deductions from connected calls.
          </CardContent>
        </Card>
      </div>

      {/* Pending Approval Notice if any */}
      {pendingRequests.length > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-xs space-y-1.5">
          <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm">
            <Clock className="h-4 w-4 animate-spin" />
            <span>You have {pendingRequests.length} top-up payment(s) pending admin verification</span>
          </div>
          <p className="text-muted-foreground leading-relaxed">
            Your payment proof for{" "}
            <strong>
              {pendingRequests.map((r) => `₹${r.price_inr} (${r.total_coins} coins)`).join(", ")}
            </strong>{" "}
            has been received. As soon as the transaction is confirmed, coins will appear immediately in your balance.
          </p>
        </div>
      )}

      {/* Pattern 6: Top-up Tiers in Clean Rounded INR Figures (OmniDimension Structure) */}
      <div id="recharge-tiers" className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/60 pb-3">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              <span>Recharge Tiers — Clean INR Pricing</span>
            </h2>
            <p className="text-xs text-muted-foreground">
              Transparent, rounded pricing packages. No awkward decimals or hidden transaction fees.
            </p>
          </div>
          <Badge variant="outline" className="self-start sm:self-auto border-primary/40 text-primary">
            1 Coin = 1 Second of AI Voice
          </Badge>
        </div>

        {/* Tiers Comparison Grid */}
        <div className="grid gap-6 md:grid-cols-3">
          {COIN_TIERS.map((tier) => {
            const isPopular = tier.id === "tier_250";
            const features = TIER_FEATURES[tier.id] || [];

            return (
              <div
                key={tier.id}
                className={`relative flex flex-col justify-between rounded-2xl border p-6 shadow-md transition-all duration-200 ${
                  isPopular
                    ? "border-primary bg-gradient-to-b from-primary/10 via-surface to-surface shadow-primary/10 ring-1 ring-primary"
                    : "border-border/80 bg-surface hover:border-border"
                }`}
              >
                {/* Popular / Tag Badge */}
                {tier.tag && (
                  <div className="absolute -top-3 right-6 rounded-full bg-gradient-to-r from-amber-400 to-yellow-500 px-3 py-0.5 text-[10px] font-black uppercase tracking-wider text-black shadow-md">
                    {tier.tag}
                  </div>
                )}

                <div>
                  {/* Tier Title */}
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      {tier.label ?? "Package"}
                    </span>
                  </div>

                  {/* Clean Rounded INR Price */}
                  <div className="mb-4 flex items-baseline gap-1">
                    <span className="text-3xl font-black text-foreground">₹{tier.price_inr}</span>
                    <span className="text-xs font-medium text-muted-foreground">one-time top-up</span>
                  </div>

                  {/* Coin Volume Display */}
                  <div className="mb-5 rounded-xl border border-border/60 bg-surface-raised p-3">
                    <div className="flex items-center gap-2 text-2xl font-black text-foreground">
                      <Coins className="h-5 w-5 text-primary" />
                      <span>{tier.total_coins.toLocaleString()}</span>
                      <span className="text-xs font-normal text-muted-foreground">Coins</span>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {tier.bonus_coins > 0 ? (
                        <>
                          {tier.base_coins} base +{" "}
                          <strong className="text-emerald-400 font-bold">+{tier.bonus_coins} bonus coins</strong>
                        </>
                      ) : (
                        `Equivalent to ${Math.floor(tier.total_coins / 60)} minutes of live voice`
                      )}
                    </p>
                  </div>

                  {/* Features List */}
                  <div className="mb-6 space-y-2.5">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      What&apos;s Included:
                    </p>
                    {features.map((feat, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-xs text-foreground">
                        <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400 mt-0.5" />
                        <span className="leading-snug">{feat}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Direct CTA */}
                <Button
                  variant={isPopular ? "gradient" : "secondary"}
                  size="default"
                  className="w-full font-bold shadow-sm"
                  onClick={() => router.push(`/app/billing/pay?tier=${tier.id}`)}
                >
                  Recharge ₹{tier.price_inr} with UPI QR →
                </Button>
              </div>
            );
          })}
        </div>
      </div>

      {/* History Sections: Top-up Requests & Call Deductions */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Top-up Requests History */}
        <Card className="border-border/70 bg-surface">
          <CardHeader className="pb-3 border-b border-border/40">
            <CardTitle className="text-sm font-semibold flex items-center gap-2 text-foreground">
              <History className="h-4 w-4 text-primary" />
              <span>UPI Top-up Verification History</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Status of your submitted UPI payment screenshots.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            {requests.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                No top-up requests yet. Select a tier above to recharge.
              </p>
            ) : (
              <div className="space-y-3">
                {requests.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center justify-between rounded-xl border border-border/60 bg-surface-raised/40 p-3 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <strong className="text-foreground">₹{r.price_inr}</strong>
                        <span className="text-muted-foreground">({r.total_coins} coins)</span>
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        {new Date(r.created_at).toLocaleString("en-IN", {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </p>
                      {r.admin_notes && (
                        <p className="text-[11px] text-amber-300 italic">Note: {r.admin_notes}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {r.status === "pending" && (
                        <Badge variant="outline" className="text-amber-400 border-amber-500/30">
                          Pending Review
                        </Badge>
                      )}
                      {r.status === "approved" && (
                        <Badge variant="success" className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                          Approved
                        </Badge>
                      )}
                      {r.status === "rejected" && (
                        <Badge variant="danger" className="bg-rose-500/15 text-rose-400 border-rose-500/30">
                          Rejected
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Coin Usage & Deduction Transactions */}
        <Card className="border-border/70 bg-surface">
          <CardHeader className="pb-3 border-b border-border/40">
            <CardTitle className="text-sm font-semibold flex items-center gap-2 text-foreground">
              <PhoneCall className="h-4 w-4 text-amber-400" />
              <span>Call Usage Deductions Ledger</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Exact seconds deducted from connected calls (1 coin = 1 second).
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            {transactions.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                No call usage recorded yet. Make a call to see coin deductions.
              </p>
            ) : (
              <div className="space-y-3">
                {transactions.slice(0, 10).map((tx) => (
                  <div
                    key={tx.id}
                    className="flex items-center justify-between rounded-xl border border-border/60 bg-surface-raised/40 p-3 text-xs"
                  >
                    <div className="space-y-1">
                      <p className="font-medium text-foreground">{tx.description}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {new Date(tx.created_at).toLocaleString("en-IN", {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </p>
                    </div>
                    <div className="text-right">
                      <span
                        className={`font-bold font-mono text-sm ${
                          tx.amount_coins >= 0 ? "text-emerald-400" : "text-amber-400"
                        }`}
                      >
                        {tx.amount_coins >= 0 ? `+${tx.amount_coins}` : tx.amount_coins}
                      </span>
                      <p className="text-[10px] text-muted-foreground">Bal: {tx.balance_after}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Image Zoom Modal */}
      {previewModalUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setPreviewModalUrl(null)}
        >
          <div className="relative max-h-[85vh] max-w-[85vw] overflow-hidden rounded-xl bg-card p-2 border border-border">
            <img
              src={previewModalUrl}
              alt="Screenshot Preview"
              className="max-h-[80vh] w-auto object-contain rounded"
            />
            <Button
              variant="outline"
              size="sm"
              className="mt-2 w-full text-xs"
              onClick={() => setPreviewModalUrl(null)}
            >
              Close
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
