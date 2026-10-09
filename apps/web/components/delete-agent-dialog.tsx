"use client";

import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, useToast } from "@jkr/ui";
import { AlertTriangle, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

interface DeleteAgentDialogProps {
  workspaceId: string;
  agentId: string;
  agentName: string;
  isOpen: boolean;
  onClose: () => void;
  onDeleted?: () => void;
  redirectAfterDelete?: boolean;
}

export function DeleteAgentDialog({
  workspaceId,
  agentId,
  agentName,
  isOpen,
  onClose,
  onDeleted,
  redirectAfterDelete = false,
}: DeleteAgentDialogProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [isDeleting, setIsDeleting] = React.useState(false);

  if (!isOpen) return null;

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      const res = await agentsApi.delete(workspaceId, agentId);
      if (res.action === "archived") {
        toast({
          title: "Agent Archived",
          description: `"${agentName}" has existing call history and was safely archived. Call recordings and analytics are preserved.`,
          variant: "success",
        });
      } else {
        toast({
          title: "Agent Deleted",
          description: `"${agentName}" was deleted successfully.`,
          variant: "success",
        });
      }
      onClose();
      if (onDeleted) {
        onDeleted();
      }
      if (redirectAfterDelete) {
        router.push("/app/agents");
      } else {
        router.refresh();
      }
    } catch (err) {
      toast({
        title: "Could not delete agent",
        description: err instanceof ApiClientError ? err.message : "An error occurred while deleting the agent.",
        variant: "danger",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <Card className="w-full max-w-md border-danger/40 bg-surface shadow-2xl">
        <CardHeader className="flex flex-row items-start justify-between pb-3">
          <div className="flex items-center gap-2 text-danger">
            <AlertTriangle className="h-5 w-5" />
            <CardTitle className="text-base font-bold text-foreground">Delete {agentName}?</CardTitle>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-surface-raised hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </CardHeader>
        <CardContent className="space-y-4">
          <CardDescription className="text-sm leading-relaxed text-muted-foreground">
            Are you sure you want to delete <strong className="text-foreground">{agentName}</strong>? This action cannot be undone.
          </CardDescription>

          <div className="rounded-lg border border-border/80 bg-surface-raised/50 p-3 text-xs text-muted-foreground space-y-1.5">
            <p>
              • If this assistant has completed call history or campaigns, it will be <strong>safely archived</strong> so your past analytics, recordings, and lead data remain intact.
            </p>
            <p>
              • If this assistant is currently assigned to an active campaign, deletion will be blocked until the campaign is paused or reassigned.
            </p>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={isDeleting}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDelete}
              loading={isDeleting}
              className="gap-1.5"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Delete Agent</span>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
