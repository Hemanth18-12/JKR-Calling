"use client";

import { type AgentToolOut, TOOL_NAME_LABELS } from "@jkr/contracts";
import { ApiClientError, toolsApi } from "@jkr/sdk";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, useToast } from "@jkr/ui";
import * as React from "react";

const REAL_SIDE_EFFECT_TOOLS = new Set([
  "book_appointment", "reschedule_appointment", "cancel_appointment", "create_human_callback", "send_whatsapp", "send_sms",
]);

export function AgentToolsEditor({
  workspaceId, agentVersionId, initialTools,
}: {
  workspaceId: string; agentVersionId: string; initialTools: AgentToolOut[];
}) {
  const { toast } = useToast();
  const [tools, setTools] = React.useState(initialTools);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const toggle = async (toolDefinitionId: string, enabled: boolean) => {
    setBusyId(toolDefinitionId);
    try {
      const updated = await toolsApi.setAgentToolEnabled(workspaceId, agentVersionId, toolDefinitionId, enabled);
      setTools((prev) => prev.map((t) => (t.tool_definition_id === toolDefinitionId ? updated : t)));
    } catch (err) {
      toast({ title: "Could not update tool", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Tools</CardTitle>
        <CardDescription>
          Which business actions this agent version can take during a call. Tools marked &quot;live effect&quot; write
          real records (appointments, handoffs, messages); the rest are mock-only this pass.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-border">
          {tools.map((t) => (
            <label key={t.tool_definition_id} className="flex items-center justify-between py-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{TOOL_NAME_LABELS[t.name] ?? t.name}</span>
                  {REAL_SIDE_EFFECT_TOOLS.has(t.name) ? (
                    <Badge variant="success">live effect</Badge>
                  ) : (
                    <Badge variant="secondary">mock only</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">{t.description}</p>
              </div>
              <input
                type="checkbox"
                checked={t.enabled}
                disabled={busyId === t.tool_definition_id}
                onChange={(e) => toggle(t.tool_definition_id, e.target.checked)}
              />
            </label>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
