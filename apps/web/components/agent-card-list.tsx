"use client";

import { LANGUAGE_OPTIONS, type AgentOut } from "@jkr/contracts";
import { Badge, Button, Card, CardContent } from "@jkr/ui";
import { Bot, Edit2, MoreVertical, PhoneCall, Trash2 } from "lucide-react";
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

export function AgentCardList({ workspaceId, initialAgents }: AgentCardListProps) {
  const router = useRouter();
  const [agents, setAgents] = React.useState<AgentOut[]>(initialAgents);
  const [editingAgent, setEditingAgent] = React.useState<AgentOut | null>(null);
  const [deletingAgent, setDeletingAgent] = React.useState<AgentOut | null>(null);

  React.useEffect(() => {
    setAgents(initialAgents);
  }, [initialAgents]);

  const getLanguageLabel = (code: string) => {
    const opt = LANGUAGE_OPTIONS.find((o) => o.value === code || o.code === code);
    if (!opt) return { label: code, code };
    return { label: opt.label, code: opt.code };
  };

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent) => {
          const lang = getLanguageLabel(agent.primary_language);
          return (
            <Card
              key={agent.id}
              className="group relative flex flex-col justify-between transition-all duration-150 hover:border-primary/50 hover:shadow-md"
            >
              <CardContent className="p-5 flex-1 flex flex-col justify-between">
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="rounded-lg bg-primary/10 p-2 text-primary">
                        <Bot className="h-5 w-5" />
                      </div>
                      <Badge variant={STATUS_VARIANT[agent.status] ?? "secondary"} className="text-[11px]">
                        {agent.status}
                      </Badge>
                    </div>

                    {/* Action buttons on card */}
                    <div className="flex items-center gap-1 opacity-90 transition-opacity">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                        title={`Edit ${agent.name}`}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setEditingAgent(agent);
                        }}
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-danger hover:bg-danger/10"
                        title={`Delete ${agent.name}`}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setDeletingAgent(agent);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>

                  <Link href={`/app/agents/${agent.id}`} className="block group-hover:text-primary transition-colors">
                    <h3 className="font-semibold text-foreground text-base tracking-tight">{agent.name}</h3>
                    <p className="text-sm text-muted-foreground mt-0.5 line-clamp-1">{agent.business_identity || "Our Business"}</p>
                  </Link>
                </div>

                <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between">
                  {/* Friendly Language Name with Code in small text */}
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{lang.label}</span>
                    <span className="font-mono text-[10px] text-muted-foreground/70">({lang.code})</span>
                  </div>

                  <Link
                    href={`/app/agents/${agent.id}`}
                    className="text-xs font-semibold text-primary hover:underline"
                  >
                    Manage →
                  </Link>
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
