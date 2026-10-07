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
import { Radio, Sparkles, Volume2, VolumeX, Zap } from "lucide-react";
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

  // Pattern 2: Welcome Message Toggles (Dynamic & Interruptible)
  const initialDynamic = Boolean(
    (version.escalation_policy as Record<string, unknown>)?.dynamic_greeting ??
      version.greeting_text.toLowerCase().includes("[dynamic]")
  );
  const initialInterruptible = Boolean(
    version.conversation_policy?.interruption_enabled ??
      (version.escalation_policy as Record<string, unknown>)?.greeting_interruptible ??
      true
  );

  const [isDynamicGreeting, setIsDynamicGreeting] = React.useState<boolean>(initialDynamic);
  const [isInterruptibleGreeting, setIsInterruptibleGreeting] = React.useState<boolean>(initialInterruptible);
  const [hasToggleChanged, setHasToggleChanged] = React.useState<boolean>(false);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
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
      // 1. Update version with metadata for dynamic & interruptible greeting
      const updatedEscalationPolicy = {
        ...(version.escalation_policy || {}),
        dynamic_greeting: isDynamicGreeting,
        greeting_interruptible: isInterruptibleGreeting,
      };

      await agentsApi.updateVersion(workspaceId, agentId, version.id, {
        ...data,
        escalation_policy: updatedEscalationPolicy,
      });

      // 2. Synchronize conversation policy barge-in setting
      if (version.conversation_policy?.id) {
        await agentsApi.updatePolicy(workspaceId, agentId, version.id, {
          interruption_enabled: isInterruptibleGreeting,
        });
      }

      toast({ title: "Persona saved successfully", variant: "success" });
      setHasToggleChanged(false);
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not save persona",
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
    <Card className="border-border/80 bg-surface">
      <CardHeader className="flex-row items-center justify-between border-b border-border/40 pb-5">
        <div>
          <CardTitle className="text-lg font-bold flex items-center">
            Persona Configuration
            <Badge variant="outline" className="ml-2 font-mono text-primary border-primary/30">
              v{version.version_number}
            </Badge>
          </CardTitle>
          <CardDescription>
            {readOnly
              ? "Published versions are immutable for auditing compliance."
              : "Draft version — customize dialogue opening, tone, and conversation rules."}
          </CardDescription>
        </div>
        {readOnly ? (
          <Button variant="secondary" size="sm" onClick={createNewDraft} type="button">
            Create new version to edit
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="pt-6">
        <fieldset disabled={readOnly} className="space-y-6 disabled:opacity-60">
          {/* AI Disclosure */}
          <div>
            <Label htmlFor="ai_disclosure_text" className="font-semibold text-foreground">
              Mandatory AI Disclosure
            </Label>
            <p className="mb-1.5 text-xs text-muted-foreground">
              Spoken immediately upon connection to comply with Indian telecom consumer transparency norms.
            </p>
            <Textarea
              id="ai_disclosure_text"
              className="font-sans"
              rows={2}
              {...register("ai_disclosure_text")}
            />
          </div>

          {/* Pattern 2: Welcome Message with Dynamic + Interruptible Toggles */}
          <div className="rounded-xl border border-primary/20 bg-surface-raised/60 p-4 space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <Label htmlFor="greeting_text" className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <span>Welcome Message (Greeting)</span>
                  <span className="font-mono text-[11px] font-normal text-muted-foreground">
                    {"{name}"} fills dynamically at call time
                  </span>
                </Label>
                <p className="text-xs text-muted-foreground">
                  Controls the opening utterance heard when the customer answers the phone call.
                </p>
              </div>

              {/* Toggles Strip (Dynamic & Interruptible) */}
              <div className="flex items-center gap-3 pt-1 sm:pt-0">
                {/* Dynamic Toggle */}
                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border/80 bg-surface px-2.5 py-1.5 transition-colors hover:border-primary/50">
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isDynamicGreeting}
                    onChange={(e) => {
                      setIsDynamicGreeting(e.target.checked);
                      setHasToggleChanged(true);
                    }}
                    disabled={readOnly}
                  />
                  <div
                    className={`flex h-4 w-7 items-center rounded-full transition-colors p-0.5 ${
                      isDynamicGreeting ? "bg-primary justify-end" : "bg-muted-foreground/30 justify-start"
                    }`}
                  >
                    <div
                      className={`h-3 w-3 rounded-full bg-black shadow-sm transition-transform`}
                    />
                  </div>
                  <div className="flex items-center gap-1 text-xs font-semibold text-foreground">
                    <Sparkles className={`h-3.5 w-3.5 ${isDynamicGreeting ? "text-primary" : "text-muted-foreground"}`} />
                    <span>Dynamic</span>
                  </div>
                </label>

                {/* Interruptible Toggle */}
                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border/80 bg-surface px-2.5 py-1.5 transition-colors hover:border-primary/50">
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isInterruptibleGreeting}
                    onChange={(e) => {
                      setIsInterruptibleGreeting(e.target.checked);
                      setHasToggleChanged(true);
                    }}
                    disabled={readOnly}
                  />
                  <div
                    className={`flex h-4 w-7 items-center rounded-full transition-colors p-0.5 ${
                      isInterruptibleGreeting ? "bg-primary justify-end" : "bg-muted-foreground/30 justify-start"
                    }`}
                  >
                    <div
                      className={`h-3 w-3 rounded-full bg-black shadow-sm transition-transform`}
                    />
                  </div>
                  <div className="flex items-center gap-1 text-xs font-semibold text-foreground">
                    {isInterruptibleGreeting ? (
                      <Volume2 className="h-3.5 w-3.5 text-primary" />
                    ) : (
                      <VolumeX className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                    <span>Interruptible</span>
                  </div>
                </label>
              </div>
            </div>

            {/* Toggle Status Descriptions */}
            <div className="flex flex-wrap gap-2 text-[11px]">
              {isDynamicGreeting ? (
                <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 font-medium text-amber-400 border border-amber-500/20">
                  <Sparkles className="h-3 w-3" />
                  Dynamic Active: AI crafts opening live from caller history &amp; context
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded bg-surface px-2 py-0.5 font-medium text-muted-foreground border border-border/60">
                  Static Greeting: Reads exact authored text below
                </span>
              )}

              {isInterruptibleGreeting ? (
                <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 font-medium text-emerald-400 border border-emerald-500/20">
                  <Volume2 className="h-3 w-3" />
                  Barge-in Enabled: Caller speaking immediately silences opening TTS
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded bg-surface px-2 py-0.5 font-medium text-muted-foreground border border-border/60">
                  <VolumeX className="h-3 w-3" />
                  Uninterruptible: Plays greeting through to completion before listening
                </span>
              )}
            </div>

            <Textarea
              id="greeting_text"
              rows={3}
              placeholder={
                isDynamicGreeting
                  ? "Describe dynamic guidelines, e.g.: Greet warmly, reference {business}, mention recent inquiry, ask if now is a good time to speak."
                  : "నమస్కారం {name} గారు, నేను {business} నుండి మాట్లాడుతున్న AI అసిస్టెంట్‌ని..."
              }
              {...register("greeting_text")}
            />
          </div>

          {/* Closing Text */}
          <div>
            <Label htmlFor="closing_text" className="font-semibold text-foreground">
              Closing Utterance
            </Label>
            <p className="mb-1.5 text-xs text-muted-foreground">
              Spoken gracefully before the call hangs up upon completing the objective.
            </p>
            <Textarea id="closing_text" rows={2} {...register("closing_text")} />
          </div>

          {/* Objective & Conversational Parameters */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="primary_objective">Primary Objective</Label>
              <Input id="primary_objective" {...register("primary_objective")} />
            </div>
            <div>
              <Label htmlFor="formality">Formality Level</Label>
              <select
                id="formality"
                className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                {...register("formality")}
              >
                {FORMALITY_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o.charAt(0).toUpperCase() + o.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="energy">Energy / Pacing</Label>
              <select
                id="energy"
                className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                {...register("energy")}
              >
                {ENERGY_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o.charAt(0).toUpperCase() + o.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="response_length">Response Length</Label>
              <select
                id="response_length"
                className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                {...register("response_length")}
              >
                {RESPONSE_LENGTH_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o.charAt(0).toUpperCase() + o.slice(1)} (telephony optimized)
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="code_switching_behavior">Multilingual Code-Switching</Label>
              <select
                id="code_switching_behavior"
                className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                {...register("code_switching_behavior")}
              >
                {CODE_SWITCH_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o.charAt(0).toUpperCase() + o.slice(1)} (Telugu • Hindi • English)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {!readOnly ? (
            <div className="pt-2">
              <Button
                onClick={handleSubmit(onSubmit)}
                type="button"
                loading={isSubmitting}
                disabled={!isDirty && !hasToggleChanged}
                variant="gradient"
                className="font-bold"
              >
                Save Persona &amp; Greeting Settings
              </Button>
            </div>
          ) : null}
        </fieldset>
      </CardContent>
    </Card>
  );
}
