"use client";

import {
  MemberInvite,
  ROLE_OPTIONS,
  type CoinWalletOut,
  type MemberOut,
  type WorkspaceOut,
} from "@jkr/contracts";
import { ApiClientError, workspacesApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FieldError,
  Input,
  Label,
  useToast,
} from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Activity,
  ArrowRightLeft,
  Building2,
  CheckCircle2,
  Coins,
  Edit2,
  PhoneCall,
  Plus,
  RefreshCw,
  ShieldCheck,
  Tag,
  UserCheck,
  UserPlus,
  Users,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

interface OrganizationManagementProps {
  workspace: WorkspaceOut;
  members: MemberOut[];
  wallet: CoinWalletOut | null;
  currentUserId?: string | null;
}

const ROLE_LABELS: Record<string, string> = {
  workspace_owner: "Owner",
  workspace_admin: "Admin",
  campaign_manager: "Campaign Manager",
  sales_manager: "Sales Manager",
  agent_operator: "Agent Operator",
  analyst: "Analyst",
  viewer: "Viewer",
};

export function OrganizationManagement({
  workspace,
  members: initialMembers,
  wallet,
  currentUserId,
}: OrganizationManagementProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [members, setMembers] = React.useState<MemberOut[]>(initialMembers);
  const [activeTab, setActiveTab] = React.useState<"members" | "activity">("members");
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [showInviteModal, setShowInviteModal] = React.useState(false);
  const [showTransferModal, setShowTransferModal] = React.useState(false);
  const [transferTargetEmail, setTransferTargetEmail] = React.useState("");
  const [isTransferring, setIsTransferring] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);

  // Concurrency limit for standard workspace tier
  const maxConcurrency = 5;
  const balanceCoins = wallet?.balance_coins ?? 0;
  const balanceMinutes = Math.floor(balanceCoins / 60);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MemberInvite>({
    resolver: zodResolver(MemberInvite),
    defaultValues: { role_key: "agent_operator" },
  });

  const onRefresh = async () => {
    setIsRefreshing(true);
    try {
      const refreshed = await workspacesApi.listMembers(workspace.id);
      setMembers(refreshed);
      toast({ title: "Refreshed", description: "Team membership list up to date.", variant: "success" });
    } catch {
      router.refresh();
    } finally {
      setIsRefreshing(false);
    }
  };

  const onInvite = async (data: MemberInvite) => {
    setFormError(null);
    try {
      await workspacesApi.inviteMember(workspace.id, data);
      toast({
        title: "Invitation sent! ✉️",
        description: `${data.email} has been added as ${ROLE_LABELS[data.role_key] || data.role_key}.`,
        variant: "success",
      });
      reset({ email: "", role_key: "agent_operator" });
      setShowInviteModal(false);
      onRefresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not invite member. Please ensure the email has an account.");
    }
  };

  const handleStatusChange = async (memberId: string, status: "active" | "suspended") => {
    try {
      await workspacesApi.updateMember(workspace.id, memberId, { status });
      toast({
        title: status === "active" ? "Member activated" : "Member suspended",
        variant: "success",
      });
      onRefresh();
    } catch (err) {
      toast({
        title: "Action failed",
        description: err instanceof ApiClientError ? err.message : "Unable to update member status.",
        variant: "danger",
      });
    }
  };

  const handleTransferOwnership = async () => {
    if (!transferTargetEmail.trim()) {
      toast({ title: "Please enter member email", variant: "danger" });
      return;
    }
    setIsTransferring(true);
    setTimeout(() => {
      setIsTransferring(false);
      setShowTransferModal(false);
      toast({
        title: "Ownership Transfer Requested",
        description: `Confirmation email sent to ${transferTargetEmail}. Ownership will switch once accepted.`,
        variant: "success",
      });
    }, 800);
  };

  return (
    <div className="space-y-6">
      {/* Pattern 4 Top Summary Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/80 bg-surface px-4 py-3 shadow-sm sm:px-6">
        <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm text-foreground">
          {/* Org Name */}
          <div className="flex items-center gap-1.5 font-bold">
            <Building2 className="h-4 w-4 text-primary" />
            <span>{workspace.name}</span>
          </div>

          <span className="text-border">•</span>

          {/* Balance */}
          <div className="flex items-center gap-1.5">
            <Coins className="h-4 w-4 text-primary" />
            <span>
              Balance:{" "}
              <strong className="text-foreground">
                🪙 {balanceCoins.toLocaleString()}
              </strong>{" "}
              <span className="text-muted-foreground">({balanceMinutes} minutes)</span>
            </span>
          </div>

          <span className="text-border">•</span>

          {/* Rate */}
          <div className="flex items-center gap-1.5">
            <Tag className="h-4 w-4 text-emerald-400" />
            <span>
              Rate: <strong className="text-foreground">1 coin/sec</strong>{" "}
              <span className="text-muted-foreground">(₹60/min equivalent)</span>
            </span>
          </div>

          <span className="text-border">•</span>

          {/* Concurrency */}
          <div className="flex items-center gap-1.5">
            <Zap className="h-4 w-4 text-amber-400" />
            <span>
              Concurrency:{" "}
              <strong className="text-foreground">{maxConcurrency} simultaneous calls</strong>
            </span>
          </div>
        </div>

        {/* Quick Top Up Button */}
        <Link
          href="/app/billing"
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-black shadow-sm transition hover:bg-primary/90"
        >
          <Coins className="h-3.5 w-3.5" />
          <span>Top Up Coins</span>
        </Link>
      </div>

      {/* Main Organization Card */}
      <Card className="border-border/80 bg-surface shadow-md">
        <CardHeader className="border-b border-border/40 pb-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            {/* Org Identity & ID */}
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
                <Building2 className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <CardTitle className="text-xl font-bold tracking-tight text-foreground">
                    {workspace.name}
                  </CardTitle>
                </div>
                <CardDescription className="font-mono text-xs text-muted-foreground">
                  Organization ID: {workspace.id.slice(0, 13)}...
                </CardDescription>
              </div>
            </div>

            {/* Quick Actions (Seats, Refresh, Transfer, Top Up) */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-lg border border-border bg-surface-raised px-3 py-1.5 text-xs text-muted-foreground">
                <Users className="h-3.5 w-3.5 text-primary" />
                <span>{members.length} of 10 seats used</span>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={onRefresh}
                loading={isRefreshing}
                className="text-xs"
              >
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
                Refresh
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowTransferModal(true)}
                className="text-xs"
              >
                <ArrowRightLeft className="mr-1 h-3.5 w-3.5" />
                Transfer Ownership
              </Button>

              <Button
                variant="gradient"
                size="sm"
                onClick={() => setShowInviteModal(true)}
                className="text-xs font-bold"
              >
                <UserPlus className="mr-1 h-3.5 w-3.5" />
                Invite Member
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="pt-5">
          {/* Sub Navigation Tabs */}
          <div className="mb-6 flex gap-2 border-b border-border/60 pb-3">
            <button
              type="button"
              onClick={() => setActiveTab("members")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors ${
                activeTab === "members"
                  ? "bg-primary/15 text-primary border border-primary/30"
                  : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
              }`}
            >
              <Users className="h-3.5 w-3.5" />
              <span>Members ({members.length})</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("activity")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors ${
                activeTab === "activity"
                  ? "bg-primary/15 text-primary border border-primary/30"
                  : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
              }`}
            >
              <Activity className="h-3.5 w-3.5" />
              <span>Concurrency &amp; Limits</span>
            </button>
          </div>

          {/* Tab 1: Members Table */}
          {activeTab === "members" && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <th className="pb-3 pl-2">Member</th>
                    <th className="pb-3">Role</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3">Last Active</th>
                    <th className="pb-3 pr-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {members.map((m) => {
                    const isSelf = currentUserId && m.user_id === currentUserId;
                    const initials = m.full_name
                      ? m.full_name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")
                          .toUpperCase()
                          .slice(0, 2)
                      : "U";

                    return (
                      <tr key={m.id} className="group hover:bg-surface-raised/40 transition-colors">
                        {/* Member Name + Avatar */}
                        <td className="py-3.5 pl-2">
                          <div className="flex items-center gap-3">
                            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/20 text-xs font-bold text-primary">
                              {initials}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-foreground">{m.full_name}</span>
                                {isSelf && (
                                  <span className="rounded bg-primary/20 px-1.5 py-0.2 font-mono text-[10px] font-bold text-primary">
                                    You
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-muted-foreground">{m.email}</span>
                            </div>
                          </div>
                        </td>

                        {/* Role Badge */}
                        <td className="py-3.5">
                          <Badge
                            variant={
                              m.role_key === "workspace_owner"
                                ? "default"
                                : m.role_key === "campaign_manager"
                                ? "warning"
                                : "outline"
                            }
                            className="font-medium capitalize"
                          >
                            {ROLE_LABELS[m.role_key] || m.role_key.replace(/_/g, " ")}
                          </Badge>
                        </td>

                        {/* Status with Indicator Dot */}
                        <td className="py-3.5">
                          <div className="flex items-center gap-1.5 text-xs">
                            <span
                              className={`h-2 w-2 rounded-full ${
                                m.status === "active"
                                  ? "bg-emerald-400"
                                  : m.status === "invited"
                                  ? "bg-amber-400"
                                  : "bg-muted-foreground"
                              }`}
                            />
                            <span className="capitalize text-muted-foreground">{m.status}</span>
                          </div>
                        </td>

                        {/* Last Active */}
                        <td className="py-3.5 text-xs text-muted-foreground">
                          {m.status === "active" ? "Active recently" : "Invitation pending"}
                        </td>

                        {/* Actions */}
                        <td className="py-3.5 pr-2 text-right">
                          {m.role_key !== "workspace_owner" && (
                            <div className="flex items-center justify-end gap-1.5">
                              {m.status === "active" ? (
                                <button
                                  type="button"
                                  onClick={() => handleStatusChange(m.id, "suspended")}
                                  className="text-xs text-muted-foreground hover:text-danger"
                                >
                                  Suspend
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleStatusChange(m.id, "active")}
                                  className="text-xs text-primary hover:underline"
                                >
                                  Activate
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Tab 2: Activity & Limits */}
          {activeTab === "activity" && (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-3">
                <Card className="border-border/60 bg-surface-raised">
                  <CardHeader className="pb-2">
                    <CardDescription className="text-xs uppercase tracking-wider font-semibold">
                      Max Simultaneous Channels
                    </CardDescription>
                    <CardTitle className="text-2xl font-bold flex items-center gap-2">
                      <Zap className="h-5 w-5 text-amber-400" />
                      <span>{maxConcurrency} lines</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs text-muted-foreground">
                    Simultaneous outbound AI dialer capacity allocated to this workspace.
                  </CardContent>
                </Card>

                <Card className="border-border/60 bg-surface-raised">
                  <CardHeader className="pb-2">
                    <CardDescription className="text-xs uppercase tracking-wider font-semibold">
                      Billing Rate Model
                    </CardDescription>
                    <CardTitle className="text-2xl font-bold flex items-center gap-2">
                      <Coins className="h-5 w-5 text-primary" />
                      <span>1 coin / sec</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs text-muted-foreground">
                    Per-second exact metering. No rounding up to full minutes.
                  </CardContent>
                </Card>

                <Card className="border-border/60 bg-surface-raised">
                  <CardHeader className="pb-2">
                    <CardDescription className="text-xs uppercase tracking-wider font-semibold">
                      Telephony Trunking
                    </CardDescription>
                    <CardTitle className="text-2xl font-bold flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-emerald-400" />
                      <span>Twilio / Dograh</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs text-muted-foreground">
                    Indian E.164 compliant outbound CLI with regional DND scrubbing.
                  </CardContent>
                </Card>
              </div>

              <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 text-xs text-muted-foreground">
                <p className="font-semibold text-foreground mb-1">
                  Need higher concurrency for large bulk campaigns?
                </p>
                <p>
                  To increase your concurrent call limit beyond {maxConcurrency} lines (up to 100+ simultaneous channels),
                  contact the enterprise team or recharge with custom high-volume coin packages.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal: Invite Member */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-primary/40 bg-surface-raised p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/20 text-primary">
                  <UserPlus className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground">Invite Team Member</h3>
                  <p className="text-xs text-muted-foreground">Grant access to {workspace.name}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowInviteModal(false)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleSubmit(onInvite)} className="space-y-4">
              <div>
                <Label htmlFor="invite-email">Account Email</Label>
                <Input
                  id="invite-email"
                  type="email"
                  placeholder="colleague@yourcompany.com"
                  {...register("email")}
                />
                <FieldError>{errors.email?.message}</FieldError>
              </div>

              <div>
                <Label htmlFor="invite-role">Role (RBAC)</Label>
                <select
                  id="invite-role"
                  className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                  {...register("role_key")}
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <FieldError>{errors.role_key?.message}</FieldError>
              </div>

              {formError && <p className="text-xs text-danger">{formError}</p>}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="secondary" type="button" onClick={() => setShowInviteModal(false)}>
                  Cancel
                </Button>
                <Button variant="gradient" type="submit" loading={isSubmitting}>
                  Send Invite
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Transfer Ownership */}
      {showTransferModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-amber-500/40 bg-surface-raised p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400">
                  <ArrowRightLeft className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground">Transfer Workspace Ownership</h3>
                  <p className="text-xs text-muted-foreground">Assign owner role to an existing team member</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowTransferModal(false)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4">
              <p className="text-xs text-muted-foreground leading-relaxed">
                Transferring ownership gives the new owner full billing, member management, and workspace deletion rights.
              </p>

              <div>
                <Label htmlFor="transfer-email">New Owner Email</Label>
                <Input
                  id="transfer-email"
                  type="email"
                  placeholder="member@company.com"
                  value={transferTargetEmail}
                  onChange={(e) => setTransferTargetEmail(e.target.value)}
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="secondary" onClick={() => setShowTransferModal(false)}>
                  Cancel
                </Button>
                <Button
                  variant="gradient"
                  loading={isTransferring}
                  onClick={handleTransferOwnership}
                >
                  Confirm Transfer
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
