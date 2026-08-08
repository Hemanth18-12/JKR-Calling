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
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
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
      { label: "Live console", href: "/app/calls/live", icon: PhoneCall },
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
      <aside
        className={`flex flex-col border-r border-border bg-surface transition-all ${collapsed ? "w-16" : "w-64"}`}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <Button variant="ghost" size="icon" onClick={() => setCollapsed((c) => !c)} aria-label="Toggle sidebar">
            <Menu className="h-4 w-4" />
          </Button>
          {!collapsed ? <span className="text-sm font-semibold tracking-tight">JKR AI Calling</span> : null}
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-4">
          {NAV.map((group) => (
            <div key={group.label || "root"}>
              {group.label && !collapsed ? (
                <p className="mb-1 px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
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
                      className={`flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors ${
                        active
                          ? "bg-primary/15 text-primary"
                          : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
                      }`}
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed ? item.label : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border bg-surface px-6">
          <div className="flex items-center gap-3">
            {workspaces.length > 0 ? (
              <select
                className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
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
            <Badge variant="warning" className="uppercase">
              local
            </Badge>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{me.user.full_name}</span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
