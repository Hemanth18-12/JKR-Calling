"use client";

import { VoicePersonaUpdate, type AgentVersionDetail } from "@jkr/contracts";
import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, useToast } from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";

export function VoiceEditor({ workspaceId, agentId, version }: { workspaceId: string; agentId: string; version: AgentVersionDetail }) {
  const router = useRouter();
  const { toast } = useToast();
  const readOnly = version.status === "published";
  const voice = version.voice_persona;

  const {
    register,
    handleSubmit,
    formState: { isSubmitting, isDirty },
  } = useForm<VoicePersonaUpdate>({
    resolver: zodResolver(VoicePersonaUpdate),
    defaultValues: {
      voice_id: voice?.voice_id ?? "",
      gender_presentation: voice?.gender_presentation ?? "female",
      speaking_speed: voice?.speaking_speed ?? 1.0,
      stability: voice?.stability ?? 0.6,
      expressiveness: voice?.expressiveness ?? 0.6,
    },
  });

  const onSubmit = async (data: VoicePersonaUpdate) => {
    try {
      await agentsApi.updateVoice(workspaceId, agentId, version.id, {
        ...data,
        speaking_speed: Number(data.speaking_speed),
        stability: Number(data.stability),
        expressiveness: Number(data.expressiveness),
      });
      toast({ title: "Saved", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: "Could not save", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Voice <Badge variant="outline" className="ml-2">v{version.version_number}</Badge>
        </CardTitle>
        <CardDescription>
          Provider: <span className="font-mono">{voice?.provider ?? "mock"}</span> — real providers (ElevenLabs,
          Cartesia, Sarvam) plug in behind this same config once credentials exist (Phase 3).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <fieldset disabled={readOnly} className="space-y-4 disabled:opacity-60">
          <div>
            <Label htmlFor="voice_id">Voice ID</Label>
            <Input id="voice_id" {...register("voice_id")} />
          </div>
          <div>
            <Label htmlFor="gender_presentation">Gender presentation</Label>
            <select
              id="gender_presentation"
              className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              {...register("gender_presentation")}
            >
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="neutral">Neutral</option>
            </select>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label htmlFor="speaking_speed">Speaking speed ({"0.5"}–{"2.0"})</Label>
              <Input id="speaking_speed" type="number" step="0.05" min="0.5" max="2.0" {...register("speaking_speed", { valueAsNumber: true })} />
            </div>
            <div>
              <Label htmlFor="stability">Stability (0–1)</Label>
              <Input id="stability" type="number" step="0.05" min="0" max="1" {...register("stability", { valueAsNumber: true })} />
            </div>
            <div>
              <Label htmlFor="expressiveness">Expressiveness (0–1)</Label>
              <Input id="expressiveness" type="number" step="0.05" min="0" max="1" {...register("expressiveness", { valueAsNumber: true })} />
            </div>
          </div>
          {!readOnly ? (
            <Button onClick={handleSubmit(onSubmit)} type="button" loading={isSubmitting} disabled={!isDirty}>
              Save voice
            </Button>
          ) : null}
        </fieldset>
      </CardContent>
    </Card>
  );
}
