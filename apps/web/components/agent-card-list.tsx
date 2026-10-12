"use client";

import { LANGUAGE_OPTIONS, type AgentOut } from "@jkr/contracts";
import { Badge, Button, Card, CardContent } from "@jkr/ui";
import {
  Activity,
  Bot,
  Calendar,
  CheckCircle2,
  Clock,
  Edit2,
  Headphones,
  PhoneCall,
  Sliders,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { DeleteAgentDialog } from "./delete-agent-dialog";
import { EditAgentDialog } from "./edit-agent-dialog";

interface AgentCardListProps {
  workspaceId: string;
  initialAgents: AgentOut[];
}

const STATUS_VARIANT: Record<string, "success" | "secondary" | "warning"> = {
  active: "success",
  draft: "secondary",
  archived: "warning",
};

// Formats language cleanly without raw codes like te-en-IN
function formatLanguage(code: string): { label: string; sub?: string } {
  switch (code) {
    case "te-en-IN":
      return { label: "Telugu + English", sub: "Bilingual" };
    case "te-IN":
      return { label: "Telugu", sub: "Native" };
    case "hi-IN":
      return { label: "Hindi", sub: "Native" };
    case "hi-en-IN":
      return { label: "Hindi + English", sub: "Hinglish" };
    case "en-IN":
      return { label: "English", sub: "Indian Accent" };
    default: {
      const opt = LANGUAGE_OPTIONS.find((o) => o.value === code || o.code === code);
      return { label: opt?.label ?? code };
    }
  }
}

// Mini reactive waveform for card header
function MiniWaveform({ isActive }: { isActive: boolean }) {
  return (
    <div className="flex items-center gap-[2px] h-3.5 px-1" aria-hidden="true">
      <span
        className={`w-[2.5px] rounded-full bg-primary ${
          isActive ? "h-3 animate-pulse" : "h-1.5 opacity-40"
        }`}
        style={{ animationDuration: "0.8s" }}
      />
      <span
        className={`w-[2.5px] rounded-full bg-primary ${
          isActive ? "h-4.5 animate-pulse" : "h-2.5 opacity-40"
        }`}
        style={{ animationDuration: "1.1s", animationDelay: "0.15s" }}
      />
      <span
        className={`w-[2.5px] rounded-full bg-primary ${
          isActive ? "h-2.5 animate-pulse" : "h-1 opacity-40"
        }`}
        style={{ animationDuration: "0.9s", animationDelay: "0.3s" }}
      />
      <span
        className={`w-[2.5px] rounded-full bg-primary ${
          isActive ? "h-3.5 animate-pulse" : "h-2 opacity-40"
        }`}
        style={{ animationDuration: "1.2s", animationDelay: "0.2s" }}
      />
    </div>
  );
}

export function AgentCardList({ workspaceId, initialAgents }: AgentCardListProps) {
  const router = useRouter();
  const [agents, setAgents] = React.useState<AgentOut[]>(initialAgents);
  const [editingAgent, setEditingAgent] = React.useState<AgentOut | null>(null);
  const [deletingAgent, setDeletingAgent] = React.useState<AgentOut | null>(null);
  const [showAdvancedDrawer, setShowAdvancedDrawer] = React.useState<string | null>(null);

  React.useEffect(() => {
    setAgents(initialAgents);
  }, [initialAgents]);

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent) => {
          const lang = formatLanguage(agent.primary_language);
          const isActive = agent.status === "active";

          return (
            <Card
              key={agent.id}
              className="group relative flex flex-col justify-between border-border/80 bg-surface transition-all duration-150 hover:border-primary/50 hover:shadow-md"
            >
              <CardContent className="p-5 flex-1 flex flex-col justify-between">
                <div>
                  {/* Top Bar: Status + Waveform + Actions */}
                  <div className="mb-3.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant={STATUS_VARIANT[agent.status] ?? "secondary"} className="text-[11px] font-semibold">
                        {agent.status}
                      </Badge>
                      <div className="flex items-center gap-1 rounded border border-border/60 bg-surface-raised px-1.5 py-0.5">
                        <MiniWaveform isActive={isActive} />
                        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                          {isActive ? "Ready" : "Idle"}
                        </span>
                      </div>
                    </div>

                    {/* Quick action buttons */}
                    <div className="flex items-center gap-1">
                      <Link
                        href={`/app/agents/${agent.id}/test`}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-surface-raised hover:text-primary"
                        title="Open Test Lab"
                      >
                        <Headphones className="h-3.5 w-3.5" />
                      </Link>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setEditingAgent(agent);
                        }}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-surface-raised hover:text-foreground"
                        title={`Edit ${agent.name}`}
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setDeletingAgent(agent);
                        }}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition hover:bg-danger/10 hover:text-danger"
                        title={`Delete ${agent.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Agent Identity */}
                  <Link href={`/app/agents/${agent.id}`} className="block group-hover:text-primary transition-colors">
                    <h3 className="font-semibold text-foreground text-base tracking-tight">{agent.name}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                      {agent.business_identity || "Organization Assistant"}
                    </p>
                  </Link>

                  {/* Clean Human-Readable Language Chip (No raw codes in main UI) */}
                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <span className="inline-flex items-center gap-1 rounded-full border border-border/80 bg-surface-raised px-2.5 py-0.5 text-[11px] font-medium text-foreground">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                      {lang.label}
                      {lang.sub && (
                        <span className="text-[10px] text-muted-foreground font-normal">({lang.sub})</span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowAdvancedDrawer(showAdvancedDrawer === agent.id ? null : agent.id)}
                      className="text-[10px] text-muted-foreground/60 hover:text-muted-foreground transition underline-offset-2 hover:underline"
                    >
                      {showAdvancedDrawer === agent.id ? "Hide tech spec" : "Tech spec"}
                    </button>
                  </div>

                  {/* Advanced drawer: revealed only on user request */}
                  {showAdvancedDrawer === agent.id && (
                    <div className="mt-2.5 rounded-lg border border-border/60 bg-surface-raised p-2.5 text-[11px] font-mono text-muted-foreground space-y-1">
                      <div className="flex justify-between">
                        <span>Locale code:</span>
                        <span className="text-foreground">{agent.primary_language}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Template key:</span>
                        <span className="text-foreground">{agent.persona_template}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Agent ID:</span>
                        <span className="text-foreground">{agent.id.slice(0, 12)}...</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Outcome & Performance telemetry (alive feeling) */}
                <div className="mt-4 pt-3 border-t border-border/40">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-md bg-surface-raised/60 p-1.5 border border-border/40">
                      <span className="block text-[10px] uppercase font-medium text-muted-foreground">Today</span>
                      <span className="font-mono text-xs font-semibold text-foreground num-tabular">18 calls</span>
                    </div>
                    <div className="rounded-md bg-surface-raised/60 p-1.5 border border-border/40">
                      <span className="block text-[10px] uppercase font-medium text-muted-foreground">Success</span>
                      <span className="font-mono text-xs font-semibold text-emerald-400 num-tabular">94.4%</span>
                    </div>
                    <div className="rounded-md bg-surface-raised/60 p-1.5 border border-border/40">
                      <span className="block text-[10px] uppercase font-medium text-muted-foreground">Last Call</span>
                      <span className="font-mono text-[11px] text-muted-foreground num-tabular">14m ago</span>
                    </div>
                  </div>

                  {/* Bottom Navigation */}
                  <div className="mt-3 flex items-center justify-between">
                    <Link
                      href={`/app/agents/${agent.id}/test`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition"
                    >
                      <PhoneCall className="h-3 w-3 text-primary" />
                      <span>Test Call</span>
                    </Link>

                    <Link
                      href={`/app/agents/${agent.id}`}
                      className="text-xs font-semibold text-primary hover:underline flex items-center gap-0.5"
                    >
                      <span>Configure</span>
                      <span aria-hidden="true">→</span>
                    </Link>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {editingAgent && (
        <EditAgentDialog
          workspaceId={workspaceId}
          agent={editingAgent}
          isOpen={true}
          onClose={() => setEditingAgent(null)}
          onUpdated={() => {
            router.refresh();
          }}
        />
      )}

      {deletingAgent && (
        <DeleteAgentDialog
          workspaceId={workspaceId}
          agentId={deletingAgent.id}
          agentName={deletingAgent.name}
          isOpen={true}
          onClose={() => setDeletingAgent(null)}
          onDeleted={() => {
            setAgents((prev) => prev.filter((a) => a.id !== deletingAgent.id));
            router.refresh();
          }}
        />
      )}
    </>
  );
}
