"use client";

import type { MeResponse, WorkspaceListItem } from "@jkr/contracts";
import { authApi, coinsApi } from "@jkr/sdk";
import { Badge, Button, useToast } from "@jkr/ui";
import {
  BarChart3,
  Bot,
  Calendar,
  ChevronRight,
  Coins,
  CreditCard,
  Gauge,
  Handshake,
  Home,
  Megaphone,
  Menu,
  MessageSquareText,
  Phone,
  PhoneCall,
  Plug,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";

import { BackButton } from "./back-button";
import { CommandPalette } from "./command-palette";
import { FaqChatbox } from "./faq-chatbox";
import { GuidedTourProvider, GuidedTourPlayer, StartTourButton } from "./guided-tour";
import { PendingInvitationsBanner } from "./pending-invitations-banner";
import { ThemeToggle } from "./theme-toggle";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  isLive?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Run",
    items: [
      { label: "Dashboard", href: "/app/dashboard", icon: Home },
      { label: "Campaigns", href: "/app/campaigns", icon: Megaphone },
      { label: "Contacts", href: "/app/contacts", icon: Users },
      { label: "Calls", href: "/app/calls", icon: Phone },
      { label: "Live Console", href: "/app/calls/live", icon: PhoneCall, isLive: true },
    ],
  },
  {
    label: "Grow",
    items: [
      { label: "Agents", href: "/app/agents", icon: Bot },
      { label: "Knowledge", href: "/app/knowledge/documents", icon: MessageSquareText },
      { label: "Website Widget", href: "/app/widget", icon: Sparkles },
    ],
  },
  {
    label: "Manage",
    items: [
      { label: "Appointments", href: "/app/appointments", icon: Calendar },
      { label: "Follow-ups", href: "/app/follow-ups", icon: MessageSquareText },
      { label: "Handoffs", href: "/app/handoffs", icon: Handshake },
      { label: "Analytics", href: "/app/analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "Coins & Billing", href: "/app/billing", icon: Coins },
      { label: "Integrations", href: "/app/integrations", icon: Plug },
      { label: "Compliance", href: "/app/compliance", icon: ShieldCheck },
      { label: "Usage", href: "/app/usage", icon: Gauge },
      { label: "Team", href: "/app/team", icon: Users },
      { label: "Settings", href: "/app/settings", icon: Settings },
    ],
  },
];

const MOBILE_NAV_TABS = [
  { label: "Dashboard", href: "/app/dashboard", icon: Home },
  { label: "Calls", href: "/app/calls", icon: Phone },
  { label: "Agents", href: "/app/agents", icon: Bot },
  { label: "Campaigns", href: "/app/campaigns", icon: Megaphone },
  { label: "Wallet", href: "/app/billing", icon: Coins },
];

function BrandWaveformMark() {
  const bars = [4, 12, 18, 10, 16, 8];
  return (
    <div className="flex items-center gap-[2px] h-5" aria-hidden="true">
      {bars.map((h, i) => (
        <span
          key={i}
          className="w-[2.5px] rounded-full bg-primary"
          style={{ height: h }}
        />
      ))}
    </div>
  );
}

