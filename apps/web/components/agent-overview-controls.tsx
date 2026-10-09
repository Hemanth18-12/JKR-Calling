"use client";

import { LANGUAGE_OPTIONS, type AgentDetail } from "@jkr/contracts";
import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, useToast } from "@jkr/ui";
import { Bot, Edit2, Globe, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { DeleteAgentDialog } from "./delete-agent-dialog";
import { EditAgentDialog } from "./edit-agent-dialog";

interface AgentOverviewControlsProps {
  workspaceId: string;
  agent: AgentDetail;
}

export function AgentOverviewControls({ workspaceId, agent }: AgentOverviewControlsProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [currentLang, setCurrentLang] = React.useState(agent.primary_language || "en-IN");
  const [selectedLang, setSelectedLang] = React.useState(agent.primary_language || "en-IN");
  const [isRegenerating, setIsRegenerating] = React.useState(false);
  const [showEdit, setShowEdit] = React.useState(false);
  const [showDelete, setShowDelete] = React.useState(false);

  React.useEffect(() => {
    setCurrentLang(agent.primary_language || "en-IN");
    setSelectedLang(agent.primary_language || "en-IN");
  }, [agent.primary_language]);

  const getLanguageMeta = (code: string) => {
    const opt = LANGUAGE_OPTIONS.find((o) => o.value === code || o.code === code);
    return opt || { label: code, code };
  };

  const currentMeta = getLanguageMeta(currentLang);
  const selectedMeta = getLanguageMeta(selectedLang);

  const handleLanguageChange = (newCode: string) => {
    setSelectedLang(newCode);
  };

  const handleRegenerate = async (targetLang: string) => {
    setIsRegenerating(true);
    try {
      await agentsApi.regeneratePersona(workspaceId, agent.id, { language: targetLang });
      setCurrentLang(targetLang);
      setSelectedLang(targetLang);
      toast({
        title: "Persona Regenerated",
        description: `Successfully regenerated persona, greeting, and voice in ${getLanguageMeta(targetLang).label}.`,
        variant: "success",
      });
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not regenerate persona",
        description: err instanceof ApiClientError ? err.message : "Failed to regenerate persona.",
        variant: "danger",
      });
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <>
      {/* Top action row */}
      <div className="flex items-center justify-between pb-2">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-foreground">Assistant Overview</h2>
          <p className="text-xs text-muted-foreground">Manage language, persona alignment, and core settings.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowEdit(true)}
            className="gap-1.5 text-xs"
          >
            <Edit2 className="h-3.5 w-3.5" />
            <span>Edit Assistant</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDelete(true)}
            className="gap-1.5 text-xs text-muted-foreground hover:bg-danger/10 hover:text-danger"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>Delete</span>
          </Button>
        </div>
      </div>

      {/* Language & Persona Alignment Banner */}
      <Card className="border-primary/40 bg-gradient-to-r from-primary/10 via-surface to-surface shadow-sm">
        <CardContent className="p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="rounded-xl bg-primary/20 p-2.5 text-primary">
                <Globe className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">Primary Language:</span>
                  <span className="font-bold text-primary text-base">{currentMeta.label}</span>
                  <span className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {currentMeta.code}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Drives speech synthesis, Sarvam STT hints, and LLM persona formulation.
                </p>
              </div>
            </div>

            {/* Language Switcher Selector */}
            <div className="flex items-center gap-2">
              <select
                value={selectedLang}
                onChange={(e) => handleLanguageChange(e.target.value)}
                className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground focus:border-primary focus:outline-none"
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label} ({opt.code})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 1-Click Regenerate Persona Prompt */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-border/80 bg-surface/90 p-3 text-xs">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-400 shrink-0" />
              <span>
                Regenerate persona, greeting, and voice matching{" "}
                <strong className="text-foreground">{selectedMeta.label}</strong> for{" "}
                <strong className="text-foreground">{agent.business_identity || "your business"}</strong>?
              </span>
            </div>
            <Button
              variant={selectedLang !== currentLang ? "gradient" : "secondary"}
              size="sm"
              loading={isRegenerating}
              onClick={() => handleRegenerate(selectedLang)}
              className="gap-1.5 text-xs shrink-0"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>{selectedLang !== currentLang ? `Switch & Regenerate in ${selectedMeta.label}` : "Regenerate Persona"}</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Edit & Delete Dialogs */}
      <EditAgentDialog
        workspaceId={workspaceId}
        agent={agent}
        isOpen={showEdit}
        onClose={() => setShowEdit(false)}
        onUpdated={() => router.refresh()}
      />

      <DeleteAgentDialog
        workspaceId={workspaceId}
        agentId={agent.id}
        agentName={agent.name}
        isOpen={showDelete}
        onClose={() => setShowDelete(false)}
        redirectAfterDelete={true}
      />
    </>
  );
}
