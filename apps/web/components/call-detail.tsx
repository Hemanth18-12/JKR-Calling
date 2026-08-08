import { type CallDetail as CallDetailType, type ToolExecutionOut, CALL_STATUS_VARIANT, TOOL_NAME_LABELS } from "@jkr/contracts";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@jkr/ui";

function SpeakerBubble({ turn }: { turn: CallDetailType["turns"][number] }) {
  const isAgent = turn.speaker === "agent";
  return (
    <div className={`flex ${isAgent ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${isAgent ? "bg-surface-raised" : "bg-primary/15"}`}>
        <p className="mb-0.5 text-xs font-medium uppercase text-muted-foreground">
          {isAgent ? "Agent" : "Customer"} {turn.is_interrupted ? <span className="text-warning">· interrupted</span> : null}
        </p>
        <p>{turn.text}</p>
      </div>
    </div>
  );
}

export function CallDetail({ call, toolExecutions }: { call: CallDetailType; toolExecutions: ToolExecutionOut[] }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Call detail</h1>
          <p className="text-sm text-muted-foreground">
            {call.direction} · {call.language ?? "unknown language"}
            {call.duration_seconds !== null ? ` · ${call.duration_seconds}s` : ""}
          </p>
        </div>
        <Badge variant={CALL_STATUS_VARIANT[call.status] ?? "secondary"}>{call.status.replace(/_/g, " ")}</Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Transcript</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {call.turns.length === 0 ? (
              <p className="text-sm text-muted-foreground">No turns recorded.</p>
            ) : (
              call.turns.map((t) => <SpeakerBubble key={t.turn_ref} turn={t} />)
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          {call.outcome ? (
            <Card>
              <CardHeader>
                <CardTitle>Outcome</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{call.outcome.category.replace(/_/g, " ")}</Badge>
                  {call.outcome.lead_score ? <Badge variant="secondary">{call.outcome.lead_score}</Badge> : null}
                </div>
                {call.outcome.score_reasons.length > 0 ? (
                  <ul className="list-inside list-disc text-xs text-muted-foreground">
                    {call.outcome.score_reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {call.interruptions.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Interruptions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                {call.interruptions.map((i, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <span>{i.classification.replace(/_/g, " ")}</span>
                    {i.stop_latency_ms !== null ? <span className="text-xs text-muted-foreground">{i.stop_latency_ms}ms stop</span> : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {toolExecutions.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Tool executions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {toolExecutions.map((e) => (
                  <div key={e.id} className="flex items-center justify-between">
                    <span>{TOOL_NAME_LABELS[e.tool_name] ?? e.tool_name}</span>
                    <Badge variant={e.status === "succeeded" ? "success" : e.status === "failed" ? "danger" : "secondary"}>{e.status}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