export function AppShell({
  me,
  workspaces,
  activeWorkspaceId,
  children,
}: {
  me: MeResponse;
  workspaces: WorkspaceListItem[];
  activeWorkspaceId: string | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { toast } = useToast();
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = React.useState(false);

  React.useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setCollapsed(true);
    }
  }, []);

  // Close mobile drawer on route change
  React.useEffect(() => {
    setMobileDrawerOpen(false);
  }, [pathname]);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? workspaces[0];

  const handleLogout = async () => {
    await authApi.logout();
    toast({ title: "Logged out", variant: "default" });
    window.location.href = "/login";
  };

  const handleSwitchWorkspace = async (workspaceId: string) => {
    await authApi.setActiveWorkspace(workspaceId);
    window.location.href = "/app/dashboard";
  };

  const isNotDashboard = pathname !== "/app/dashboard" && pathname !== "/app";
  const breadcrumbs = getBreadcrumbs(pathname);

  const [coinBalance, setCoinBalance] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (!activeWorkspace?.id) return;
    coinsApi
      .getWallet(activeWorkspace.id)
      .then((w) => setCoinBalance(w.balance_coins))
      .catch(() => {});
  }, [activeWorkspace?.id, pathname]);

  const navGroups = React.useMemo(() => {
    const groups = [...NAV_GROUPS];
    if (me?.user?.is_platform_super_admin) {
      groups.push({
        label: "Platform Admin",
        items: [{ label: "Verify Coins", href: "/app/admin/coins", icon: ShieldCheck }],
      });
    }
    return groups;
  }, [me?.user?.is_platform_super_admin]);

  return (
    <GuidedTourProvider>
      <div className="relative flex min-h-screen bg-background overflow-x-hidden">
        {/* Luminous Multi-Color Aurora Mesh Lighting Backdrop */}
        <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden select-none" aria-hidden="true">
          {/* Solar Gold/Amber Luminous Bloom (Top-Left) */}
          <div className="absolute -top-[12%] -left-[8%] h-[640px] w-[640px] rounded-full bg-gradient-to-br from-amber-400/25 via-yellow-500/15 to-transparent blur-[120px] dark:from-amber-400/18 dark:via-yellow-500/10 animate-aurora-1" />
          {/* Cyber Violet / Electric Indigo Bloom (Top-Right) */}
          <div className="absolute -top-[10%] -right-[8%] h-[700px] w-[700px] rounded-full bg-gradient-to-bl from-indigo-500/22 via-purple-500/18 to-transparent blur-[130px] dark:from-indigo-500/18 dark:via-purple-600/12 animate-aurora-2" />
          {/* Cyan / Aqua Emerald Aurora Glow (Center-Left) */}
          <div className="absolute top-[38%] left-[20%] h-[580px] w-[580px] rounded-full bg-gradient-to-tr from-cyan-400/18 via-teal-400/12 to-transparent blur-[140px] dark:from-cyan-500/12 dark:via-emerald-500/08 animate-aurora-3" />
          {/* Sunset Rose / Coral Radiant Orb (Bottom-Right) */}
          <div className="absolute -bottom-[12%] right-[10%] h-[620px] w-[620px] rounded-full bg-gradient-to-tl from-rose-500/18 via-pink-500/12 to-transparent blur-[140px] dark:from-rose-500/12 dark:via-amber-500/08 animate-aurora-1" />
          {/* Precision Micro-Dot Matrix */}
          <div className="absolute inset-0 bg-[radial-gradient(rgba(100,116,139,0.14)_1px,transparent_1px)] dark:bg-[radial-gradient(rgba(255,255,255,0.06)_1px,transparent_1px)] [background-size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_40%,#000_70%,transparent_100%)] opacity-70" />
        </div>

        {/* Desktop Sidebar */}
        <aside
          className={`relative hidden md:flex flex-col border-r border-border/80 bg-surface/85 backdrop-blur-xl transition-all duration-200 z-30 ${
            collapsed ? "w-16" : "w-60"
          }`}
        >
          {/* Logo & Collapse Header */}
          <div className="flex h-14 items-center justify-between border-b border-border/80 px-3">
            {!collapsed ? (
              <Link href="/app/dashboard" className="flex items-center gap-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-raised border border-border/80 shadow-xs">
                  <BrandWaveformMark />
                </div>
                <span className="font-display text-sm font-bold tracking-tight text-foreground">JKR AI Calling</span>
              </Link>
            ) : (
              <div className="mx-auto flex h-7 w-7 items-center justify-center rounded-lg bg-surface-raised border border-border/80 shadow-xs">
                <BrandWaveformMark />
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
              onClick={() => setCollapsed((c) => !c)}
              aria-label="Toggle sidebar"
            >
              <Menu className="h-4 w-4" />
            </Button>
          </div>

          {/* Navigation Groups */}
          <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3">
            {navGroups.map((group) => (
              <div key={group.label}>
                {!collapsed ? (
                  <p className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                    {group.label}
                  </p>
                ) : null}
                <div className="space-y-0.5">
                  {group.items.map((item) => {
                    const active = pathname === item.href || (item.href !== "/app/dashboard" && pathname?.startsWith(`${item.href}/`));
                    return (
                      <Link
                        key={item.href}
                        href={item.href as never}
                        className={`group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                          active
                            ? "bg-primary/10 text-primary font-semibold"
                            : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
                        }`}
                        title={collapsed ? item.label : undefined}
                      >
                        <item.icon
                          className={`h-4 w-4 shrink-0 transition-colors ${
                            active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                          }`}
                        />
                        {!collapsed && (
                          <div className="flex flex-1 items-center justify-between">
                            <span>{item.label}</span>
                            {item.isLive ? (
                              <span className="flex h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                            ) : null}
                          </div>
                        )}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Admin link for super admin */}
          {me?.user?.is_platform_super_admin && (
            <div className="p-2 border-t border-border">
              <Link
                href="/admin"
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-surface-raised border border-border text-foreground hover:border-primary/40 text-xs font-semibold transition-colors"
              >
                <ShieldCheck className="h-4 w-4 text-primary shrink-0" />
                {!collapsed && (
                  <div className="flex items-center justify-between flex-1">
                    <span>Admin Console</span>
                    <span className="text-[10px] bg-primary text-black px-1 py-0.2 rounded font-bold">
                      Super
                    </span>
                  </div>
                )}
              </Link>
            </div>
          )}

          {/* Persistent Sidebar Coin Runway & User Footer */}
          {!collapsed ? (
            <div className="border-t border-border p-2.5 space-y-2">
              <Link
                href="/app/billing"
                className="flex items-center justify-between rounded-lg border border-border/80 bg-surface-raised px-2.5 py-1.5 text-xs transition-colors hover:border-primary/40"
              >
                <div className="flex items-center gap-1.5">
                  <Coins className="h-3.5 w-3.5 text-primary" />
                  <span className="text-muted-foreground">Coin Balance</span>
                </div>
                <span className="font-mono font-bold tabular-nums text-foreground">
                  {coinBalance !== null ? coinBalance.toLocaleString() : "..."}
                </span>
              </Link>

              <div className="flex items-center gap-2 rounded-lg px-2 py-1">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[11px] font-bold text-primary">
                  {me?.user?.full_name?.charAt(0)?.toUpperCase() ?? "U"}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-foreground">{me?.user?.full_name ?? "User"}</p>
                  <p className="truncate text-[10px] text-muted-foreground">{me?.user?.email ?? ""}</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="border-t border-border p-2 flex justify-center">
              <Link href="/app/billing" title="Coin Balance" className="p-1 text-primary">
                <Coins className="h-4 w-4" />
              </Link>
            </div>
          )}
        </aside>

        {/* Mobile Drawer (When Opened) */}
        <AnimatePresence>
          {mobileDrawerOpen && (
            <div className="fixed inset-0 z-50 md:hidden flex">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setMobileDrawerOpen(false)}
                className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              />
              <motion.div
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ type: "spring", damping: 25, stiffness: 250 }}
                className="relative w-72 max-w-[80vw] bg-surface border-r border-border h-full flex flex-col z-10"
              >
                <div className="flex h-14 items-center justify-between border-b border-border px-4">
                  <Link href="/app/dashboard" className="flex items-center gap-2">
                    <BrandWaveformMark />
                    <span className="font-display text-sm font-bold text-foreground">JKR AI Calling</span>
                  </Link>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0"
                    onClick={() => setMobileDrawerOpen(false)}
                  >
                    ✕
                  </Button>
                </div>

                <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
                  {navGroups.map((group) => (
                    <div key={group.label}>
                      <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                        {group.label}
                      </p>
                      <div className="space-y-0.5">
                        {group.items.map((item) => {
                          const active = pathname === item.href;
                          return (
                            <Link
                              key={item.href}
                              href={item.href as never}
                              className={`flex items-center gap-3 rounded-lg px-2.5 py-2 text-xs font-medium transition-colors ${
                                active
                                  ? "bg-primary/10 text-primary font-semibold"
                                  : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
                              }`}
                            >
                              <item.icon className="h-4 w-4" />
                              <span>{item.label}</span>
                            </Link>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </nav>

                <div className="border-t border-border p-3">
                  <Button variant="outline" size="sm" onClick={handleLogout} className="w-full text-xs">
                    Log out
                  </Button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* Main Content Area */}
        <div className="relative flex flex-1 flex-col min-w-0">
          {/* Top Header */}
          <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border/80 bg-surface/80 px-3 sm:px-6 backdrop-blur-xl shadow-2xs">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              {/* Mobile Menu Button */}
              <button
                type="button"
                onClick={() => setMobileDrawerOpen(true)}
                className="md:hidden flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground hover:text-foreground"
                aria-label="Open navigation menu"
              >
                <Menu className="h-4 w-4" />
              </button>

              {/* Back button if not on root dashboard */}
              {isNotDashboard ? (
                <div className="flex items-center gap-1.5 pr-1 border-r border-border/60">
                  <BackButton fallbackHref="/app/dashboard" size="sm" showLabel={false} />
                </div>
              ) : null}

              {/* Breadcrumb Trail */}
              {breadcrumbs.length > 0 ? (
                <nav aria-label="Breadcrumb" className="hidden lg:flex items-center gap-1 text-xs text-muted-foreground truncate">
                  {breadcrumbs.map((crumb, idx) => (
                    <React.Fragment key={crumb.href}>
                      {idx > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />}
                      {crumb.isLast ? (
                        <span className="font-semibold text-foreground truncate">{crumb.label}</span>
                      ) : (
                        <Link
                          href={crumb.href as never}
                          className="hover:text-foreground transition-colors truncate hover:underline"
                        >
                          {crumb.label}
                        </Link>
                      )}
                    </React.Fragment>
                  ))}
                </nav>
              ) : null}

              {/* Workspace Selector */}
              {workspaces.length > 0 ? (
                <select
                  className="rounded-lg border border-border/80 bg-surface px-2.5 py-1 text-xs text-foreground transition-colors hover:border-primary/40 focus:outline-none focus:ring-1 focus:ring-primary/40 font-medium"
                  value={activeWorkspace?.id ?? ""}
                  onChange={(e) => handleSwitchWorkspace(e.target.value)}
                >
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="text-xs text-muted-foreground">No workspace yet</span>
              )}

              <Badge variant="mock" className="hidden sm:inline-flex text-[10px]">
                Mock Provider
              </Badge>
            </div>

            {/* Right Controls */}
            <div className="flex items-center gap-2 sm:gap-2.5">
              {/* Global Command Palette */}
              <CommandPalette />

              {/* Coin Wallet Balance Chip with SVG icon */}
              <Link
                href="/app/billing"
                className="flex items-center gap-1.5 rounded-lg border border-border/80 bg-surface px-2.5 py-1 text-xs font-semibold text-foreground hover:border-primary/40 transition-colors shadow-2xs"
                title="AI Calling Coin Balance (1 coin = 1 second)"
              >
                <svg className="h-3.5 w-3.5 text-primary shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 6v12M8 10h8M8 14h6" />
                </svg>
                <span className="font-mono text-primary font-bold tabular-nums">
                  {coinBalance !== null ? coinBalance.toLocaleString() : "..."}
                </span>
                <span className="text-[10px] text-muted-foreground hidden sm:inline">coins</span>
              </Link>

              {/* Theme Toggle */}
              <ThemeToggle />

              <StartTourButton
                pageId={getTourPageId(pathname)}
                size="sm"
                variant="outline"
                label="Tour"
                className="hidden sm:inline-flex text-xs h-8"
              />

              <Button variant="outline" size="sm" onClick={handleLogout} className="text-xs hidden sm:inline-flex">
                Log out
              </Button>
            </div>
          </header>

          {/* In-app Pending Invitations Banner */}
          <PendingInvitationsBanner />

          {/* Page Content with padding bottom reserve for mobile tab bar */}
          <main className="relative z-10 flex-1 overflow-y-auto pb-20 md:pb-8">
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className="h-full"
            >
              {children}
            </motion.div>
          </main>

          {/* Global Floating Draggable FAQ Assistant */}
          <FaqChatbox />

          {/* Global Guided Voice Tour Player & Spotlight Overlay */}
          <GuidedTourPlayer />
        </div>

        {/* Mobile Bottom Tab Bar */}
        <nav
          aria-label="Mobile Navigation"
          className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-surface/95 border-t border-border/80 backdrop-blur-md px-2 py-1.5 flex items-center justify-around"
        >
          {MOBILE_NAV_TABS.map((tab) => {
            const active = pathname === tab.href || (tab.href !== "/app/dashboard" && pathname?.startsWith(`${tab.href}/`));
            const Icon = tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href as never}
                className={`flex flex-col items-center gap-1 py-1 px-2.5 rounded-lg text-[10px] font-medium transition-colors ${
                  active ? "text-primary font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-primary" : "text-muted-foreground"}`} />
                <span>{tab.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </GuidedTourProvider>
  );
}

function getTourPageId(pathname: string | null): string {
  if (!pathname) return "dashboard";
  if (pathname.includes("/calls/live")) return "live_console";
  if (pathname.includes("/campaigns")) return "campaigns";
  if (pathname.includes("/calls")) return "calls";
  if (pathname.includes("/analytics")) return "analytics";
  return "dashboard";
}

const ROUTE_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  agents: "Agents",
  persona: "Persona Editor",
  voice: "Voice Persona",
  knowledge: "Knowledge",
  documents: "Documents",
  campaigns: "Campaigns",
  contacts: "Contacts",
  calls: "Calls",
  live: "Live Console",
  "follow-ups": "Follow-ups",
  handoffs: "Handoffs",
  appointments: "Appointments",
  analytics: "Analytics",
  compliance: "Compliance",
  integrations: "Integrations",
  billing: "Billing",
  usage: "Usage",
  team: "Team",
  settings: "Settings",
  new: "New",
};

function getBreadcrumbs(pathname: string | null) {
  if (!pathname || pathname === "/app" || pathname === "/app/dashboard") {
    return [];
  }
  const parts = pathname.replace(/^\/app\/?/, "").split("/").filter(Boolean);
  const crumbs: { label: string; href: string; isLast: boolean }[] = [
    { label: "Dashboard", href: "/app/dashboard", isLast: false },
  ];

  let cumulative = "/app";
  parts.forEach((part, index) => {
    cumulative += `/${part}`;
    const isUuid = /^[0-9a-f-]{36}$/i.test(part);
    const label = ROUTE_LABELS[part] ?? (isUuid ? "Details" : part.charAt(0).toUpperCase() + part.slice(1));
    crumbs.push({
      label,
      href: cumulative,
      isLast: index === parts.length - 1,
    });
  });

  return crumbs;
}
