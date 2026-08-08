"use client";

import { type AgentVersionOut } from "@jkr/contracts";
import { agentsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent } from "@jkr/ui";
import { useRouter } from "next/navigation";
import * as React from "react";

import { PublishButton } from "@/components/publish-button";

export function VersionsList({ workspaceId, agentId, versions }: { workspaceId: string; agentId: string; versions: AgentVersionOut[] }) {
  const router = useRouter();
  const [creating, setCreating] = React.useState(false);

  const createDraft = async () => {
    setCreating(true);
    try {
      await agentsApi.createVersion(workspaceId, agentId, versions[0]?.id);
      router.refresh();
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-4">
      <Button onClick={createDraft} loading={creating} variant="secondary" size="sm">
        New draft from latest
      </Button>
      <div className="space-y-3">
        {versions.map((v) => (
          <Card key={v.id}>
            <CardContent className="flex items-center justify-between p-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm">v{v.version_number}</span>
                  <Badge variant={v.status === "published" ? "success" : "secondary"}>{v.status}</Badge>
                  {v.published_at ? (
                    <span className="text-xs text-muted-foreground">
                      published {new Date(v.published_at).toLocaleString()}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 max-w-xl truncate text-sm text-muted-foreground">{v.greeting_text}</p>
              </div>
              {v.status !== "published" ? <PublishButton workspaceId={workspaceId} agentId={agentId} versionId={v.id} /> : null}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
