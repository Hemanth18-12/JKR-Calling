"use client";

import { LANGUAGE_OPTIONS } from "@jkr/contracts";
import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, useToast } from "@jkr/ui";
import { Bot, Edit3, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

interface EditAgentDialogProps {
  workspaceId: string;
  agent: {
    id: string;
    name: string;
    business_identity: string;
    description?: string | null;
    primary_language: string;
    persona_template?: string | null;
    status: string;
  };
  isOpen: boolean;
  onClose: () => void;
  onUpdated?: () => void;
}

const CATEGORY_OPTIONS = [
  { value: "sales_qualifier", label: "Lead Qualification (Sales Qualifier)" },
  { value: "appointment_coordinator", label: "Appointments (Appointment Coordinator)" },
  { value: "warm_receptionist", label: "Customer Support (Warm Receptionist)" },
  { value: "retention_specialist", label: "Payment & Collections (Retention Specialist)" },
  { value: "feedback_collector", label: "Feedback & Follow-up (Feedback Collector)" },
];

export function EditAgentDialog({
  workspaceId,
  agent,
  isOpen,
  onClose,
  onUpdated,
}: EditAgentDialogProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [name, setName] = React.useState(agent.name);
  const [businessIdentity, setBusinessIdentity] = React.useState(agent.business_identity);
  const [description, setDescription] = React.useState(agent.description || "");
  const [language, setLanguage] = React.useState(agent.primary_language || "en-IN");
  const [category, setCategory] = React.useState(agent.persona_template || "warm_receptionist");
  const [regeneratePersona, setRegeneratePersona] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (isOpen) {
      setName(agent.name);
      setBusinessIdentity(agent.business_identity);
      setDescription(agent.description || "");
      setLanguage(agent.primary_language || "en-IN");
      setCategory(agent.persona_template || "warm_receptionist");
      setRegeneratePersona(false);
    }
  }, [isOpen, agent]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast({ title: "Agent name is required", variant: "danger" });
      return;
    }
    if (!businessIdentity.trim()) {
      toast({ title: "Business name is required", variant: "danger" });
      return;
    }

    setIsSubmitting(true);
    try {
      await agentsApi.update(workspaceId, agent.id, {
        name: name.trim(),
        business_identity: businessIdentity.trim(),
        description: description.trim() || undefined,
        primary_language: language,
        persona_template: category,
        regenerate_persona_flag: regeneratePersona,
      });

      toast({
        title: "Agent Updated",
        description: `Successfully updated "${name.trim()}".${regeneratePersona ? " Persona and greeting were refreshed." : ""}`,
        variant: "success",
      });

      onClose();
      if (onUpdated) onUpdated();
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not update agent",
        description: err instanceof ApiClientError ? err.message : "An error occurred while updating the agent.",
        variant: "danger",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <Card className="w-full max-w-lg border-border/80 bg-surface shadow-2xl">
        <CardHeader className="flex flex-row items-start justify-between pb-3">
          <div className="flex items-center gap-2">
            <Edit3 className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-base font-bold text-foreground">Edit Voice AI Assistant</CardTitle>
              <CardDescription className="text-xs">Update agent configuration, business identity, and primary language.</CardDescription>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-surface-raised hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="edit-agent-name">Assistant name</Label>
                <Input
                  id="edit-agent-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Fashion Sales Qualifier"
                  required
                />
              </div>
              <div>
                <Label htmlFor="edit-agent-biz">Business name</Label>
                <Input
                  id="edit-agent-biz"
                  value={businessIdentity}
                  onChange={(e) => setBusinessIdentity(e.target.value)}
                  placeholder="e.g. Crazy Cloths"
                  required
                />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="edit-agent-category">Business Category</Label>
                <select
                  id="edit-agent-category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  {CATEGORY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <Label htmlFor="edit-agent-lang">Primary Language</Label>
                <select
                  id="edit-agent-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  {LANGUAGE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label} ({opt.code})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <Label htmlFor="edit-agent-desc">Description</Label>
              <textarea
                id="edit-agent-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What does this assistant do?"
                rows={2}
                className="w-full rounded-md border border-border bg-surface p-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none"
              />
            </div>

            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
              <label className="flex items-start gap-2.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={regeneratePersona}
                  onChange={(e) => setRegeneratePersona(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-border text-primary focus:ring-primary"
                />
                <div className="text-xs">
                  <span className="font-semibold text-foreground">Regenerate persona, greeting & voice</span>
                  <p className="text-muted-foreground mt-0.5">
                    Automatically rewrites the persona, disclosure, and greeting in the selected language with "{businessIdentity || "your business"}" and category starter text.
                  </p>
                </div>
              </label>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button type="submit" variant="gradient" size="sm" loading={isSubmitting}>
                Save Changes
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
