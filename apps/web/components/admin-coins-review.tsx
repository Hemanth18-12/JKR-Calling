"use client";

import { type CoinTopupRequestOut } from "@jkr/contracts";
import { adminCoinsApi } from "@jkr/sdk";
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
  AlertCircle,
  CheckCircle2,
  Clock,
  Coins,
  ExternalLink,
  Eye,
  Filter,
  RefreshCw,
  Search,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import * as React from "react";

interface AdminCoinsReviewProps {
  initialRequests: CoinTopupRequestOut[];
}

export function AdminCoinsReview({ initialRequests }: AdminCoinsReviewProps) {
  const { toast } = useToast();
  const [requests, setRequests] = React.useState<CoinTopupRequestOut[]>(initialRequests);
  const [filter, setFilter] = React.useState<"all" | "pending" | "approved" | "rejected">("pending");
  const [loading, setLoading] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");

  const [activeScreenshotUrl, setActiveScreenshotUrl] = React.useState<string | null>(null);
  const [activeScreenshotReq, setActiveScreenshotReq] = React.useState<CoinTopupRequestOut | null>(null);

  // Approve dialog state
  const [approvingId, setApprovingId] = React.useState<string | null>(null);
  const [approveNotes, setApproveNotes] = React.useState("");
  const [actionBusy, setActionBusy] = React.useState(false);

  // Reject dialog state
  const [rejectingId, setRejectingId] = React.useState<string | null>(null);
  const [rejectReason, setRejectReason] = React.useState("");

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const data = await adminCoinsApi.listTopupRequests();
      setRequests(data);
    } catch (err: any) {
      toast({
        title: "Could not load requests",
        description: err?.message || "Please refresh",
        variant: "danger",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!approvingId) return;
    setActionBusy(true);
    try {
      await adminCoinsApi.approveTopup(approvingId, { notes: approveNotes.trim() || undefined });
      toast({
        title: "Top-up Approved! 🪙",
        description: "Coins credited to user's wallet immediately.",
        variant: "success",
      });
      setApprovingId(null);
      setApproveNotes("");
      await fetchRequests();
    } catch (err: any) {
      toast({
        title: "Approval Failed",
        description: err?.message || "Error approving request",
        variant: "danger",
      });
    } finally {
      setActionBusy(false);
    }
  };

  const handleReject = async () => {
    if (!rejectingId) return;
    setActionBusy(true);
    try {
      await adminCoinsApi.rejectTopup(rejectingId, { notes: rejectReason.trim() || "Payment verification failed" });
      toast({
        title: "Top-up Rejected",
        description: "Request marked as rejected. No coins credited.",
        variant: "default",
      });
      setRejectingId(null);
      setRejectReason("");
      await fetchRequests();
    } catch (err: any) {
      toast({
        title: "Rejection Failed",
        description: err?.message || "Error rejecting request",
        variant: "danger",
      });
    } finally {
      setActionBusy(false);
    }
  };

  const filteredRequests = requests.filter((r) => {
    if (filter !== "all" && r.status !== filter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchEmail = r.user_email?.toLowerCase().includes(q);
      const matchWs = r.workspace_name?.toLowerCase().includes(q);
      const matchId = r.id.toLowerCase().includes(q);
      return matchEmail || matchWs || matchId;
    }
    return true;
  });

  const pendingCount = requests.filter((r) => r.status === "pending").length;
  const approvedCount = requests.filter((r) => r.status === "approved").length;
  const rejectedCount = requests.filter((r) => r.status === "rejected").length;

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <ShieldCheck className="h-6 w-6 text-emerald-400" />
            Admin Top-up Verification
          </h1>
          <p className="text-sm text-muted-foreground">
            Review incoming manual UPI payments, inspect proof screenshots, and approve coin allocations.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchRequests} loading={loading}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Stats and Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="flex items-center gap-1.5 overflow-x-auto p-1 bg-surface-raised rounded-xl border border-border">
          <Button
            size="sm"
            variant={filter === "pending" ? "gradient" : "ghost"}
            className="text-xs h-8"
            onClick={() => setFilter("pending")}
          >
            Pending
            <span className="ml-1.5 rounded-full bg-amber-500/20 text-amber-300 px-1.5 py-0.2 text-[10px] font-bold">
              {pendingCount}
            </span>
          </Button>

          <Button
            size="sm"
            variant={filter === "approved" ? "gradient" : "ghost"}
            className="text-xs h-8"
            onClick={() => setFilter("approved")}
          >
            Approved
            <span className="ml-1.5 rounded-full bg-emerald-500/20 text-emerald-300 px-1.5 py-0.2 text-[10px] font-bold">
              {approvedCount}
            </span>
          </Button>

          <Button
            size="sm"
            variant={filter === "rejected" ? "gradient" : "ghost"}
            className="text-xs h-8"
            onClick={() => setFilter("rejected")}
          >
            Rejected
            <span className="ml-1.5 rounded-full bg-rose-500/20 text-rose-300 px-1.5 py-0.2 text-[10px] font-bold">
              {rejectedCount}
            </span>
          </Button>

          <Button
            size="sm"
            variant={filter === "all" ? "gradient" : "ghost"}
            className="text-xs h-8"
            onClick={() => setFilter("all")}
          >
            All History ({requests.length})
          </Button>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search email, workspace..."
            className="pl-8 h-9 text-xs"
          />
        </div>
      </div>

      {/* Main Table Card */}
      <Card className="border-border/80 bg-surface shadow-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-raised border-b border-border text-muted-foreground font-semibold uppercase tracking-wider text-[10px]">
              <tr>
                <th className="py-3 px-4">User &amp; Workspace</th>
                <th className="py-3 px-4">Amount &amp; Coins</th>
                <th className="py-3 px-4">Payment Proof</th>
                <th className="py-3 px-4">Submitted At</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filteredRequests.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-muted-foreground">
                    No requests found matching current filter.
                  </td>
                </tr>
              ) : (
                filteredRequests.map((req) => (
                  <tr key={req.id} className="hover:bg-surface-raised/40 transition-colors">
                    {/* User / Workspace */}
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-foreground text-sm">
                        {req.user_email || "Unknown User"}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        Workspace: <span className="text-foreground">{req.workspace_name}</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground font-mono">
                        ID: {req.id.slice(0, 8)}...
                      </div>
                    </td>

                    {/* Amount & Coins */}
                    <td className="py-3.5 px-4">
                      <div className="text-sm font-extrabold text-emerald-400">
                        ₹{req.price_inr}
                      </div>
                      <div className="text-[11px] font-semibold text-foreground flex items-center gap-1">
                        <Coins className="h-3 w-3 text-primary" />
                        {req.total_coins} coins
                      </div>
                      {req.bonus_coins > 0 && (
                        <div className="text-[10px] text-emerald-400">
                          ({req.base_coins} base + {req.bonus_coins} bonus)
                        </div>
                      )}
                    </td>

                    {/* Payment Proof Screenshot */}
                    <td className="py-3.5 px-4">
                      <button
                        type="button"
                        onClick={() => {
                          setActiveScreenshotUrl(req.screenshot_url);
                          setActiveScreenshotReq(req);
                        }}
                        className="group flex items-center gap-2.5 rounded-xl border border-border/80 bg-surface-raised/90 p-1.5 hover:border-primary/60 hover:bg-surface-raised transition-all text-left shadow-sm"
                      >
                        <div className="h-11 w-11 rounded-lg overflow-hidden bg-black/60 relative flex items-center justify-center border border-border shrink-0 shadow-inner group-hover:ring-2 group-hover:ring-primary/40 transition-all">
                          <img
                            src={req.screenshot_url}
                            alt="Payment Proof"
                            className="h-full w-full object-cover transition-transform group-hover:scale-105"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = "none";
                            }}
                          />
                          <div className="absolute inset-0 bg-black/30 group-hover:bg-transparent transition-colors flex items-center justify-center pointer-events-none">
                            <Eye className="h-4 w-4 text-white drop-shadow opacity-75 group-hover:opacity-100 transition-opacity" />
                          </div>
                        </div>
                        <div className="text-[11px]">
                          <span className="font-bold text-foreground block group-hover:text-primary transition-colors flex items-center gap-1">
                            Inspect Proof
                            <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                          </span>
                          <span className="text-[10px] text-muted-foreground">Click to inspect</span>
                        </div>
                      </button>
                    </td>

                    {/* Submitted At */}
                    <td className="py-3.5 px-4 text-muted-foreground text-[11px]">
                      {new Date(req.created_at).toLocaleString("en-IN", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                      {req.reviewed_at && (
                        <div className="text-[10px] text-muted-foreground/80 mt-1">
                          Reviewed: {new Date(req.reviewed_at).toLocaleTimeString("en-IN", { timeStyle: "short" })}
                        </div>
                      )}
                    </td>

                    {/* Status Badge */}
                    <td className="py-3.5 px-4">
                      {req.status === "pending" && (
                        <Badge variant="outline" className="text-amber-400 border-amber-500/40 bg-amber-500/10">
                          Pending Review
                        </Badge>
                      )}
                      {req.status === "approved" && (
                        <div className="space-y-0.5">
                          <Badge variant="success" className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                            Approved
                          </Badge>
                          {req.admin_notes && (
                            <p className="text-[10px] text-muted-foreground italic truncate max-w-[120px]">
                              {req.admin_notes}
                            </p>
                          )}
                        </div>
                      )}
                      {req.status === "rejected" && (
                        <div className="space-y-0.5">
                          <Badge variant="danger" className="bg-rose-500/15 text-rose-400 border-rose-500/30">
                            Rejected
                          </Badge>
                          {req.admin_notes && (
                            <p className="text-[10px] text-rose-400/90 italic truncate max-w-[120px]">
                              {req.admin_notes}
                            </p>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right">
                      {req.status === "pending" ? (
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            size="sm"
                            variant="gradient"
                            className="text-xs h-7 px-2.5 font-bold"
                            onClick={() => {
                              setApprovingId(req.id);
                              setApproveNotes("");
                            }}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs h-7 px-2.5 text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
                            onClick={() => {
                              setRejectingId(req.id);
                              setRejectReason("");
                            }}
                          >
                            Reject
                          </Button>
                        </div>
                      ) : (
                        <span className="text-[11px] text-muted-foreground/60 italic">Resolved</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Screenshot Zoom Modal */}
      {activeScreenshotUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-md"
          onClick={() => {
            setActiveScreenshotUrl(null);
            setActiveScreenshotReq(null);
          }}
        >
          <div
            className="relative max-h-[92vh] max-w-2xl w-full overflow-hidden rounded-2xl bg-card border border-border shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-border bg-surface-raised shrink-0">
              <div>
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <Eye className="h-4 w-4 text-primary" />
                  Payment Proof Inspection
                </h3>
                {activeScreenshotReq && (
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {activeScreenshotReq.user_email} • ₹{activeScreenshotReq.price_inr} • {activeScreenshotReq.total_coins} coins
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={activeScreenshotUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline flex items-center gap-1 font-semibold px-2.5 py-1 rounded bg-primary/10 border border-primary/20"
                >
                  Open in New Tab <ExternalLink className="h-3 w-3" />
                </a>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                  onClick={() => {
                    setActiveScreenshotUrl(null);
                    setActiveScreenshotReq(null);
                  }}
                >
                  ✕
                </Button>
              </div>
            </div>

            <div className="relative flex-1 overflow-auto bg-black/95 p-4 flex items-center justify-center min-h-[350px]">
              <img
                src={activeScreenshotUrl}
                alt="Payment Proof"
                className="max-h-[65vh] w-auto max-w-full rounded-lg object-contain shadow-2xl border border-white/10"
              />
            </div>

            <div className="p-3 border-t border-border bg-surface-raised flex items-center justify-between shrink-0">
              <span className="text-[11px] text-muted-foreground font-medium">
                {activeScreenshotReq ? `Status: ${activeScreenshotReq.status.toUpperCase()}` : ""}
              </span>
              <div className="flex items-center gap-2">
                {activeScreenshotReq && activeScreenshotReq.status === "pending" && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setRejectingId(activeScreenshotReq.id);
                        setActiveScreenshotUrl(null);
                        setActiveScreenshotReq(null);
                      }}
                      className="text-xs text-rose-400 border-rose-500/40 hover:bg-rose-500/10"
                    >
                      <XCircle className="h-3.5 w-3.5 mr-1" />
                      Reject
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      onClick={() => {
                        setApprovingId(activeScreenshotReq.id);
                        setActiveScreenshotUrl(null);
                        setActiveScreenshotReq(null);
                      }}
                      className="text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                      Approve Payment
                    </Button>
                  </>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setActiveScreenshotUrl(null);
                    setActiveScreenshotReq(null);
                  }}
                  className="text-xs"
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Approve Confirmation Modal with Embedded Screenshot */}
      {approvingId && (() => {
        const reqToApprove = requests.find((r) => r.id === approvingId);
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm">
            <Card className="w-full max-w-lg border-emerald-500/40 bg-card shadow-2xl overflow-hidden">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-base font-bold text-foreground flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                  Approve Payment &amp; Credit Coins
                </CardTitle>
                <CardDescription className="text-xs">
                  Verify the customer&apos;s UPI screenshot proof below before crediting coins.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 pt-4">
                {reqToApprove && (
                  <div className="rounded-xl border border-border bg-surface-raised p-3 space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <div>
                        <span className="text-muted-foreground">User: </span>
                        <span className="font-bold text-foreground">{reqToApprove.user_email}</span>
                        <div className="text-[10px] text-muted-foreground">
                          Workspace: {reqToApprove.workspace_name}
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="font-extrabold text-emerald-400 text-sm">
                          ₹{reqToApprove.price_inr}
                        </span>
                        <div className="text-[11px] font-semibold text-primary">
                          +{reqToApprove.total_coins} coins
                        </div>
                      </div>
                    </div>

                    {/* Screenshot Proof Preview */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground">
                        <span>Customer Payment Screenshot:</span>
                        <a
                          href={reqToApprove.screenshot_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline flex items-center gap-1 text-[11px]"
                        >
                          Open Original <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                      <div
                        className="relative max-h-56 w-full overflow-hidden rounded-lg border border-border bg-black/70 flex items-center justify-center cursor-pointer group"
                        onClick={() => {
                          setActiveScreenshotUrl(reqToApprove.screenshot_url);
                          setActiveScreenshotReq(reqToApprove);
                        }}
                      >
                        <img
                          src={reqToApprove.screenshot_url}
                          alt="Payment Proof"
                          className="max-h-56 w-auto object-contain transition-transform group-hover:scale-102"
                        />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-semibold gap-1.5">
                          <Eye className="h-4 w-4" /> Click to enlarge
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div>
                  <Label htmlFor="approve-notes" className="text-xs font-medium">
                    Admin Verification Note (optional)
                  </Label>
                  <Input
                    id="approve-notes"
                    placeholder="e.g. Verified transaction reference in bank statement"
                    value={approveNotes}
                    onChange={(e) => setApproveNotes(e.target.value)}
                    className="mt-1 text-xs"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setApprovingId(null)}
                    disabled={actionBusy}
                    className="text-xs"
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={handleApprove}
                    loading={actionBusy}
                    className="text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white"
                  >
                    Confirm &amp; Credit Coins
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        );
      })()}

      {/* Reject Confirmation Modal with Embedded Screenshot */}
      {rejectingId && (() => {
        const reqToReject = requests.find((r) => r.id === rejectingId);
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm">
            <Card className="w-full max-w-md border-rose-500/40 bg-card shadow-2xl overflow-hidden">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-base font-bold text-foreground flex items-center gap-2">
                  <XCircle className="h-5 w-5 text-rose-400" />
                  Reject Top-up Request
                </CardTitle>
                <CardDescription className="text-xs">
                  The payment could not be verified. No coins will be credited.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 pt-4">
                {reqToReject && (
                  <div className="rounded-xl border border-border bg-surface-raised p-3 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-foreground">{reqToReject.user_email}</span>
                      <span className="font-bold text-rose-400">₹{reqToReject.price_inr}</span>
                    </div>
                    <div
                      className="relative max-h-36 w-full overflow-hidden rounded-lg border border-border bg-black/70 flex items-center justify-center cursor-pointer"
                      onClick={() => {
                        setActiveScreenshotUrl(reqToReject.screenshot_url);
                        setActiveScreenshotReq(reqToReject);
                      }}
                    >
                      <img
                        src={reqToReject.screenshot_url}
                        alt="Payment Proof"
                        className="max-h-36 w-auto object-contain"
                      />
                    </div>
                  </div>
                )}

                <div>
                  <Label htmlFor="reject-reason" className="text-xs font-medium">
                    Rejection Reason (will be shown to user)
                  </Label>
                  <Input
                    id="reject-reason"
                    placeholder="e.g. Transaction reference not found in bank statement"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    className="mt-1 text-xs"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRejectingId(null)}
                    disabled={actionBusy}
                    className="text-xs"
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleReject}
                    loading={actionBusy}
                    className="text-xs font-bold"
                  >
                    Reject Request
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        );
      })()}
    </div>
  );
}
