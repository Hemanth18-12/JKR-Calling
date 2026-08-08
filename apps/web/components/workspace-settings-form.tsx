"use client";

import { WorkspaceUpdate, type WorkspaceOut } from "@jkr/contracts";
import { ApiClientError, workspacesApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, useToast } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export function WorkspaceSettingsForm({ workspace }: { workspace: WorkspaceOut }) {
  const router = useRouter();
  const { toast } = useToast();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<WorkspaceUpdate>({
    resolver: zodResolver(WorkspaceUpdate),
    defaultValues: {
      name: workspace.name,
      timezone: workspace.timezone,
      default_language: workspace.default_language,
      recording_retention_days: workspace.recording_retention_days,
      transcript_retention_days: workspace.transcript_retention_days,
    },
  });

  const onSubmit = async (data: WorkspaceUpdate) => {
    setFormError(null);
    try {
      await workspacesApi.update(workspace.id, data);
      toast({ title: "Saved", variant: "success" });
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not save settings.");
    }
  };

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Workspace settings</CardTitle>
        <CardDescription>Slug ({workspace.slug}) is permanent.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="ws-name">Business name</Label>
            <Input id="ws-name" {...register("name")} />
          </div>
          <div>
            <Label htmlFor="ws-timezone">Timezone</Label>
            <Input id="ws-timezone" {...register("timezone")} />
          </div>
          <div>
            <Label htmlFor="ws-language">Default language</Label>
            <Input id="ws-language" {...register("default_language")} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="ws-recording">Recording retention (days)</Label>
              <Input id="ws-recording" type="number" {...register("recording_retention_days", { valueAsNumber: true })} />
            </div>
            <div>
              <Label htmlFor="ws-transcript">Transcript retention (days)</Label>
              <Input id="ws-transcript" type="number" {...register("transcript_retention_days", { valueAsNumber: true })} />
            </div>
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" loading={isSubmitting}>
            Save changes
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
