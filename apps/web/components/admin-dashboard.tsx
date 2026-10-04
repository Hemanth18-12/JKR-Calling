"use client";

import type {
  AdminDashboardOverview,
  CoinTopupRequestOut,
  UserOut,
} from "@jkr/contracts";
import { adminCoinsApi, authApi } from "@jkr/sdk";
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
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Coins,
  CreditCard,
  ExternalLink,
  Eye,
  LogOut,
  PhoneCall,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingUp,
  User,
  Users,
  Wallet,
  XCircle,
  Zap,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

interface AdminDashboardProps {
  currentUser: UserOut;
  initialOverview: AdminDashboardOverview | null;
  initialRequests: CoinTopupRequestOut[];
}

export function AdminDashboard({
  currentUser,
  initialOverview,
  initialRequests,
}: AdminDashboardProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [overview, setOverview] = React.useState<AdminDashboardOverview | null>(initialOverview);
  const [requests, setRequests] = React.useState<CoinTopupRequestOut[]>(initialRequests);
  const [activeTab, setActiveTab] = React.useState<"requests" | "users" | "revenue">("requests");

  const [loading, setLoading] = React.useState(false);
  const [requestFilter, setRequestFilter] = React.useState<"pending" | "approved" | "rejected" | "all">("pending");
  const [requestSearch, setRequestSearch] = React.useState("");
  const [userSearch, setUserSearch] = React.useState("");

  // Screenshot Zoom Modal
  const [activeScreenshotUrl, setActiveScreenshotUrl] = React.useState<string | null>(null);

  // Approve dialog state
  const [approvingId, setApprovingId] = React.useState<string | null>(null);
  const [approveNotes, setApproveNotes] = React.useState("");
  const [actionBusy, setActionBusy] = React.useState(false);

  // Reject dialog state
  const [rejectingId, setRejectingId] = React.useState<string | null>(null);
  const [rejectReason, setRejectReason] = React.useState("");

  const refreshAllData = async () => {
    setLoading(true);
    try {
      const [newOverview, newRequests] = await Promise.all([
        adminCoinsApi.getOverview(),
        adminCoinsApi.listTopupRequests(),
      ]);
      setOverview(newOverview);
      setRequests(newRequests);
      toast({
        title: "Admin Data Refreshed",
        description: "Overview metrics and top-up queue updated.",
        variant: "default",
      });
    } catch (err: any) {
      toast({
        title: "Refresh Failed",
        description: err?.message || "Could not reload data.",
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
      await refreshAllData();
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
      await adminCoinsApi.rejectTopup(rejectingId, {
        notes: rejectReason.trim() || "Payment verification failed",
      });
      toast({
        title: "Top-up Rejected",
        description: "Request marked as rejected. No coins credited.",
        variant: "default",
      });
      setRejectingId(null);
      setRejectReason("");
      await refreshAllData();
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

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } finally {
      router.push("/admin/login");
    }
  };

  // Filtered requests
  const filteredRequests = requests.filter((r) => {
    if (requestFilter !== "all" && r.status !== requestFilter) return false;
    if (requestSearch.trim()) {
      const q = requestSearch.toLowerCase();
      const matchEmail = r.user_email?.toLowerCase().includes(q);
      const matchWs = r.workspace_name?.toLowerCase().includes(q);
      const matchId = r.id.toLowerCase().includes(q);
      return matchEmail || matchWs || matchId;
    }
    return true;
  });

  // Filtered users
  const filteredUsers = (overview?.users || []).filter((u) => {
    if (!userSearch.trim()) return true;
    const q = userSearch.toLowerCase();
    return (
      u.email.toLowerCase().includes(q) ||
      (u.full_name && u.full_name.toLowerCase().includes(q)) ||
      (u.workspace_name && u.workspace_name.toLowerCase().includes(q))
    );
  });

  const pendingCount = requests.filter((r) => r.status === "pending").length;
  const approvedCount = requests.filter((r) => r.status === "approved").length;
  const rejectedCount = requests.filter((r) => r.status === "rejected").length;

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Top Admin Navbar */}
      <header className="sticky top-0 z-30 border-b border-border/80 bg-surface/95 backdrop-blur-md px-4 sm:px-8 py-3.5">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-amber-600 shadow-md shadow-primary/20 border border-primary/30">
              <ShieldCheck className="h-5 w-5 text-black stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base tracking-tight text-foreground">
                  JKR Admin Console
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live System
                </span>
              </div>
              <p className="text-xs text-muted-foreground font-mono">
                Operator: <span className="text-primary font-bold">Platform Super Admin</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={refreshAllData}
              loading={loading}
              className="h-8 text-xs border-border"
            >
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
              Refresh
            </Button>

            <Link href="/app/dashboard">
              <Button variant="ghost" size="sm" className="h-8 text-xs text-muted-foreground hover:text-foreground">
                <Zap className="h-3.5 w-3.5 mr-1 text-primary" />
                Open App
              </Button>
            </Link>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="h-8 text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
            >
              <LogOut className="h-3.5 w-3.5 mr-1" />
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto p-4 sm:p-8 space-y-8">
        {/* KPI Summary Cards Grid */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Card 1: Total Revenue (Income Overview) */}
          <Card className="border-border/80 bg-gradient-to-br from-emerald-500/10 via-surface to-surface shadow-md relative overflow-hidden">
            <div className="absolute right-3 top-3 opacity-15">
              <CreditCard className="h-16 w-16 text-emerald-400" />
            </div>
            <CardHeader className="pb-2">
              <CardDescription className="text-xs uppercase tracking-wider font-semibold text-emerald-400 flex items-center gap-1.5">
                <TrendingUp className="h-3.5 w-3.5" /> Total Platform Revenue
              </CardDescription>
              <CardTitle className="text-3xl font-extrabold text-foreground">
                ₹{(overview?.total_revenue_inr ?? 0).toLocaleString()}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground space-y-1">
              <div className="flex justify-between items-center">
                <span>This Month:</span>
                <strong className="text-emerald-400">
                  ₹{(overview?.revenue_this_month_inr ?? 0).toLocaleString()}
                </strong>
              </div>
              <div className="flex justify-between items-center">
                <span>This Week:</span>
                <strong className="text-foreground">
                  ₹{(overview?.revenue_this_week_inr ?? 0).toLocaleString()}
                </strong>
              </div>
            </CardContent>
          </Card>

          {/* Card 2: Platform Usage Overview */}
          <Card className="border-border/80 bg-gradient-to-br from-primary/10 via-surface to-surface shadow-md relative overflow-hidden">
            <div className="absolute right-3 top-3 opacity-15">
              <Coins className="h-16 w-16 text-primary" />
            </div>
            <CardHeader className="pb-2">
              <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5" /> Total Coins Consumed
              </CardDescription>
              <CardTitle className="text-3xl font-extrabold text-foreground">
                {(overview?.total_coins_spent ?? 0).toLocaleString()}
                <span className="text-xs font-normal text-muted-foreground ml-1.5">coins</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground space-y-1">
              <div className="flex justify-between items-center">
                <span>Talk Time:</span>
                <strong className="text-foreground">
                  {Math.floor((overview?.total_call_seconds ?? 0) / 60)}m{" "}
                  {(overview?.total_call_seconds ?? 0) % 60}s
                </strong>
              </div>
              <div className="flex justify-between items-center">
                <span>Total Calls:</span>
                <strong className="text-foreground">{overview?.total_calls_count ?? 0} connected</strong>
              </div>
            </CardContent>
          </Card>

          {/* Card 3: Users & Workspaces */}
          <Card className="border-border/80 bg-surface shadow-md relative overflow-hidden">
            <div className="absolute right-3 top-3 opacity-15">
              <Users className="h-16 w-16 text-muted-foreground" />
            </div>
            <CardHeader className="pb-2">
              <CardDescription className="text-xs uppercase tracking-wider font-semibold text-muted-foreground flex items-center gap-1.5">
                <Building2 className="h-3.5 w-3.5" /> Registered Community
              </CardDescription>
              <CardTitle className="text-3xl font-extrabold text-foreground">
                {(overview?.total_users_count ?? 0).toLocaleString()}
                <span className="text-xs font-normal text-muted-foreground ml-1.5">users</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground space-y-1">
              <div className="flex justify-between items-center">
                <span>Active Workspaces:</span>
                <strong className="text-foreground">{overview?.total_workspaces_count ?? 0}</strong>
              </div>
              <div className="flex justify-between items-center">
                <span>Total Recharged:</span>
                <strong className="text-primary font-bold">
                  +{(overview?.total_coins_recharged ?? 0).toLocaleString()} coins
                </strong>
              </div>
            </CardContent>
          </Card>

          {/* Card 4: Top-up Review Queue */}
          <Card className="border-border/80 bg-surface shadow-md relative overflow-hidden">
            <div className="absolute right-3 top-3 opacity-15">
              <Clock className="h-16 w-16 text-amber-400" />
            </div>
            <CardHeader className="pb-2">
              <CardDescription className="text-xs uppercase tracking-wider font-semibold text-amber-400 flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" /> Review Queue
              </CardDescription>
              <CardTitle className="text-3xl font-extrabold text-foreground flex items-center gap-2">
                <span>{pendingCount}</span>
                <span className="text-xs font-normal text-amber-400">pending review</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground space-y-1">
              <div className="flex justify-between items-center">
                <span>Approved:</span>
                <strong className="text-emerald-400 font-semibold">{approvedCount} payments</strong>
              </div>
              <div className="flex justify-between items-center">
                <span>Rejected:</span>
                <strong className="text-rose-400">{rejectedCount} payments</strong>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 border-b border-border/80 pb-3">
          <Button
            size="sm"
            variant={activeTab === "requests" ? "gradient" : "ghost"}
            onClick={() => setActiveTab("requests")}
            className="text-xs font-semibold h-9"
          >
            <Clock className="h-3.5 w-3.5 mr-1.5" />
            Top-up Requests &amp; Approvals
            {pendingCount > 0 && (
              <span className="ml-2 rounded-full bg-amber-500 text-black px-1.5 py-0.2 text-[10px] font-black">
                {pendingCount}
              </span>
            )}
          </Button>

          <Button
            size="sm"
            variant={activeTab === "users" ? "gradient" : "ghost"}
            onClick={() => setActiveTab("users")}
            className="text-xs font-semibold h-9"
          >
            <Users className="h-3.5 w-3.5 mr-1.5" />
            Users &amp; Balances ({overview?.users?.length ?? 0})
          </Button>

          <Button
            size="sm"
            variant={activeTab === "revenue" ? "gradient" : "ghost"}
            onClick={() => setActiveTab("revenue")}
            className="text-xs font-semibold h-9"
          >
            <TrendingUp className="h-3.5 w-3.5 mr-1.5" />
            Income &amp; Usage Telemetry
          </Button>
        </div>

        {/* TAB 1: Top-up Requests & Approvals */}
        {activeTab === "requests" && (
          <div className="space-y-4">
            {/* Filter and Search Bar */}
            <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
              <div className="flex items-center gap-1.5 overflow-x-auto p-1 bg-surface-raised rounded-xl border border-border">
                <Button
                  size="sm"
                  variant={requestFilter === "pending" ? "gradient" : "ghost"}
                  className="text-xs h-8"
                  onClick={() => setRequestFilter("pending")}
                >
                  Pending ({pendingCount})
                </Button>
                <Button
                  size="sm"
                  variant={requestFilter === "approved" ? "gradient" : "ghost"}
                  className="text-xs h-8"
                  onClick={() => setRequestFilter("approved")}
                >
                  Approved ({approvedCount})
                </Button>
                <Button
                  size="sm"
                  variant={requestFilter === "rejected" ? "gradient" : "ghost"}
                  className="text-xs h-8"
                  onClick={() => setRequestFilter("rejected")}
                >
                  Rejected ({rejectedCount})
                </Button>
                <Button
                  size="sm"
                  variant={requestFilter === "all" ? "gradient" : "ghost"}
                  className="text-xs h-8"
                  onClick={() => setRequestFilter("all")}
                >
                  All ({requests.length})
                </Button>
              </div>

              <div className="relative w-full sm:w-72">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={requestSearch}
                  onChange={(e) => setRequestSearch(e.target.value)}
                  placeholder="Search email, workspace..."
                  className="pl-8 h-9 text-xs"
                />
              </div>
            </div>

            {/* Table */}
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
                          No top-up requests found under the selected filter.
                        </td>
                      </tr>
                    ) : (
                      filteredRequests.map((req) => (
                        <tr key={req.id} className="hover:bg-surface-raised/40 transition-colors">
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
                                ({req.base_coins} + {req.bonus_coins} bonus)
                              </div>
                            )}
                          </td>

                          <td className="py-3.5 px-4">
                            <button
                              type="button"
                              onClick={() => setActiveScreenshotUrl(req.screenshot_url)}
                              className="group flex items-center gap-2 rounded-lg border border-border/80 bg-surface-raised p-1.5 hover:border-primary/50 transition-all text-left"
                            >
                              <div className="h-8 w-8 rounded overflow-hidden bg-black relative flex items-center justify-center border border-border/60">
                                <Eye className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                              </div>
                              <div className="text-[11px]">
                                <span className="font-medium text-foreground block group-hover:text-primary">
                                  View Screenshot
                                </span>
                                <span className="text-[10px] text-muted-foreground">Click to inspect</span>
                              </div>
                            </button>
                          </td>

                          <td className="py-3.5 px-4 text-muted-foreground text-[11px]">
                            {new Date(req.created_at).toLocaleString("en-IN", {
                              dateStyle: "medium",
                              timeStyle: "short",
                            })}
                            {req.reviewed_at && (
                              <div className="text-[10px] text-muted-foreground/80 mt-1">
                                Reviewed:{" "}
                                {new Date(req.reviewed_at).toLocaleTimeString("en-IN", {
                                  timeStyle: "short",
                                })}
                              </div>
                            )}
                          </td>

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
                                  <p className="text-[10px] text-muted-foreground italic truncate max-w-[130px]">
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
                                  <p className="text-[10px] text-rose-400/90 italic truncate max-w-[130px]">
                                    {req.admin_notes}
                                  </p>
                                )}
                              </div>
                            )}
                          </td>

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
          </div>
        )}

        {/* TAB 2: Users & Coin Balances Overview */}
        {activeTab === "users" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Registered User Directory</h3>
                <p className="text-xs text-muted-foreground">
                  Real registered users, account creation dates, linked workspaces, and live coin balances.
                </p>
              </div>

              <div className="relative w-full sm:w-72">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  value={userSearch}
                  onChange={(e) => setUserSearch(e.target.value)}
                  placeholder="Filter users by email or workspace..."
                  className="pl-8 h-9 text-xs"
                />
              </div>
            </div>

            <Card className="border-border/80 bg-surface shadow-md overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-raised border-b border-border text-muted-foreground font-semibold uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="py-3 px-4">User Email &amp; Name</th>
                      <th className="py-3 px-4">Signup Date</th>
                      <th className="py-3 px-4">Workspace</th>
                      <th className="py-3 px-4">Active Coin Balance</th>
                      <th className="py-3 px-4">Recharged / Spent</th>
                      <th className="py-3 px-4 text-right">User ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filteredUsers.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-12 text-center text-muted-foreground">
                          No users match the search criteria.
                        </td>
                      </tr>
                    ) : (
                      filteredUsers.map((u) => (
                        <tr key={u.user_id} className="hover:bg-surface-raised/40 transition-colors">
                          <td className="py-3.5 px-4">
                            <div className="font-semibold text-foreground text-sm flex items-center gap-1.5">
                              <User className="h-3.5 w-3.5 text-primary" />
                              {u.email}
                            </div>
                            {u.full_name && (
                              <div className="text-[11px] text-muted-foreground">{u.full_name}</div>
                            )}
                          </td>

                          <td className="py-3.5 px-4 text-muted-foreground">
                            {new Date(u.signup_date).toLocaleDateString("en-IN", {
                              day: "numeric",
                              month: "short",
                              year: "numeric",
                            })}
                          </td>

                          <td className="py-3.5 px-4">
                            <span className="font-medium text-foreground">{u.workspace_name}</span>
                          </td>

                          <td className="py-3.5 px-4">
                            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/30 text-primary font-bold text-xs">
                              <Coins className="h-3.5 w-3.5" />
                              {u.coin_balance.toLocaleString()}
                            </div>
                          </td>

                          <td className="py-3.5 px-4 space-y-0.5">
                            <div className="text-emerald-400 font-semibold text-[11px]">
                              +{u.total_recharged_coins.toLocaleString()} credited
                            </div>
                            <div className="text-amber-400 text-[11px]">
                              -{u.total_spent_coins.toLocaleString()} used
                            </div>
                          </td>

                          <td className="py-3.5 px-4 text-right font-mono text-[10px] text-muted-foreground">
                            {u.user_id.slice(0, 8)}...
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* TAB 3: Income & Usage Telemetry */}
        {activeTab === "revenue" && (
          <div className="space-y-6">
            <div>
              <h3 className="text-base font-bold text-foreground">Revenue by Top-up Tier</h3>
              <p className="text-xs text-muted-foreground">
                Distribution of sales across configured top-up tiers.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {(overview?.revenue_by_tier || []).map((t) => (
                <Card key={t.tier_id} className="border-border/80 bg-surface shadow-md p-5 space-y-3">
                  <div className="flex justify-between items-center">
                    <Badge variant="outline" className="border-primary/40 text-primary font-semibold">
                      {t.tier_id === "tier_100"
                        ? "Starter"
                        : t.tier_id === "tier_250"
                        ? "Most Popular"
                        : "Pro Value"}
                    </Badge>
                    <span className="text-base font-extrabold text-foreground">₹{t.price_inr}</span>
                  </div>

                  <div className="space-y-1">
                    <div className="text-2xl font-black text-emerald-400">
                      ₹{t.total_revenue_inr.toLocaleString()}
                    </div>
                    <p className="text-xs text-muted-foreground">Total Revenue from this Tier</p>
                  </div>

                  <div className="pt-2 border-t border-border/60 flex justify-between items-center text-xs">
                    <span className="text-muted-foreground">Approved Orders:</span>
                    <strong className="text-foreground">{t.approved_count}</strong>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-muted-foreground">Coins Issued:</span>
                    <strong className="text-primary">
                      {(t.approved_count * t.total_coins).toLocaleString()}
                    </strong>
                  </div>
                </Card>
              ))}
            </div>

            {/* Income & Usage Comparison Card */}
            <Card className="border-border/80 bg-surface shadow-md p-6 space-y-4">
              <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" /> Platform Usage &amp; Unit Economics
              </h4>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-border bg-surface-raised p-4 space-y-1">
                  <span className="text-xs text-muted-foreground">Total Income Realized:</span>
                  <p className="text-xl font-extrabold text-emerald-400">
                    ₹{(overview?.total_revenue_inr ?? 0).toLocaleString()}
                  </p>
                  <p className="text-[11px] text-muted-foreground">From verified manual UPI payments</p>
                </div>

                <div className="rounded-xl border border-border bg-surface-raised p-4 space-y-1">
                  <span className="text-xs text-muted-foreground">Total Talk Time Delivered:</span>
                  <p className="text-xl font-extrabold text-primary">
                    {Math.floor((overview?.total_call_seconds ?? 0) / 60)} minutes
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    {(overview?.total_call_seconds ?? 0).toLocaleString()} total seconds consumed
                  </p>
                </div>

                <div className="rounded-xl border border-border bg-surface-raised p-4 space-y-1">
                  <span className="text-xs text-muted-foreground">Platform Burn Rate:</span>
                  <p className="text-xl font-extrabold text-foreground">
                    {(overview?.total_coins_spent ?? 0).toLocaleString()} coins
                  </p>
                  <p className="text-[11px] text-muted-foreground">1 coin = 1 connected second</p>
                </div>
              </div>
            </Card>
          </div>
        )}
      </main>

      {/* Screenshot Zoom Modal */}
      {activeScreenshotUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
          onClick={() => setActiveScreenshotUrl(null)}
        >
          <div
            className="relative max-h-[90vh] max-w-[90vw] overflow-hidden rounded-2xl bg-card p-4 border border-border shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-border mb-3">
              <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                <Eye className="h-4 w-4 text-primary" />
                Payment Proof Inspection
              </h3>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => setActiveScreenshotUrl(null)}
              >
                ✕
              </Button>
            </div>
            <div className="relative max-h-[75vh] overflow-auto flex items-center justify-center">
              <img
                src={activeScreenshotUrl}
                alt="Payment Proof"
                className="max-h-[70vh] w-auto rounded-lg object-contain shadow-md"
              />
            </div>
            <div className="mt-3 text-right">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setActiveScreenshotUrl(null)}
                className="text-xs"
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Approve Confirmation Modal */}
      {approvingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <Card className="w-full max-w-md border-emerald-500/40 bg-card shadow-2xl">
            <CardHeader>
              <CardTitle className="text-base font-bold text-foreground flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                Approve Payment &amp; Credit Coins
              </CardTitle>
              <CardDescription className="text-xs">
                This will credit the tier&apos;s coins to the customer&apos;s workspace wallet immediately.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="approve-notes" className="text-xs font-medium">
                  Admin Verification Note (optional)
                </Label>
                <Input
                  id="approve-notes"
                  placeholder="e.g. Verified PhonePe transaction ID in bank statement"
                  value={approveNotes}
                  onChange={(e) => setApproveNotes(e.target.value)}
                  className="mt-1 text-xs"
                />
              </div>
              <div className="flex justify-end gap-2">
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
                  variant="gradient"
                  size="sm"
                  onClick={handleApprove}
                  loading={actionBusy}
                  className="text-xs font-bold"
                >
                  Confirm &amp; Credit Coins
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Reject Confirmation Modal */}
      {rejectingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <Card className="w-full max-w-md border-rose-500/40 bg-card shadow-2xl">
            <CardHeader>
              <CardTitle className="text-base font-bold text-foreground flex items-center gap-2">
                <XCircle className="h-5 w-5 text-rose-400" />
                Reject Top-up Request
              </CardTitle>
              <CardDescription className="text-xs">
                The payment could not be verified. No coins will be credited.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
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
              <div className="flex justify-end gap-2">
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
      )}
    </div>
  );
}
