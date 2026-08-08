"use client";

import { MemberInvite, ROLE_OPTIONS, type MemberOut } from "@jkr/contracts";
import { ApiClientError, workspacesApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FieldError,
  Input,
  Label,
  useToast,
} from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

const STATUS_VARIANT: Record<string, "success" | "warning" | "secondary"> = {
  active: "success",
  invited: "warning",
  suspended: "secondary",
};

export function TeamMembers({ workspaceId, members }: { workspaceId: string; members: MemberOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MemberInvite>({ resolver: zodResolver(MemberInvite), defaultValues: { role_key: "viewer" } });

  const onInvite = async (data: MemberInvite) => {
    setFormError(null);
    try {
      await workspacesApi.inviteMember(workspaceId, data);
      toast({ title: "Invited", description: `${data.email} added as ${data.role_key}`, variant: "success" });
      reset({ email: "", role_key: "viewer" });
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not invite member.");
    }
  };

  const setStatus = async (memberId: string, status: "active" | "suspended") => {
    await workspacesApi.updateMember(workspaceId, memberId, { status });
    router.refresh();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>{members.length} people have access to this workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-border">
            {members.map((m) => (
              <div key={m.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="text-sm font-medium">{m.full_name}</p>
                  <p className="text-xs text-muted-foreground">{m.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{m.role_key.replace(/_/g, " ")}</Badge>
                  <Badge variant={STATUS_VARIANT[m.status] ?? "secondary"}>{m.status}</Badge>
                  {m.status === "invited" ? (
                    <Button size="sm" variant="secondary" onClick={() => setStatus(m.id, "active")}>
                      Activate
                    </Button>
                  ) : m.status === "active" ? (
                    <Button size="sm" variant="ghost" onClick={() => setStatus(m.id, "suspended")}>
                      Suspend
                    </Button>
                  ) : (
                    <Button size="sm" variant="secondary" onClick={() => setStatus(m.id, "active")}>
                      Reactivate
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invite someone</CardTitle>
          <CardDescription>They need an existing JKR AI Calling account.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onInvite)} className="space-y-4">
            <div>
              <Label htmlFor="invite-email">Email</Label>
              <Input id="invite-email" type="email" {...register("email")} />
              <FieldError>{errors.email?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="invite-role">Role</Label>
              <select
                id="invite-role"
                className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                {...register("role_key")}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.label}
                  </option>
                ))}
              </select>
              <FieldError>{errors.role_key?.message}</FieldError>
            </div>
            {formError ? <p className="text-sm text-danger">{formError}</p> : null}
            <Button type="submit" className="w-full" loading={isSubmitting}>
              Send invite
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
