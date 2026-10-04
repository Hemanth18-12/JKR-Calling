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
  const { toast } = useToast();
  const [wallet, setWallet] = React.useState<CoinWalletOut>(initialWallet);
  const [requests, setRequests] = React.useState<CoinTopupRequestOut[]>(initialRequests);
  const [transactions, setTransactions] = React.useState<CoinTransactionOut[]>(initialTransactions);

  const [selectedTier, setSelectedTier] = React.useState<CoinTier>(COIN_TIERS[1] ?? COIN_TIERS[0]!);
  const [screenshotBase64, setScreenshotBase64] = React.useState<string | null>(null);
  const [screenshotPreview, setScreenshotPreview] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [submittedRequest, setSubmittedRequest] = React.useState<CoinTopupRequestOut | null>(null);
  const [previewModalUrl, setPreviewModalUrl] = React.useState<string | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast({
        title: "Invalid file",
        description: "Please upload an image file (PNG, JPG, or screenshot).",
        variant: "danger",
      });
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      setScreenshotBase64(result);
      setScreenshotPreview(result);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmitProof = async () => {
    if (!screenshotBase64) {
      toast({
        title: "Proof Required",
        description: "Please select or take a screenshot of your successful UPI payment.",
        variant: "danger",
      });
      return;
    }

    setUploading(true);
    try {
      const req = await coinsApi.createTopupRequest(workspaceId, {
        tier_id: selectedTier.id,
        screenshot_base64: screenshotBase64,
      });

      setSubmittedRequest(req);
      setScreenshotBase64(null);
      setScreenshotPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = "";

      toast({
        title: "Payment Proof Submitted! 🎉",
        description: "Your top-up request is under review. Coins will be added once confirmed.",
        variant: "success",
      });
      await refreshData();
    } catch (err: any) {
      toast({
        title: "Submission Failed",
        description: err?.message || "Could not submit payment proof. Please try again.",
        variant: "danger",
      });
    } finally {
      setUploading(false);
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

      {/* Part 1 & Part 2: Add Coins / Top Up Section */}
      <Card className="border-border/80 shadow-lg bg-surface">
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-lg font-bold flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" />
                Add Coins — Instant UPI QR Payment
              </CardTitle>
              <CardDescription>
                Select your top-up tier, scan the QR code using any UPI app (PhonePe / GPay / Paytm), and upload your payment screenshot.
              </CardDescription>
            </div>
            <Badge variant="outline" className="self-start sm:self-auto border-primary/30 text-primary">
              1 Coin = 1 Second
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Tier Selection Cards */}
          <div>
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 block">
              1. Choose Top-up Tier
            </Label>
            <div className="grid gap-3 sm:grid-cols-3">
              {COIN_TIERS.map((tier) => {
                const isSelected = selectedTier.id === tier.id;
                return (
                  <div
                    key={tier.id}
                    onClick={() => setSelectedTier(tier)}
                    className={`relative cursor-pointer rounded-xl border p-4 transition-all duration-200 ${
                      isSelected
                        ? "border-primary bg-primary/10 shadow-md ring-1 ring-primary"
                        : "border-border/70 bg-surface-raised hover:border-border hover:bg-surface-raised/80"
                    }`}
                  >
                    {tier.tag && (
                      <span className="absolute -top-2.5 right-3 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 px-2 py-0.5 text-[10px] font-bold text-white shadow-sm">
                        {tier.tag}
                      </span>
                    )}
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-muted-foreground">
                        {tier.label ?? "Standard"}
                      </span>
                      <span className="text-base font-extrabold text-foreground">
                        ₹{tier.price_inr}
                      </span>
                    </div>

                    <div className="space-y-1">
                      <div className="text-2xl font-black text-foreground flex items-center gap-1.5">
                        <Coins className="h-5 w-5 text-primary" />
                        {tier.total_coins}
                        <span className="text-xs font-normal text-muted-foreground">coins</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
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
                );
              })}
            </div>
          </div>

          {/* QR Payment Box & File Upload */}
          <div className="rounded-2xl border border-border/80 bg-surface-raised/50 p-5 space-y-6">
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block">
              2. Scan &amp; Pay via UPI
            </Label>

            <div className="grid gap-6 md:grid-cols-12 items-center">
              {/* QR Code Container */}
              <div className="md:col-span-5 flex flex-col items-center justify-center p-4 bg-black/40 rounded-xl border border-border/60">
                <div className="relative w-56 h-72 sm:w-60 sm:h-80 overflow-hidden rounded-lg shadow-xl border border-border/50">
                  <Image
                    src="/payment_qr.png"
                    alt="PhonePe UPI Payment QR"
                    fill
                    className="object-contain"
                    priority
                  />
                </div>
                <div className="mt-3 text-center space-y-0.5">
                  <p className="text-xs font-semibold text-foreground">tejavath Hemanth</p>
                  <p className="text-[11px] text-muted-foreground font-mono">+91 8019101606</p>
                  <span className="inline-block mt-1 text-[10px] text-emerald-400 font-medium bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    ✓ Verified PhonePe Merchant
                  </span>
                </div>
              </div>

              {/* Instructions and Upload */}
              <div className="md:col-span-7 space-y-5">
                <div className="rounded-xl bg-surface border border-border/70 p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Selected Plan:</span>
                    <strong className="text-foreground">{selectedTier.label}</strong>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Coins Credited:</span>
                    <strong className="text-primary font-bold">{selectedTier.total_coins} Coins</strong>
                  </div>
                  <div className="border-t border-border/60 pt-2 flex items-center justify-between">
                    <span className="text-sm font-semibold text-foreground">Exact Amount to Pay:</span>
                    <span className="text-2xl font-black text-emerald-400">₹{selectedTier.price_inr}</span>
                  </div>
                </div>

                <div className="space-y-3">
                  <Label htmlFor="payment-screenshot" className="text-xs font-medium text-foreground block">
                    3. Upload Payment Screenshot (Proof)
                  </Label>

                  <div className="flex flex-col gap-3">
                    <input
                      ref={fileInputRef}
                      id="payment-screenshot"
                      type="file"
                      accept="image/*"
                      onChange={handleFileChange}
                      className="block w-full text-xs text-muted-foreground file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-primary file:text-black hover:file:bg-primary/90 cursor-pointer"
                    />

                    {screenshotPreview && (
                      <div className="relative inline-block mt-2">
                        <p className="text-[11px] text-muted-foreground mb-1">Selected screenshot preview:</p>
                        <div
                          className="relative h-32 w-32 rounded-lg border border-border overflow-hidden cursor-pointer hover:opacity-90 transition-opacity"
                          onClick={() => setPreviewModalUrl(screenshotPreview)}
                        >
                          <img
                            src={screenshotPreview}
                            alt="Screenshot preview"
                            className="h-full w-full object-cover"
                          />
                        </div>
                      </div>
                    )}

                    <Button
                      variant="gradient"
                      className="w-full mt-2 font-bold"
                      onClick={handleSubmitProof}
                      disabled={!screenshotBase64 || uploading}
                      loading={uploading}
                    >
                      <Upload className="h-4 w-4 mr-2" />
                      {uploading
                        ? "Uploading Proof..."
                        : `I've Paid ₹${selectedTier.price_inr} — Submit for Review`}
                    </Button>
                  </div>

                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    💡 After transfer, upload your payment receipt or success screen. Our admin reviews incoming payments promptly and credits the coins directly to your wallet.
                  </p>
                </div>
              </div>
            </div>
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
