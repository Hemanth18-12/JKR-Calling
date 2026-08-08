"use client";

import { CAMPAIGN_OBJECTIVE_OPTIONS, CampaignCreate } from "@jkr/contracts";
import { ApiClientError, campaignsApi } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export function NewCampaignForm({ workspaceId, agents }: { workspaceId: string; agents: { id: string; name: string }[] }) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CampaignCreate>({
    resolver: zodResolver(CampaignCreate),
    defaultValues: { objective: "qualify_lead", agent_id: agents[0]?.id, max_attempts: 3, required_fields: [], optional_fields: [], success_conditions: [], stop_conditions: [] },
  });

  const onSubmit = async (data: CampaignCreate) => {
    setFormError(null);
    try {
      const campaign = await campaignsApi.create(workspaceId, data);
      router.push(`/app/campaigns/${campaign.id}`);
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not create campaign.");
    }
  };

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>New campaign</CardTitle>
        <CardDescription>Starts in draft. Add contacts, dry-run, then launch.</CardDescription>
      </CardHeader>
      <CardContent>
        {agents.length === 0 ? (
          <p className="text-sm text-warning">No published agent yet — publish an agent version before creating a campaign.</p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <Label htmlFor="campaign-name">Campaign name</Label>
              <Input id="campaign-name" placeholder="September appointment drive" {...register("name")} />
              <FieldError>{errors.name?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="campaign-objective">Objective</Label>
              <select id="campaign-objective" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("objective")}>
                {CAMPAIGN_OBJECTIVE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="campaign-agent">Agent</Label>
              <select id="campaign-agent" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("agent_id")}>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <FieldError>{errors.agent_id?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="campaign-max-attempts">Max attempts per contact</Label>
              <Input id="campaign-max-attempts" type="number" min={1} max={10} {...register("max_attempts", { valueAsNumber: true })} />
              <FieldError>{errors.max_attempts?.message}</FieldError>
            </div>
            {formError ? <p className="text-sm text-danger">{formError}</p> : null}
            <Button type="submit" className="w-full" loading={isSubmitting}>
              Create campaign
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
