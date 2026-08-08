"use client";

import { AgentCreate, LANGUAGE_OPTIONS, type PersonaTemplateOut } from "@jkr/contracts";
import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export function NewAgentForm({ workspaceId, templates }: { workspaceId: string; templates: PersonaTemplateOut[] }) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AgentCreate>({
    resolver: zodResolver(AgentCreate),
    defaultValues: { primary_language: "te-en-IN", persona_template: templates[0]?.key ?? "warm_receptionist" },
  });

  const onSubmit = async (data: AgentCreate) => {
    setFormError(null);
    try {
      const agent = await agentsApi.create(workspaceId, data);
      router.push(`/app/agents/${agent.id}`);
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not create agent.");
    }
  };

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>New agent</CardTitle>
        <CardDescription>
          Starts from a persona template with a disclosure-compliant greeting already filled in —
          you can edit everything after.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="agent-name">Agent name</Label>
            <Input id="agent-name" placeholder="Dental Receptionist" {...register("name")} />
            <FieldError>{errors.name?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="business-identity">Business identity (spoken in greeting)</Label>
            <Input id="business-identity" placeholder="Aaha Dental Care" {...register("business_identity")} />
            <FieldError>{errors.business_identity?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="persona-template">Persona template</Label>
            <select
              id="persona-template"
              className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              {...register("persona_template")}
            >
              {templates.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="primary-language">Primary language</Label>
            <select
              id="primary-language"
              className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              {...register("primary_language")}
            >
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Create agent
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
