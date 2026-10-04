"use client";

import { COIN_TIERS, type CoinTier, type CoinTopupRequestOut } from "@jkr/contracts";
import { coinsApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Label,
  useToast,
} from "@jkr/ui";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Coins,
  CreditCard,
  ExternalLink,
  Eye,
  Info,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

interface CoinPaymentClientProps {
  workspaceId: string;
  initialTierId: string;
}

export function CoinPaymentClient({
  workspaceId,
  initialTierId,
}: CoinPaymentClientProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [selectedTierId, setSelectedTierId] = React.useState<string>(initialTierId);
  const selectedTier =
    COIN_TIERS.find((t) => t.id === selectedTierId) || COIN_TIERS[1] || COIN_TIERS[0]!;

  const [screenshotBase64, setScreenshotBase64] = React.useState<string | null>(null);
  const [screenshotPreview, setScreenshotPreview] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [submittedRequest, setSubmittedRequest] = React.useState<CoinTopupRequestOut | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = React.useState(false);

  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  // Duplicate submission guard ref: guarantees immediate synchronous locking
  const isSubmittingRef = React.useRef(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast({
        title: "Invalid file format",
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

  const handleSubmitProof = async (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    // Synchronous double-submission lock: block if already in flight
    if (isSubmittingRef.current || uploading) {
      return;
    }

    if (!screenshotBase64) {
      toast({
        title: "Screenshot Required",
        description: "Please upload a screenshot of your completed UPI payment.",
        variant: "danger",
      });
      return;
    }

    isSubmittingRef.current = true;
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
        description: "Your top-up request is under review. Coins will be credited upon approval.",
        variant: "success",
      });
    } catch (err: any) {
      toast({
        title: "Submission Error",
        description: err?.message || "Could not submit payment proof. Please try again.",
        variant: "danger",
      });
    } finally {
      setUploading(false);
      isSubmittingRef.current = false;
    }
  };

  if (submittedRequest) {
    return (
      <div className="space-y-6 animate-in fade-in duration-300">
        <Link
          href="/app/billing"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Billing &amp; Wallet
        </Link>

        <Card className="border-emerald-500/40 bg-gradient-to-br from-emerald-500/10 via-surface to-surface shadow-xl p-6 sm:p-8 text-center space-y-5">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
            <CheckCircle2 className="h-8 w-8" />
          </div>

          <div className="space-y-2 max-w-lg mx-auto">
            <h2 className="text-2xl font-bold text-foreground">
              Payment Proof Submitted Successfully!
            </h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              We have received your payment proof for{" "}
              <strong className="text-foreground">₹{submittedRequest.price_inr}</strong> (
              <strong className="text-primary">{submittedRequest.total_coins} coins</strong>).
              Your request is currently pending manual admin verification.
            </p>
          </div>

          <div className="mx-auto max-w-md rounded-xl border border-border/80 bg-surface-raised p-4 text-xs space-y-2 text-left">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Request ID:</span>
              <span className="font-mono text-foreground font-semibold">
                {submittedRequest.id.slice(0, 13)}...
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Plan:</span>
              <span className="text-foreground font-medium">
                {submittedRequest.tier_id === "tier_100"
                  ? "Starter"
                  : submittedRequest.tier_id === "tier_250"
                  ? "Most Popular"
                  : "Pro Value"}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Amount Paid:</span>
              <span className="text-emerald-400 font-bold">₹{submittedRequest.price_inr}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Coins Credited on Approval:</span>
              <span className="text-primary font-bold">{submittedRequest.total_coins} coins</span>
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-border/60">
              <span className="text-muted-foreground">Status:</span>
              <Badge variant="outline" className="text-amber-400 border-amber-500/40 bg-amber-500/10">
                <Clock className="h-3 w-3 mr-1 animate-spin" />
                Pending Admin Review
              </Badge>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <Button
              variant="gradient"
              onClick={() => router.push("/app/billing")}
              className="w-full sm:w-auto font-bold"
            >
              Go to Wallet &amp; Billing History
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setSubmittedRequest(null);
                setScreenshotBase64(null);
                setScreenshotPreview(null);
              }}
              className="w-full sm:w-auto text-xs"
            >
              Submit Another Top-up
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Navigation & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Link
          href="/app/billing"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Billing
        </Link>
        <Badge variant="outline" className="self-start sm:self-auto border-primary/40 text-primary">
          1 Coin = 1 Second of AI Voice Calling
        </Badge>
      </div>

      {/* Main Top Banner: Selected Amount & Coins */}
      <Card className="border-primary/50 bg-gradient-to-r from-primary/15 via-surface to-surface shadow-md">
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge variant="default" className="bg-primary text-black font-bold">
                  {selectedTier.label || "Selected Tier"}
                </Badge>
                {selectedTier.tag && (
                  <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 font-semibold bg-emerald-500/10">
                    {selectedTier.tag}
                  </Badge>
                )}
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Pay ₹{selectedTier.price_inr} for {selectedTier.total_coins} coins
              </h1>
              <p className="text-xs text-muted-foreground">
                {selectedTier.bonus_coins > 0 ? (
                  <>
                    Includes {selectedTier.base_coins} base coins +{" "}
                    <strong className="text-emerald-400">+{selectedTier.bonus_coins} bonus coins</strong>!
                    (Equivalent to {Math.floor(selectedTier.total_coins / 60)} minutes talk time)
                  </>
                ) : (
                  `Equivalent to ${Math.floor(selectedTier.total_coins / 60)} minutes connected AI conversation`
                )}
              </p>
            </div>

            {/* Quick Switch Tier Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground mr-1">Switch Tier:</span>
              {COIN_TIERS.map((t) => {
                const isCurrent = t.id === selectedTier.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSelectedTierId(t.id)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all border ${
                      isCurrent
                        ? "bg-primary text-black border-primary shadow-sm"
                        : "bg-surface-raised border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"
                    }`}
                  >
                    ₹{t.price_inr} ({t.total_coins}c)
                  </button>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Payment Section: Clean Focused Vertical Flow */}
      <div className="max-w-2xl mx-auto space-y-6">
        <Card className="border-border/80 bg-surface shadow-xl overflow-hidden">
          {/* Card Header: Merchant Info & Verified Badge */}
          <CardHeader className="text-center pb-4 border-b border-border/60 bg-surface-raised/40">
            <div className="flex flex-col items-center gap-1.5">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold">
                <ShieldCheck className="h-3.5 w-3.5" />
                Verified PhonePe Merchant
              </div>
              <CardTitle className="text-lg font-bold text-foreground">
                tejavath Hemanth
              </CardTitle>
              <CardDescription className="text-xs font-mono text-muted-foreground">
                +91 8019101606 • UPI ID: 8019101606@ybl
              </CardDescription>
            </div>
          </CardHeader>

          <CardContent className="p-6 sm:p-8 space-y-6">
            {/* Clean Cropped QR Display */}
            <div className="flex flex-col items-center justify-center">
              <div className="relative w-64 h-64 sm:w-72 sm:h-72 overflow-hidden rounded-2xl border-2 border-primary/30 shadow-2xl bg-black p-2 hover:border-primary/60 transition-colors">
                <Image
                  src="/payment_qr.png"
                  alt="PhonePe UPI Payment QR Code"
                  fill
                  className="object-contain p-1"
                  priority
                />
              </div>

              <div className="mt-3 text-center space-y-1">
                <p className="text-xs font-semibold text-foreground">
                  Scan QR with PhonePe, Google Pay, Paytm, or BHIM
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Exact amount to pay: <strong className="text-emerald-400 font-bold">₹{selectedTier.price_inr}</strong>
                </p>
              </div>
            </div>

            {/* Separator */}
            <div className="relative flex items-center justify-center">
              <div className="border-t border-border/80 w-full" />
              <span className="bg-surface px-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider shrink-0">
                Step 2: Upload Proof Below
              </span>
            </div>

            {/* Upload Payment Screenshot Field Directly Below the QR */}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pay-screenshot-input" className="text-xs font-semibold text-foreground flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Upload className="h-4 w-4 text-primary" />
                    Upload Payment Screenshot
                  </span>
                  <span className="text-[11px] text-muted-foreground font-normal">
                    JPG, PNG or Screenshot
                  </span>
                </Label>
                <input
                  ref={fileInputRef}
                  id="pay-screenshot-input"
                  type="file"
                  accept="image/*"
                  onChange={handleFileChange}
                  disabled={uploading}
                  className="block w-full text-xs text-muted-foreground file:mr-3 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-primary file:text-black hover:file:bg-primary/90 cursor-pointer disabled:opacity-50 border border-border rounded-xl p-1 bg-surface-raised/50"
                />
              </div>

              {screenshotPreview && (
                <div className="rounded-xl border border-border bg-surface-raised p-3 flex items-center justify-between animate-in fade-in">
                  <div className="flex items-center gap-3">
                    <div
                      className="relative h-14 w-14 rounded-lg overflow-hidden border border-border cursor-pointer hover:opacity-90"
                      onClick={() => setPreviewModalOpen(true)}
                    >
                      <img
                        src={screenshotPreview}
                        alt="Screenshot preview"
                        className="h-full w-full object-cover"
                      />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground">Screenshot attached</p>
                      <p className="text-[11px] text-muted-foreground">Click thumbnail to inspect</p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={uploading}
                    onClick={() => {
                      setScreenshotBase64(null);
                      setScreenshotPreview(null);
                      if (fileInputRef.current) fileInputRef.current.value = "";
                    }}
                    className="text-xs text-rose-400 hover:text-rose-300"
                  >
                    Remove
                  </Button>
                </div>
              )}

              {/* Submit button with double-submission protection */}
              <Button
                type="button"
                variant="gradient"
                className="w-full h-11 font-bold text-sm shadow-md"
                disabled={!screenshotBase64 || uploading}
                loading={uploading}
                onClick={handleSubmitProof}
              >
                <Upload className="h-4 w-4 mr-2" />
                {uploading
                  ? "Submitting Payment Proof..."
                  : `I've Paid ₹${selectedTier.price_inr} — Submit for Review`}
              </Button>

              <div className="rounded-xl border border-border/60 bg-surface-raised/40 p-3.5 text-xs text-muted-foreground space-y-1">
                <p className="text-[11px] leading-relaxed flex items-center gap-1.5 text-foreground font-medium">
                  <Info className="h-3.5 w-3.5 text-primary shrink-0" />
                  Fast Approval Process
                </p>
                <p className="text-[11px] leading-relaxed">
                  Your screenshot is verified manually by our admin team. Once confirmed, <strong className="text-primary font-semibold">{selectedTier.total_coins} coins</strong> will be immediately credited to your wallet.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Screenshot Zoom Modal */}
      {previewModalOpen && screenshotPreview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
          onClick={() => setPreviewModalOpen(false)}
        >
          <div
            className="relative max-h-[90vh] max-w-[90vw] overflow-hidden rounded-2xl bg-card p-4 border border-border shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-border mb-3">
              <h3 className="text-sm font-bold text-foreground">Attached Screenshot Preview</h3>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => setPreviewModalOpen(false)}
              >
                ✕
              </Button>
            </div>
            <div className="relative max-h-[75vh] overflow-auto flex items-center justify-center">
              <img
                src={screenshotPreview}
                alt="Payment Proof Zoom"
                className="max-h-[70vh] w-auto rounded-lg object-contain shadow-md"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
