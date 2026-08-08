"use client";

import { AgentVersionUpdate, type AgentVersionDetail } from "@jkr/contracts";
import { agentsApi, ApiClientError } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Textarea,
  useToast,
} from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

const FORMALITY_OPTIONS = ["warm", "balanced", "formal"];
const ENERGY_OPTIONS = ["low", "medium", "high"];
const RESPONSE_LENGTH_OPTIONS = ["short", "medium", "long"];
const CODE_SWITCH_OPTIONS = ["adaptive", "minimal", "heavy"];

export function PersonaEditor({
  workspaceId,
  agentId,
  version,
}: {
  workspaceId: string;
  agentId: string;
  version: AgentVersionDetail;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const readOnly = version.status === "published";
  const {
    register,
    handleSubmit,
    formState: { isSubmitting, isDirty },
  } = useForm<AgentVersionUpdate>({
    resolver: zodResolver(AgentVersionUpdate),
    defaultValues: {
      primary_objective: version.primary_objective,
      ai_disclosure_text: version.ai_disclosure_text,
      greeting_text: version.greeting_text,
      closing_text: version.closing_text,
      formality: version.formality,
      energy: version.energy,
      response_length: version.response_length,
      code_switching_behavior: version.code_switching_behavior,
    },
  });

  const onSubmit = async (data: AgentVersionUpdate) => {
    try {
      await agentsApi.updateVersion(workspaceId, agentId, version.id, data);
      toast({ title: "Saved", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not save",
        description: err instanceof ApiClientError ? err.message : undefined,
        variant: "danger",
      });
    }
  };

  const createNewDraft = async () => {
    const newVersion = await agentsApi.createVersion(workspaceId, agentId, version.id);
    router.push({ pathname: `/app/agents/${agentId}/persona`, query: { version: newVersion.id } } as never);
    router.refresh();
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>
            Persona <Badge variant="outline" className="ml-2">v{version.version_number}</Badge>
          </CardTitle>
          <CardDescription>
            {readOnly ? "Published versions are immutable." : "Draft — changes save to this version."}
          </CardDescription>
        </div>
        {readOnly ? (
          <Button variant="secondary" size="sm" onClick={createNewDraft} type="button">
            Create new version to edit
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <fieldset disabled={readOnly} className="space-y-4 disabled:opacity-60">
          <div>
            <Label htmlFor="ai_disclosure_text">AI disclosure</Label>
            <Textarea id="ai_disclosure_text" {...register("ai_disclosure_text")} />
          </div>
          <div>
            <Label htmlFor="greeting_text">
              Greeting <span className="font-mono text-xs text-muted-foreground">{"{name}"} fills at call time</span>
            </Label>
            <Textarea id="greeting_text" {...register("greeting_text")} />
          </div>
          <div>
            <Label htmlFor="closing_text">Closing</Label>
            <Textarea id="closing_text" {...register("closing_text")} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="primary_objective">Primary objective</Label>
              <Input id="primary_objective" {...register("primary_objective")} />
            </div>
            <div>
              <Label htmlFor="formality">Formality</Label>
              <select id="formality" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("formality")}>
                {FORMALITY_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="energy">Energy</Label>
              <select id="energy" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("energy")}>
                {ENERGY_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="response_length">Response length</Label>
              <select id="response_length" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("response_length")}>
                {RESPONSE_LENGTH_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="code_switching_behavior">Code-switching</Label>
              <select id="code_switching_behavior" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("code_switching_behavior")}>
                {CODE_SWITCH_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
          </div>
          {!readOnly ? (
            <Button onClick={handleSubmit(onSubmit)} type="button" loading={isSubmitting} disabled={!isDirty}>
              Save persona
            </Button>
          ) : null}
        </fieldset>
      </CardContent>
    </Card>
  );
}
