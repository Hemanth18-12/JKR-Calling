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
  CheckCircle2,
  Clock,
  Coins,
  CreditCard,
  ExternalLink,
  History,
  PhoneCall,
  QrCode,
  ShieldAlert,
  Sparkles,
  Upload,
  XCircle,
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
      // ignore in background
    }
  };

  const pendingRequests = requests.filter((r) => r.status === "pending");

  return (
    <div className="space-y-8">
      {/* Overview Cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Main Coin Balance Card */}
        <Card className="relative overflow-hidden border-primary/40 bg-gradient-to-br from-primary/10 via-surface to-surface shadow-md">
          <div className="absolute right-3 top-3 opacity-15">
            <Coins className="h-20 w-20 text-primary" />
          </div>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
              Active Coin Wallet
            </CardDescription>
            <CardTitle className="text-3xl font-extrabold flex items-center gap-2 text-foreground">
              <span>🪙</span>
              <span>{wallet.balance_coins.toLocaleString()}</span>
              <span className="text-xs font-normal text-muted-foreground self-end pb-1">coins</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-1">
            <p>
              ⚡ <strong>1 coin = 1 second</strong> of AI voice calling.
            </p>
            <p>
              Available talk time:{" "}
              <strong className="text-foreground">
                {Math.floor(wallet.balance_coins / 60)}m {wallet.balance_coins % 60}s
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
            Lifetime approved top-up credits.
          </CardContent>
        </Card>

        {/* Total Spent */}
        <Card className="border-border/70 bg-surface">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <ArrowUpRight className="h-3.5 w-3.5 text-amber-400" />
              Total Call Usage Spent
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-foreground">
              -{wallet.total_spent_coins.toLocaleString()}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Deducted for actual connected call duration.
          </CardContent>
        </Card>
      </div>

      {/* Pending Approval Notice if any */}
      {pendingRequests.length > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-xs space-y-1.5">
          <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm">
            <Clock className="h-4 w-4 animate-spin" />
            <span>You have {pendingRequests.length} top-up payment(s) under review</span>
          </div>
          <p className="text-muted-foreground leading-relaxed">
            Your payment proof for{" "}
            <strong>
              {pendingRequests.map((r) => `₹${r.price_inr} (${r.total_coins} coins)`).join(", ")}
            </strong>{" "}
            was received and is currently being verified by the platform admin. Once approved, coins will be instantly credited to your wallet balance.
          </p>
        </div>
      )}

      {/* Add Coins Section — Redirects to Dedicated Payment Page */}
      <Card className="border-border/80 shadow-lg bg-surface">
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-lg font-bold flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                Add Coins — Top-up Tiers
              </CardTitle>
              <CardDescription>
                Select your preferred top-up package to proceed to our secure UPI QR payment checkout. 1 coin = 1 second of AI call time.
              </CardDescription>
            </div>
            <Badge variant="outline" className="self-start sm:self-auto border-primary/30 text-primary">
              1 Coin = 1 Second
            </Badge>
          </div>
        </CardHeader>

        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            {COIN_TIERS.map((tier) => (
              <div
                key={tier.id}
                onClick={() => router.push(`/app/billing/pay?tier=${tier.id}`)}
                className="group relative cursor-pointer rounded-xl border border-border/70 bg-surface-raised p-5 transition-all duration-200 hover:border-primary hover:bg-surface-raised/90 hover:shadow-lg flex flex-col justify-between"
              >
                {tier.tag && (
                  <span className="absolute -top-2.5 right-4 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 px-2.5 py-0.5 text-[10px] font-bold text-white shadow-sm">
                    {tier.tag}
                  </span>
                )}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      {tier.label ?? "Standard"}
                    </span>
                    <span className="text-lg font-extrabold text-foreground">
                      ₹{tier.price_inr}
                    </span>
                  </div>

                  <div className="space-y-1.5 mb-4">
                    <div className="text-3xl font-black text-foreground flex items-center gap-2">
                      <Coins className="h-6 w-6 text-primary" />
                      {tier.total_coins}
                      <span className="text-xs font-normal text-muted-foreground">coins</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {tier.bonus_coins > 0 ? (
                        <>
                          {tier.base_coins} base +{" "}
                          <strong className="text-emerald-400">+{tier.bonus_coins} bonus</strong>
                        </>
                      ) : (
                        `${Math.floor(tier.total_coins / 60)} minutes talk time`
                      )}
                    </p>
                  </div>
                </div>

                <Button
                  variant="gradient"
                  size="sm"
                  className="w-full font-bold mt-2 group-hover:scale-[1.02] transition-transform"
                  onClick={(e) => {
                    e.stopPropagation();
                    router.push(`/app/billing/pay?tier=${tier.id}`);
                  }}
                >
                  Select &amp; Pay ₹{tier.price_inr} →
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Part 4: History Sections (Top-up Requests & Call Deductions) */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Top-up Requests History */}
        <Card className="border-border/70 bg-surface">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <History className="h-4 w-4 text-muted-foreground" />
              Top-up Requests
            </CardTitle>
            <CardDescription className="text-xs">
              History of your manual UPI payment submissions.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {requests.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                No top-up requests yet. Select a tier above to recharge.
              </p>
            ) : (
              <div className="space-y-3">
                {requests.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center justify-between rounded-lg border border-border/60 bg-surface-raised/40 p-3 text-xs"
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
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <PhoneCall className="h-4 w-4 text-muted-foreground" />
              Call Usage Deductions
            </CardTitle>
            <CardDescription className="text-xs">
              Live deductions recorded per call (1 coin = 1 second).
            </CardDescription>
          </CardHeader>
          <CardContent>
            {transactions.length === 0 ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                No call usage recorded yet. Make a call to see coin deductions.
              </p>
            ) : (
              <div className="space-y-3">
                {transactions.slice(0, 10).map((tx) => (
                  <div
                    key={tx.id}
                    className="flex items-center justify-between rounded-lg border border-border/60 bg-surface-raised/40 p-3 text-xs"
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
