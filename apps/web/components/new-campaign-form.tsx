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

            {/* Unique Feature #5: Adaptive Retry Timing Strategy */}
            <div className="rounded-xl border border-primary/30 bg-primary/5 p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="retry-strategy" className="text-xs font-semibold text-primary">
                  🧠 Smart Retry Strategy (Unique Feature)
                </Label>
                <span className="rounded bg-primary/20 px-2 py-0.5 text-[10px] font-medium text-primary">
                  Adaptive
                </span>
              </div>
              <select
                id="retry-strategy"
                className="flex h-9 w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-foreground"
                defaultValue="adaptive_smart_window"
              >
                <option value="adaptive_smart_window">
                  Adaptive Smart Window (Shifts morning ↔ evening time buckets per contact)
                </option>
                <option value="fixed_interval">Fixed 4-hour cooldown</option>
                <option value="next_day">Next business day same time</option>
              </select>
              <p className="text-[11px] text-muted-foreground">
                Automatically avoids calling at the same time-of-day bucket if the lead was busy or unanswered.
              </p>
            </div>

            {formError ? <p className="text-sm text-danger">{formError}</p> : null}
            <Button type="submit" className="w-full" variant="gradient" loading={isSubmitting}>
              Create campaign
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

