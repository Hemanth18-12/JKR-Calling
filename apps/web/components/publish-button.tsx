"use client";

import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Button, useToast } from "@jkr/ui";
import { Rocket } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export function PublishButton({ workspaceId, agentId, versionId }: { workspaceId: string; agentId: string; versionId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const [loading, setLoading] = React.useState(false);

  const onPublish = async () => {
    setLoading(true);
    try {
      await agentsApi.publishVersion(workspaceId, agentId, versionId);
      toast({ title: "Published", description: "This version is now live for calls.", variant: "success" });
      router.refresh();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : "Could not publish.";
      const fields = err instanceof ApiClientError ? (err.details?.fields as Record<string, string> | undefined) : undefined;
      toast({
        title: "Cannot publish",
        description: fields ? Object.values(fields).join(" ") : message,
        variant: "danger",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button onClick={onPublish} loading={loading} variant="gradient" size="sm">
      <Rocket className="h-4 w-4" /> Publish this version
    </Button>
  );
}
