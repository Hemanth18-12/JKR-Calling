"use client";

import { useEffect, useState } from "react";
import { workspacesApi, ApiClientError } from "@jkr/sdk";
import type { PendingInvitationOut } from "@jkr/contracts";
import { Button, useToast } from "@jkr/ui";
import { Mail, Check, X, Loader2, Sparkles } from "lucide-react";

export function PendingInvitationsBanner() {
  const { toast } = useToast();
  const [invitations, setInvitations] = useState<PendingInvitationOut[]>([]);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function fetchPending() {
      try {
        const list = await workspacesApi.listPendingInvitations();
        if (isMounted) {
          setInvitations(list);
        }
      } catch {
        // Silently fail if unauthenticated or network hiccup
      }
    }
    fetchPending();
    return () => {
      isMounted = false;
    };
  }, []);

  if (invitations.length === 0) return null;

  const handleAccept = async (inv: PendingInvitationOut) => {
    setActionInProgress(inv.id);
    try {
      const res = await workspacesApi.acceptInvitation({ invitation_id: inv.id });
      toast({
        title: "Invitation Accepted! 🎉",
        description: `You are now a member of ${inv.workspace_name} (${inv.role_name}).`,
        variant: "success",
      });
      // Remove from list
      setInvitations((prev) => prev.filter((item) => item.id !== inv.id));
      // Refresh window so workspace switcher & active workspace are live
      setTimeout(() => {
        window.location.reload();
      }, 800);
    } catch (err: any) {
      toast({
        title: "Action failed",
        description: err instanceof ApiClientError ? err.message : "Failed to accept invitation.",
        variant: "danger",
      });
      setActionInProgress(null);
    }
  };

  const handleDecline = async (inv: PendingInvitationOut) => {
    setActionInProgress(inv.id);
    try {
      await workspacesApi.declineInvitation(inv.id);
      toast({
        title: "Invitation Declined",
        description: `Invitation to join ${inv.workspace_name} was declined.`,
        variant: "default",
      });
      setInvitations((prev) => prev.filter((item) => item.id !== inv.id));
    } catch (err: any) {
      toast({
        title: "Action failed",
        description: err instanceof ApiClientError ? err.message : "Failed to decline invitation.",
        variant: "danger",
      });
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="w-full bg-gradient-to-r from-amber-500/15 via-primary/10 to-amber-500/15 border-b border-primary/30 px-4 py-2.5 shadow-sm">
      <div className="max-w-7xl mx-auto flex flex-col gap-2">
        {invitations.map((inv) => (
          <div
            key={inv.id}
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs"
          >
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary border border-primary/30">
                <Mail className="h-3.5 w-3.5" />
              </div>
              <p className="text-foreground">
                <strong className="text-primary font-semibold">{inv.inviter_name}</strong> invited you to join the{" "}
                <strong className="font-bold underline decoration-primary/40 underline-offset-2">
                  {inv.workspace_name}
                </strong>{" "}
                workspace as <span className="font-medium text-primary">[{inv.role_name}]</span>.
              </p>
            </div>

            <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
              <Button
                size="sm"
                variant="gradient"
                disabled={actionInProgress === inv.id}
                onClick={() => handleAccept(inv)}
                className="h-7 px-3 text-[11px] font-bold"
              >
                {actionInProgress === inv.id ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <Check className="h-3 w-3 mr-1" />
                )}
                Accept
              </Button>

              <Button
                size="sm"
                variant="outline"
                disabled={actionInProgress === inv.id}
                onClick={() => handleDecline(inv)}
                className="h-7 px-2.5 text-[11px] text-muted-foreground hover:text-danger hover:border-danger/40"
              >
                <X className="h-3 w-3 mr-1" />
                Decline
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
