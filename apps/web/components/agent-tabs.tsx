"use client";

import { Badge } from "@jkr/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { label: "Overview", segment: "" },
  { label: "Persona", segment: "persona" },
  { label: "Voice", segment: "voice" },
  { label: "Versions", segment: "versions" },
  { label: "Knowledge", segment: "knowledge" },
  { label: "Tools", segment: "tools" },
  { label: "Test Lab", segment: "test" },
];

export function AgentTabs({ agentId, agentName, status }: { agentId: string; agentName: string; status: string }) {
  const pathname = usePathname();
  const base = `/app/agents/${agentId}`;

  return (
    <div className="border-b border-border bg-surface px-8 pt-6">
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{agentName}</h1>
        <Badge variant={status === "active" ? "success" : "secondary"}>{status}</Badge>
      </div>
      <nav className="flex gap-1">
        {TABS.map((tab) => {
          const href = tab.segment ? `${base}/${tab.segment}` : base;
          const active = pathname === href;
          return (
            <Link
              key={tab.label}
              href={href as never}
              className={`rounded-t-md px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
