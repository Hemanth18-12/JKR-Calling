"use client";

import { AgentCreate, LANGUAGE_OPTIONS, type PersonaTemplateOut } from "@jkr/contracts";
import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FieldError, Input, Label, Textarea } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

export function NewAgentForm({
  workspaceId,
  templates,
  initialPrompt,
  initialCategory,
}: {
  workspaceId: string;
  templates: PersonaTemplateOut[];
  initialPrompt?: string;
  initialCategory?: string;
}) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);

  // Derive initial values from initialPrompt if passed
  const derivedValues = React.useMemo(() => {
    let name = "New Calling Agent";
    let business = "My Business";
    let template = templates[0]?.key ?? "warm_receptionist";

    if (initialPrompt) {
      const lower = initialPrompt.toLowerCase();
      if (lower.includes("dental") || lower.includes("clinic") || lower.includes("appointment")) {
        name = "Dental Appointment Coordinator";
        business = "Aaha Dental Care";
        template = "appointment_coordinator";
      } else if (lower.includes("real estate") || lower.includes("sales") || lower.includes("lead")) {
        name = "Property Sales Qualifier";
        business = "Hyderabad Properties";
        template = "sales_qualifier";
      } else if (lower.includes("emi") || lower.includes("payment") || lower.includes("collection")) {
        name = "Payment & EMI Reminder Agent";
        business = "SecureFinance Services";
        template = "retention_specialist";
      } else if (lower.includes("support") || lower.includes("service")) {
        name = "Customer Support Assistant";
        business = "Retail Care";
        template = "warm_receptionist";
      }
    }

    if (initialCategory === "appointments") template = "appointment_coordinator";
    if (initialCategory === "lead_qualification") template = "sales_qualifier";
    if (initialCategory === "collections") template = "retention_specialist";

    return { name, business, template };
  }, [initialPrompt, initialCategory, templates]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AgentCreate>({
    resolver: zodResolver(AgentCreate),
    defaultValues: {
      name: derivedValues.name,
      business_identity: derivedValues.business,
      description: initialPrompt || "",
      primary_language: "te-en-IN",
      persona_template: derivedValues.template,
    },
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
    <Card className="max-w-xl border-border/80 bg-surface">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {initialPrompt && <Sparkles className="h-5 w-5 text-primary" />}
          <span>New Voice AI Assistant</span>
        </CardTitle>
        <CardDescription>
          {initialPrompt
            ? "Pre-populated from your prompt description — customize any fields below before creating."
            : "Starts from a persona template with a disclosure-compliant greeting already filled in — you can edit everything after."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="agent-name">Agent Name</Label>
            <Input id="agent-name" placeholder="Dental Receptionist" {...register("name")} />
            <FieldError>{errors.name?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="business-identity">Business Identity (spoken in greeting)</Label>
            <Input id="business-identity" placeholder="Aaha Dental Care" {...register("business_identity")} />
            <FieldError>{errors.business_identity?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="persona-template">Persona Template</Label>
            <select
              id="persona-template"
              className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
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
            <Label htmlFor="primary-language">Primary Language</Label>
            <select
              id="primary-language"
              className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
              {...register("primary_language")}
            >
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="description">Description / Objective Notes</Label>
            <Textarea
              id="description"
              rows={3}
              placeholder="Internal notes on what this agent handles..."
              {...register("description")}
            />
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" variant="gradient" className="w-full font-bold" loading={isSubmitting}>
            Create Agent
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
