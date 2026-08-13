"use client";

import type { MeResponse, WorkspaceListItem } from "@jkr/contracts";
import { authApi } from "@jkr/sdk";
import { Badge, Button, useToast } from "@jkr/ui";
import {
  BarChart3,
  Bot,
  Calendar,
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
  Users,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

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

const NAV: NavGroup[] = [
  { label: "", items: [{ label: "Dashboard", href: "/app/dashboard", icon: Home }] },
  {
    label: "Build",
    items: [
      { label: "Agents", href: "/app/agents", icon: Bot },
      { label: "Knowledge", href: "/app/knowledge/documents", icon: MessageSquareText },
    ],
  },
  {
    label: "Run",
    items: [
      { label: "Campaigns", href: "/app/campaigns", icon: Megaphone },
      { label: "Contacts", href: "/app/contacts", icon: Users },
      { label: "Calls", href: "/app/calls", icon: Phone },
      { label: "Live console", href: "/app/calls/live", icon: PhoneCall, isLive: true },
    ],
  },
  {
    label: "Follow through",
    items: [
      { label: "Follow-ups", href: "/app/follow-ups", icon: MessageSquareText },
      { label: "Handoffs", href: "/app/handoffs", icon: Handshake },
      { label: "Appointments", href: "/app/appointments", icon: Calendar },
    ],
  },
  {
    label: "Understand",
    items: [{ label: "Analytics", href: "/app/analytics", icon: BarChart3 }],
  },
  {
    label: "Govern",
    items: [
      { label: "Compliance", href: "/app/compliance", icon: ShieldCheck },
      { label: "Integrations", href: "/app/integrations", icon: Plug },
      { label: "Billing", href: "/app/billing", icon: CreditCard },
      { label: "Usage", href: "/app/usage", icon: Gauge },
      { label: "Team", href: "/app/team", icon: Users },
      { label: "Settings", href: "/app/settings", icon: Settings },
    ],
  },
];

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
  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? workspaces[0];

  const handleLogout = async () => {
    await authApi.logout();
    toast({ title: "Logged out", variant: "default" });
    router.push("/login");
    router.refresh();
  };

  const handleSwitchWorkspace = async (workspaceId: string) => {
    await authApi.setActiveWorkspace(workspaceId);
    router.push("/app/dashboard");
    router.refresh();
  };

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={`relative flex flex-col border-r border-border bg-surface transition-all duration-300 ${
          collapsed ? "w-16" : "w-64"
        }`}
      >
        {/* Ambient violet glow on sidebar top */}
        <div className="pointer-events-none absolute left-0 top-0 h-40 w-full overflow-hidden">
          <div className="absolute -left-8 -top-8 h-40 w-40 rounded-full bg-primary/8 blur-3xl" />
        </div>

        {/* Logo */}
        <div className="relative flex h-14 items-center gap-2.5 border-b border-border px-3">
          <Button variant="ghost" size="icon" onClick={() => setCollapsed((c) => !c)} aria-label="Toggle sidebar">
            <Menu className="h-4 w-4" />
          </Button>
          {!collapsed ? (
            <div className="flex items-center gap-1.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[#5B3FE4]">
                <Zap className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="font-display text-sm font-bold tracking-tight text-foreground">JKR AI Calling</span>
            </div>
          ) : (
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[#5B3FE4]">
              <Zap className="h-3.5 w-3.5 text-white" />
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-5 overflow-y-auto px-2 py-4">
          {NAV.map((group) => (
            <div key={group.label || "root"}>
              {group.label && !collapsed ? (
                <p className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                  {group.label}
                </p>
              ) : null}
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
                  return (
                    <Link
                      key={item.href}
                      href={item.href as never}
                      className={`group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-150 ${
                        active
                          ? item.isLive
                            ? "bg-secondary/10 text-secondary"
                            : "bg-primary/12 text-primary"
                          : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
                      }`}
                    >
                      {active && (
                        <span
                          className={`absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full ${
                            item.isLive ? "bg-secondary" : "bg-primary"
                          }`}
                        />
                      )}
                      <item.icon
                        className={`h-4 w-4 shrink-0 transition-transform duration-150 group-hover:scale-110 ${
                          item.isLive && active ? "text-secondary" : ""
                        }`}
                      />
                      {!collapsed ? (
                        <span className="truncate">{item.label}</span>
                      ) : null}
                      {!collapsed && item.isLive ? (
                        <span className="ml-auto flex h-1.5 w-1.5 items-center justify-center">
                          <span className="absolute h-2.5 w-2.5 animate-ping rounded-full bg-secondary/60" />
                          <span className="relative h-1.5 w-1.5 rounded-full bg-secondary" />
                        </span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* User foot */}
        {!collapsed && (
          <div className="border-t border-border p-3">
            <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
                {me.user.full_name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-foreground">{me.user.full_name}</p>
                <p className="truncate text-[10px] text-muted-foreground">{me.user.email}</p>
              </div>
            </div>
          </div>
        )}
      </aside>

      {/* Main content area */}
      <div className="flex flex-1 flex-col">
        {/* Top header */}
        <header className="flex h-14 items-center justify-between border-b border-border bg-surface/80 px-6 backdrop-blur-md">
          <div className="flex items-center gap-3">
            {workspaces.length > 0 ? (
              <select
                className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-foreground transition-colors hover:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/30"
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
              <span className="text-sm text-muted-foreground">No workspace yet</span>
            )}
            <Badge variant="mock" className="uppercase tracking-wider">
              MOCK
            </Badge>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{me.user.full_name}</span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-gradient-mesh">{children}</main>
      </div>
    </div>
  );
}
